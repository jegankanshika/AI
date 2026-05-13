# AI

High-level design and reference architecture for **Credit Co-Pilot** — an
agentic loan underwriting assistant. The repo holds the design write-up, a
branded PDF, a Visio-style architecture diagram rendered with real tech logos,
and the scripts that generate them.

---

## Contents

| File | What it is |
|---|---|
| `credit_copilot_design.md` | Markdown source of the Credit Co-Pilot high-level design (architecture, tech stack, data model, sequence flow, compliance, rollout). |
| `CreditCoPilot_Design.pdf` | Branded multi-page PDF of the design — cover page, exec summary + KPIs, full-page architecture figure, components, tech stack, tool surface, sequence, compliance, rollout, open questions. |
| `credit_copilot_architecture.png` / `.pdf` | Standalone architecture diagram with logos for Claude, AWS (EKS, S3, KMS, Textract, SageMaker, API Gateway), Postgres, Kafka, Temporal, Redis, OpenSearch, MLflow, OPA, Auth0, FastAPI, React, Terraform, GitHub Actions, Datadog, Langfuse, Slack. |
| `INSTALL.md` | System + Python prerequisites and step-by-step setup. |
| `requirements.txt` | Pinned Python dependencies. |
| `training_data/` | Synthetic loan dataset, schema dictionary, generator script, and policy snippets used as the RAG corpus. |

---

## Credit Co-Pilot — at a glance

An agentic AI system that assists human underwriters by automating data
gathering, analysis, and risk-narrative drafting for loan applications. The
agent ingests an application packet (PDFs, bank statements, tax returns,
bureau pulls), reasons over policy rules, computes risk metrics, and produces
an auditable underwriting memo with a recommended decision
(approve / decline / refer-to-human).

**Design pillars**
- Human-in-the-loop — agent recommends, underwriter decides.
- Auditability — every decision traces to source documents and policy clauses.
- Compliance-first — ECOA, FCRA, GLBA, GDPR, SR 11-7.
- Modular — swappable models, tools, and data sources.

**Core stack**
Claude Opus 4.7 + Haiku 4.5 · LangGraph · FastAPI · Next.js · AWS EKS ·
Temporal · Postgres + pgvector · Kafka · MLflow + SageMaker · OPA / Camunda ·
Feast · Datadog + Langfuse.

See `CreditCoPilot_Design.pdf` for the full design.

---

## Reproducing the diagram and PDF

Requirements: Python 3.10+, Graphviz.

```bash
# system dep (Debian/Ubuntu)
sudo apt-get install -y graphviz

# python deps
pip install diagrams reportlab pillow

# generate the architecture PNG/PDF
python build_diagram.py

# compose the branded design PDF (depends on the PNG above)
python build_pdf.py
```

Outputs:
- `credit_copilot_architecture.png` / `.pdf`
- `CreditCoPilot_Design.pdf`

---

## Branches

- `main` — stable artifacts.
- `claude/loan-underwriting-tech-design-iLTw4` — Credit Co-Pilot design work.

---

## License

No license has been declared yet. Treat the contents as **all rights reserved**
until a license file is added.
