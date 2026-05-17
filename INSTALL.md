# Prerequisites & Installation

Steps to set up the environment and reproduce the design artifacts
(architecture diagram, composed PDF) and to generate the synthetic
training dataset used to develop the Credit Co-Pilot risk models.

---

## 1. System prerequisites

| Tool | Purpose | Tested version |
|---|---|---|
| Python | runs the build + data scripts | 3.10 – 3.12 |
| pip | package manager | latest |
| git | clone / push | any |

---

## 2. Python environment

A virtual environment is strongly recommended.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

The pinned dependencies (`requirements.txt`):

- `faker`, `numpy`, `pandas` — synthetic training-data generator.

---

## 3. Generate the synthetic training dataset

```bash
python training_data/generate_synthetic_data.py --rows 10000 \
    --out training_data/synthetic_loans.csv --seed 42
```

See `training_data/README.md` and `training_data/data_dictionary.md`
for the schema, generation logic, and the bias / leakage caveats.

---

## 4. Optional — runtime stack for the full system

The design references a much larger production stack (Claude API,
AWS EKS, Temporal, Kafka, Postgres, OPA, etc.). Those are **not**
installed by this repo — see `credit_copilot_design.md` §4 for
the canonical choices and `CreditCoPilot_Design.pdf` for the
architecture diagram.

Minimum dev credentials you will eventually need:

- `ANTHROPIC_API_KEY` — for Claude Opus 4.7 / Haiku 4.5.
- AWS credentials with access to S3, KMS, Textract, SageMaker.
- Bureau / Plaid / KYC sandbox keys.

Keep these out of the repo. Use a `.env` file (gitignored) or your
secret manager of choice.

---

## 5. Troubleshooting

- **`Resource not accessible by integration` on push** — the GitHub
  integration token lacks `contents: write` for this repo; re-authorize
  and restart your session.
