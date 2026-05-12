# Credit Co-Pilot: Agentic Loan Underwriting Assistant
## High-Level Design & Tech Stack

---

## 1. Overview

**Credit Co-Pilot** is an agentic AI system that assists human underwriters by
automating the data-gathering, analysis, and risk-narrative steps of loan
underwriting. The agent ingests an application packet (PDFs, bank statements,
tax returns, credit-bureau pulls), reasons over policy rules, computes risk
metrics, and produces an auditable underwriting memo with a recommended
decision (approve / decline / refer-to-human).

Design goals:
- **Human-in-the-loop**: the agent recommends, the underwriter decides.
- **Auditability**: every decision is traceable to source documents and policy clauses.
- **Compliance-first**: ECOA, FCRA, GLBA, GDPR, model-risk (SR 11-7) constraints baked in.
- **Modular**: swappable models, tools, and data sources.

---

## 2. System Architecture

```
                +-----------------------------+
                |       Loan Officer UI        |
                |  (Next.js + assistant chat)  |
                +--------------+---------------+
                               |
                               v
                +-----------------------------+
                |     API Gateway / BFF        |
                |   (FastAPI, OAuth2 / JWT)    |
                +--------------+---------------+
                               |
                               v
        +----------------------+-----------------------+
        |          Agent Orchestrator (LangGraph)       |
        |  - Planner / Router                           |
        |  - Tool executor (sandboxed)                  |
        |  - Memory (short + long term)                 |
        |  - Guardrails (PII, policy, jailbreak)        |
        +-+----------+--------+----------+--------+-----+
          |          |        |          |        |
          v          v        v          v        v
   +-------------+ +-------+ +--------+ +------+ +-----------+
   | Document AI | | RAG   | | Risk   | | Bureau| | Decision  |
   | (OCR + IDP) | | Index | | Models | | APIs  | | Engine    |
   +-------------+ +-------+ +--------+ +------+ +-----------+
          |          |         |          |          |
          v          v         v          v          v
   +-------------------------------------------------------+
   |                Data & Storage Layer                    |
   |  Postgres | S3 (docs) | pgvector/OpenSearch | Feature  |
   |  Store (Feast) | Kafka (events) | Audit log (WORM)    |
   +-------------------------------------------------------+
```

---

## 3. Core Components

### 3.1 Agent Orchestrator
- **Framework:** LangGraph (stateful graph) on top of the Anthropic SDK.
- **Model:** `claude-opus-4-7` for planning / memo drafting; `claude-haiku-4-5` for cheap classification, extraction, routing.
- **Prompt caching** on the policy manual + underwriting playbook (large, stable system context) to cut cost ~70%.
- **Tool use loop**: the model calls typed tools; orchestrator executes and feeds results back until a terminal `submit_memo` tool is invoked.
- **Determinism controls**: temperature 0 for numeric extraction and policy checks; higher temperature only for narrative.

### 3.2 Document Intelligence (IDP)
- **OCR**: AWS Textract or Azure Document Intelligence for forms + tables.
- **Layout-aware extraction**: LayoutLMv3 / Donut for structured fields (W-2, 1040, paystub, bank statement).
- **Schema validation**: Pydantic models per doc type; reject + re-prompt on schema miss.
- **Fraud signals**: file metadata, font-consistency, EXIF, MRZ/checksum checks.

### 3.3 Retrieval (RAG)
- **Vector store**: pgvector (small) or OpenSearch / Pinecone (scale).
- **Embeddings**: Voyage-3 or `text-embedding-3-large`.
- **Hybrid search**: BM25 + dense + reranker (Cohere Rerank or `claude-haiku` as reranker).
- **Corpus**: underwriting policy, product matrices, regulatory bulletins, prior memos (de-identified).

### 3.4 Risk & Scoring
- **Classical models** (served via MLflow / SageMaker / Vertex):
  - PD (probability of default) — XGBoost / LightGBM.
  - LGD / EAD — GBM or survival models.
  - Affordability — rules + DTI/DSCR calculators.
- **Feature store**: Feast, hydrated from bureau pulls, bank-transaction categorization, internal history.
- **Explainability**: SHAP values surfaced to the agent and rendered in the memo.

### 3.5 Decision Engine
- **Rules**: Open Policy Agent (OPA) / Rego or a DMN engine (Camunda) for hard policy gates (LTV caps, OFAC, age, jurisdiction).
- **Agent role**: gather evidence and propose; rules engine adjudicates hard constraints. Soft factors flow through the agent's narrative + score.

### 3.6 Tooling Surface (what the LLM can call)
- `fetch_credit_bureau(applicant_id)` — Experian / Equifax / TransUnion.
- `extract_document(doc_id, schema)` — IDP wrapper.
- `categorize_transactions(account_id, window)` — Plaid + classifier.
- `compute_ratios(financials)` — deterministic Python (DTI, DSCR, LTV).
- `lookup_policy(query)` — RAG over policy manual.
- `score_pd(features)` — calls ML model service.
- `run_kyc_aml(applicant)` — sanctions, PEP, adverse media.
- `request_stipulation(applicant_id, item)` — ask borrower for missing doc.
- `submit_memo(decision, rationale, citations)` — terminal action; writes to system of record.

All tools are typed (JSON schema), idempotent, and emit audit events.

