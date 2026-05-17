# Data Dictionary — `synthetic_loans.csv`

All fields are synthetic. Types in pandas notation.

| Column | Type | Unit / Domain | Description |
|---|---|---|---|
| `application_id` | string (uuid4) | — | Synthetic application identifier. |
| `applicant_id` | string (uuid4) | — | Synthetic applicant identifier. |
| `application_date` | date | ISO-8601 | Date the application was submitted. |
| `age` | int | years, 18–80 | Applicant age. |
| `state` | string | US 2-letter | Applicant state of residence. |
| `employment_status` | category | `{employed, self_employed, retired, unemployed, student}` | Current employment. |
| `years_employed` | float | years, 0–45 | Tenure in current job (0 if unemployed). |
| `annual_income` | float | USD | Gross annual income (log-normal). |
| `monthly_housing_cost` | float | USD / month | Rent or mortgage payment. |
| `product` | category | `{personal_loan, auto, mortgage, sm_business}` | Product applied for. |
| `requested_amount` | float | USD | Loan amount requested. |
| `term_months` | int | months | Loan term. |
| `purpose` | category | `{debt_consolidation, home_improvement, auto, medical, business, other}` | Stated purpose. |
| `interest_rate_offered` | float | annual %, e.g. 7.25 | Rate offered at origination. |
| `credit_score` | int | 300–850 | Bureau score (FICO-like). |
| `revolving_utilization` | float | 0.0–1.5 | Revolving balances / limits. |
| `open_trades` | int | count | Open trade lines. |
| `delinquencies_24m` | int | count | 30+ day delinquencies in last 24 months. |
| `inquiries_6m` | int | count | Hard inquiries in last 6 months. |
| `bankruptcies_7y` | int | count | Bankruptcies in last 7 years. |
| `oldest_trade_months` | int | months | Age of oldest trade line. |
| `dti` | float | ratio, 0.0–2.0 | Total monthly debt / gross monthly income. |
| `pti` | float | ratio, 0.0–1.0 | Loan payment / gross monthly income. |
| `ltv` | float | ratio, 0.0–1.5 | Loan-to-value (mortgage / auto only; NaN otherwise). |
| `outcome` | category | `{paid, current, delinquent, default, charged_off}` | Terminal status at observation cutoff. |
| `default_within_12m` | int | {0, 1} | **Primary PD target.** 1 if 90+ DPD within 12 months of origination. |
| `lgd` | float | 0.0–1.0 | Realized loss given default (NaN if no default). |
| `ead` | float | USD | Exposure at default (NaN if no default). |

## Excluded by policy

The following attributes are **never** included in the schema. Adding them is
a fair-lending violation under ECOA / Reg B and will fail CI checks.

- Race / ethnicity
- Gender
- Marital status
- National origin
- Religion
- Receipt of public assistance
- Age, only used as a positive factor (special rule under Reg B)
- Any direct PII (name, SSN, full address, phone, email)

## Target leakage

These columns are computed *after* origination and must be dropped before
training:

- `outcome`, `default_within_12m`, `lgd`, `ead`

`default_within_12m` is the supervised label and goes into `y`, not `X`.
