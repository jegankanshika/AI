# Training Data — Credit Co-Pilot

This folder holds the **synthetic** loan-application dataset used to develop and
unit-test the Credit Co-Pilot risk models (PD / LGD / EAD), policy rules, and
agent prompts.

> ⚠️ **No real customer data is stored in this repository, ever.**
> Real underwriting data is regulated (GLBA, GDPR, FCRA) and must live in the
> production data plane (Postgres + S3 with KMS, access logged). The files here
> are entirely synthetic and exist only so engineers can run end-to-end tests
> locally and CI can run without secrets.

---

## Files

| File | What it is |
|---|---|
| `generate_synthetic_data.py` | Faker / numpy-based generator. Deterministic with `--seed`. |
| `synthetic_loans.csv` | A small (100-row) sample committed to the repo so tests run out of the box. |
| `data_dictionary.md` | Field-by-field definitions, types, units, and ranges. |
| `policy_snippets/` | Short markdown snippets used as the RAG corpus for `lookup_policy`. |

Generate a larger set locally:

```bash
python generate_synthetic_data.py --rows 10000 --out synthetic_loans.csv --seed 42
```

---

## Schema (summary)

The CSV mirrors the production `application + extraction + bureau_pull + risk_score`
join. One row = one historical loan application with a known outcome.

Key columns:

- **Identifiers**: `application_id`, `applicant_id` (synthetic UUIDs).
- **Applicant**: `age`, `state`, `employment_status`, `years_employed`,
  `annual_income`, `monthly_housing_cost`.
- **Loan**: `product`, `requested_amount`, `term_months`, `purpose`,
  `interest_rate_offered`.
- **Bureau**: `credit_score`, `revolving_utilization`, `open_trades`,
  `delinquencies_24m`, `inquiries_6m`, `bankruptcies_7y`, `oldest_trade_months`.
- **Derived ratios**: `dti`, `pti`, `ltv` (where applicable).
- **Label**: `outcome` ∈ {`paid`, `current`, `delinquent`, `default`,
  `charged_off`}, plus `default_within_12m` (binary, the primary PD target).

See `data_dictionary.md` for the full list.

---

## Generation logic (high level)

1. **Demographics**: Faker generates names → discarded (we keep only
   non-identifying numeric and categorical features).
2. **Financials**: log-normal income; employment length skewed by age;
   housing cost as a fraction of income.
3. **Bureau**: credit score sampled from a mixture (sub-prime / prime / super-prime)
   correlated with income and employment length.
4. **Loan terms**: amount and rate conditioned on credit tier.
5. **Outcome**: ground-truth PD computed from a hand-coded logistic model over
   {credit_score, dti, delinquencies_24m, employment_status}, with noise. Binary
   `default_within_12m` drawn from a Bernoulli on that PD.

The generator is **deliberately biased-free of protected attributes** — race,
gender, marital status, and national origin are not generated and must never
be added. The fair-lending tests in `tests/` will fail CI if any prohibited
basis appears in the schema.

---

## Caveats

- This synthetic data is fine for **plumbing tests, schema validation,
  prompt/regression evals, and demos**. It is **not** a substitute for real
  back-testing on historical book data, which must happen inside the secure
  data plane with model-risk sign-off (SR 11-7).
- The hand-coded outcome model is intentionally simple. Calibration and
  feature importance from this data will **not** match production.
- Do not train production models on this data.

---

## Updating the dataset

1. Edit `generate_synthetic_data.py`.
2. Re-generate the sample: `python generate_synthetic_data.py --rows 100 --seed 42 --out synthetic_loans.csv`.
3. Update `data_dictionary.md` if columns changed.
4. Commit all three together (generator + sample + dictionary).