### 3.7 Guardrails
- **Input**: PII redaction before sending to model where possible; prompt-injection filter on borrower-supplied text.
- **Output**: structured-output validator; policy-violation classifier (e.g. mention of prohibited basis under ECOA).
- **Action**: write-tools gated by capability tokens; dollar-amount and override actions require human approval.
- **Adversarial review**: secondary `claude-haiku` critic agent reviews the memo for hallucinated citations and disparate-impact red flags before submission.

### 3.8 Human-in-the-Loop UX
- Underwriter sees: structured memo, source citations (hover to view doc snippet), risk-score breakdown, agent's tool-call trace, and one-click overrides.
- Feedback (accept / edit / reject) is captured and routed to:
  - Eval set for offline regression.
  - RLHF/DPO data candidates (with compliance review).

---

## 4. Tech Stack Summary

| Layer | Choice |
|---|---|
| LLM | Claude Opus 4.7 (reasoning) + Claude Haiku 4.5 (utility) via Anthropic API |
| Agent framework | LangGraph + Anthropic SDK tool use |
| Backend | Python 3.12, FastAPI, Pydantic v2 |
| Frontend | Next.js 14 (App Router), React, Tailwind, shadcn/ui, Vercel AI SDK |
| Auth | Auth0 / Okta, OAuth2 + OIDC, RBAC via Cerbos |
| Storage | Postgres 16, S3 (docs, encrypted KMS), pgvector / OpenSearch |
| Streaming | Kafka or Kinesis for event bus |
| Workflow | Temporal for long-running async tasks (doc ingest, bureau pulls) |
| ML serving | MLflow + KServe / SageMaker endpoints |
| Feature store | Feast |
| Rules | OPA (Rego) or Camunda DMN |
| Observability | OpenTelemetry, Datadog, LangSmith / Langfuse for LLM traces |
| Eval | Promptfoo + custom golden set; offline shadow scoring |
| Infra | AWS (EKS), Terraform, GitHub Actions CI/CD |
| Secrets | AWS Secrets Manager + KMS |

---

## 5. Data Model (selected)

- `application(id, applicant_id, product, amount, status, created_at)`
- `document(id, application_id, type, s3_key, ocr_json, hash, uploaded_at)`
- `extraction(document_id, schema_version, fields_jsonb, confidence)`
- `bureau_pull(applicant_id, bureau, pulled_at, payload_jsonb, hash)`
- `risk_score(application_id, model_version, pd, lgd, ead, features_jsonb, shap_jsonb)`
- `agent_run(application_id, run_id, model, prompt_hash, tool_trace_jsonb, tokens, cost)`
- `memo(application_id, run_id, decision, rationale_md, citations_jsonb, reviewer_id, reviewed_at)`
- `audit_event(id, actor, action, target, payload_jsonb, ts)` — WORM, immutable.

---

## 6. Sequence (Happy Path)

1. Loan officer uploads application packet → S3; event on Kafka.
2. Temporal workflow: IDP extracts each doc; results persisted; structured fields validated.
3. Bureau + KYC tools called in parallel; results cached.
4. Agent run starts. Planner builds task list: verify identity → assemble income → compute ratios → check policy → score → draft memo.
5. Agent executes tools; each call logged with inputs/outputs + cost.
6. Decision engine evaluates hard gates against extracted features; agent receives the verdict.
7. Critic agent reviews draft memo; on pass, memo persisted and surfaced to underwriter.
8. Underwriter approves / edits / declines; final action recorded; downstream booking system notified.

---

## 7. Compliance, Risk, and Governance

- **Model risk (SR 11-7 / OCC 2011-12)**: model inventory, independent validation, ongoing monitoring (PSI, KS, AUC drift).
- **Fair lending**: disparate-impact testing on agent recommendations vs. protected classes; prohibited-basis filter on inputs.
- **Explainability**: every decline ships with adverse-action reason codes (FCRA §615).
- **Data**: PII tokenized at rest; access logged; data-retention per jurisdiction.
- **Reproducibility**: prompts, model versions, and tool versions pinned per `agent_run`; deterministic replay supported.
- **Change management**: prompt + policy changes flow through PR review, eval-gated CI, and staged rollout (shadow → canary → 100%).

---

## 8. Evaluation Strategy

- **Offline**: golden set of ~500 historical applications with ground-truth decisions; track decision concordance, memo factuality, citation accuracy, ratio-calculation accuracy.
- **Shadow mode**: run agent alongside underwriters for N weeks; compare without acting.
- **Online**: champion/challenger; KPIs = cycle time, underwriter override rate, default rate at 6/12 months, complaint rate.
- **Red team**: prompt injection via borrower-supplied PDFs; synthetic fraud documents; bias probes.

---

## 9. Phased Rollout

| Phase | Scope | Exit criteria |
|---|---|---|
| 0. Spike | Single product (unsecured personal loan), 1 IDP doc type, read-only memo draft | Memo factuality ≥ 95% on golden set |
| 1. Assistive | Full doc set, agent drafts memo, human decides | Underwriter time per file −30% |
| 2. Co-pilot | Agent auto-approves low-risk band under thresholds | Default rate ≤ baseline, override rate < 10% |
| 3. Expand | Add SMB / mortgage products; multi-language | Per-product eval gates |

---

## 10. Open Questions

- Build vs. buy for IDP (Textract vs. Hyperscience vs. in-house Donut)?
- On-prem deployment requirement for any jurisdictions? If yes, evaluate Claude on Bedrock + private VPC.
- Tolerance for fully-automated decisions in any band, or always human-in-the-loop at launch?
- Source of truth for policy: PDF manual vs. structured DSL? RAG quality depends on this.
