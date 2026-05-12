"""Compose the Credit Co-Pilot design PDF with cover, architecture diagram, and content."""
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak,
    Table, TableStyle, ListFlowable, ListItem, KeepTogether
)
from reportlab.pdfgen import canvas
from PIL import Image as PILImage

PNG = "/home/user/AI/credit_copilot_architecture.png"
OUT = "/home/user/AI/CreditCoPilot_Design.pdf"

styles = getSampleStyleSheet()

TITLE = ParagraphStyle(
    "TitleX", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=30, leading=36, alignment=TA_CENTER, textColor=colors.HexColor("#0B3D91")
)
SUB = ParagraphStyle(
    "SubX", parent=styles["Title"], fontName="Helvetica",
    fontSize=16, leading=22, alignment=TA_CENTER, textColor=colors.HexColor("#444444")
)
H1 = ParagraphStyle(
    "H1X", parent=styles["Heading1"], fontName="Helvetica-Bold",
    fontSize=18, leading=22, textColor=colors.HexColor("#0B3D91"), spaceBefore=10, spaceAfter=8
)
H2 = ParagraphStyle(
    "H2X", parent=styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=13, leading=17, textColor=colors.HexColor("#1F4E79"), spaceBefore=8, spaceAfter=4
)
BODY = ParagraphStyle(
    "BodyX", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=10.5, leading=15, alignment=TA_LEFT, textColor=colors.HexColor("#1F1F1F")
)
BULLET = ParagraphStyle(
    "BulletX", parent=BODY, leftIndent=14, bulletIndent=4
)
SMALL = ParagraphStyle(
    "Small", parent=BODY, fontSize=9, leading=12, textColor=colors.HexColor("#666666")
)


def hr(color="#0B3D91", width=1):
    from reportlab.platypus import HRFlowable
    return HRFlowable(width="100%", thickness=width, color=colors.HexColor(color), spaceBefore=4, spaceAfter=8)


def header_footer(canv: canvas.Canvas, doc):
    canv.saveState()
    w, h = doc.pagesize
    # Header bar
    canv.setFillColor(colors.HexColor("#0B3D91"))
    canv.rect(0, h - 1.0 * cm, w, 1.0 * cm, fill=1, stroke=0)
    canv.setFillColor(colors.white)
    canv.setFont("Helvetica-Bold", 10)
    canv.drawString(1.2 * cm, h - 0.65 * cm, "Credit Co-Pilot — Agentic Loan Underwriting Assistant")
    canv.setFont("Helvetica", 9)
    canv.drawRightString(w - 1.2 * cm, h - 0.65 * cm, "High-Level Design")
    # Footer
    canv.setFillColor(colors.HexColor("#888888"))
    canv.setFont("Helvetica", 8)
    canv.drawString(1.2 * cm, 0.6 * cm, "Confidential — Internal Use Only")
    canv.drawRightString(w - 1.2 * cm, 0.6 * cm, f"Page {doc.page}")
    canv.restoreState()


def cover_page(canv: canvas.Canvas, doc):
    w, h = doc.pagesize
    canv.saveState()
    # gradient-like band
    canv.setFillColor(colors.HexColor("#0B3D91"))
    canv.rect(0, h - 7 * cm, w, 7 * cm, fill=1, stroke=0)
    canv.setFillColor(colors.HexColor("#1F77B4"))
    canv.rect(0, h - 8 * cm, w, 1 * cm, fill=1, stroke=0)

    canv.setFillColor(colors.white)
    canv.setFont("Helvetica-Bold", 34)
    canv.drawCentredString(w / 2, h - 4 * cm, "Credit Co-Pilot")
    canv.setFont("Helvetica", 18)
    canv.drawCentredString(w / 2, h - 5.2 * cm, "Agentic Loan Underwriting Assistant")
    canv.setFont("Helvetica-Oblique", 13)
    canv.drawCentredString(w / 2, h - 6.2 * cm, "High-Level Design  |  Tech Stack  |  System Architecture")

    # tags
    canv.setFillColor(colors.HexColor("#333333"))
    canv.setFont("Helvetica-Bold", 11)
    canv.drawCentredString(w / 2, h - 10 * cm,
                           "Claude Opus 4.7  •  LangGraph  •  AWS EKS  •  Temporal  •  Postgres  •  Kafka")
    canv.setFont("Helvetica", 11)
    canv.drawCentredString(w / 2, h - 10.8 * cm,
                           "OPA  •  SageMaker  •  pgvector  •  Feast  •  MLflow  •  Datadog")

    canv.setFillColor(colors.HexColor("#888888"))
    canv.setFont("Helvetica", 10)
    canv.drawCentredString(w / 2, 2 * cm, "Prepared 2026-05-12 • Confidential")
    canv.restoreState()


def fit_image(path, max_w, max_h):
    im = PILImage.open(path)
    iw, ih = im.size
    ratio = min(max_w / iw, max_h / ih)
    return Image(path, width=iw * ratio, height=ih * ratio)


story = []

# Cover page (drawn via onFirstPage); add a blank flowable
story.append(Spacer(1, 1))
story.append(PageBreak())

# Page 2: Executive summary
story.append(Paragraph("Executive Summary", H1))
story.append(hr())
story.append(Paragraph(
    "Credit Co-Pilot is an agentic AI system that assists human underwriters by automating "
    "data gathering, analysis, and risk-narrative drafting for loan applications. The agent "
    "ingests an application packet (PDFs, bank statements, tax returns, bureau pulls), reasons "
    "over policy rules, computes risk metrics, and produces an auditable underwriting memo with "
    "a recommended decision (approve / decline / refer-to-human).", BODY))
story.append(Spacer(1, 8))
story.append(Paragraph("Design pillars", H2))
for b in [
    "<b>Human-in-the-loop</b> — the agent recommends, the underwriter decides.",
    "<b>Auditability</b> — every decision traces to source documents and policy clauses.",
    "<b>Compliance-first</b> — ECOA, FCRA, GLBA, GDPR, SR 11-7 baked in.",
    "<b>Modular</b> — swappable models, tools, and data sources.",
]:
    story.append(Paragraph("• " + b, BULLET))

story.append(Spacer(1, 10))
story.append(Paragraph("Headline KPIs (target)", H2))
kpi_data = [
    ["Cycle time / file", "−30% Phase 1", "−55% Phase 2"],
    ["Memo factuality (golden set)", "≥ 95%", "≥ 98%"],
    ["Underwriter override rate", "< 20%", "< 10%"],
    ["Default rate vs. baseline", "≤ baseline", "≤ baseline"],
]
t = Table(kpi_data, colWidths=[6.5 * cm, 4.5 * cm, 4.5 * cm])
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F0FE")),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BBBBBB")),
    ("FONT", (0, 0), (-1, -1), "Helvetica", 10),
    ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 10),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
]))
story.append(t)

story.append(PageBreak())

# Page 3: Architecture diagram (landscape via separate doc would be ideal, but we keep portrait + scale)
story.append(Paragraph("System Architecture", H1))
story.append(hr())
story.append(Paragraph(
    "End-to-end view of components, data flow, and the AI/ML, knowledge, decisioning, and "
    "platform planes. Tech logos are used to indicate the canonical implementation choice for "
    "each role.", BODY))
story.append(Spacer(1, 8))
story.append(fit_image(PNG, max_w=17.5 * cm, max_h=22 * cm))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "Figure 1. Credit Co-Pilot reference architecture. Solid arrows indicate runtime data "
    "flow; dotted arrows indicate platform/observability dependencies.", SMALL))
story.append(PageBreak())

# Page 4: Core components
story.append(Paragraph("Core Components", H1))
story.append(hr())

components = [
    ("Agent Orchestrator",
     "LangGraph state machine on the Anthropic SDK. <b>Claude Opus 4.7</b> for planning and memo "
     "drafting; <b>Claude Haiku 4.5</b> for cheap classification, extraction, and routing. Prompt "
     "caching pins the policy manual + underwriting playbook (~70% cost reduction). Tool-use loop "
     "runs until the terminal <i>submit_memo</i> tool is invoked. Temperature 0 for numeric "
     "extraction and policy checks; higher only for narrative."),
    ("Document Intelligence (IDP)",
     "AWS Textract / Azure Document Intelligence for OCR + tables; LayoutLMv3 / Donut for "
     "structured fields (W-2, 1040, paystub, bank statement). Pydantic schema validation; "
     "fraud signals from EXIF, font consistency, MRZ checksums."),
    ("Retrieval (RAG)",
     "pgvector (small scale) or OpenSearch / Pinecone (scale). Voyage-3 or text-embedding-3-large "
     "embeddings. Hybrid BM25 + dense + reranker (Cohere Rerank or Haiku-as-judge). Corpus = "
     "policy, product matrices, regulatory bulletins, de-identified prior memos."),
    ("Risk &amp; Scoring",
     "PD/LGD/EAD models (XGBoost / LightGBM, survival models) served via MLflow + SageMaker. "
     "Feast feature store. SHAP values surfaced in the memo for explainability."),
    ("Decision Engine",
     "Open Policy Agent (Rego) or Camunda DMN for hard policy gates — LTV caps, OFAC, "
     "jurisdiction, age. Agent proposes; rules engine adjudicates."),
    ("Guardrails",
     "PII redaction, prompt-injection filter on borrower text, structured-output validator, "
     "policy-violation classifier (prohibited basis under ECOA), capability-token-gated write "
     "tools, and a Haiku critic agent that reviews the memo for hallucinated citations and "
     "disparate-impact red flags before submission."),
    ("Human-in-the-Loop UX",
     "Underwriter sees structured memo with hover-to-source citations, risk-score breakdown, "
     "agent tool-call trace, and one-click overrides. Feedback feeds offline eval and (with "
     "compliance review) RLHF/DPO datasets."),
]
for title, body in components:
    story.append(Paragraph(title, H2))
    story.append(Paragraph(body, BODY))
    story.append(Spacer(1, 4))

story.append(PageBreak())

# Page 5: Tech stack table
story.append(Paragraph("Tech Stack", H1))
story.append(hr())
stack = [
    ["Layer", "Choice"],
    ["LLM", "Claude Opus 4.7 (reasoning) + Haiku 4.5 (utility) via Anthropic API"],
    ["Agent framework", "LangGraph + Anthropic SDK tool use"],
    ["Backend", "Python 3.12, FastAPI, Pydantic v2"],
    ["Frontend", "Next.js 14, React, Tailwind, shadcn/ui, Vercel AI SDK"],
    ["Auth / RBAC", "Auth0 / Okta, OAuth2 + OIDC, Cerbos"],
    ["Storage", "Postgres 16, S3 (KMS), pgvector / OpenSearch"],
    ["Event bus", "Kafka / Kinesis"],
    ["Workflow", "Temporal (long-running async tasks)"],
    ["ML serving", "MLflow + KServe / SageMaker"],
    ["Feature store", "Feast"],
    ["Rules", "OPA (Rego) or Camunda DMN"],
    ["Observability", "OpenTelemetry, Datadog, LangSmith / Langfuse"],
    ["Eval", "Promptfoo + custom golden set; offline shadow scoring"],
    ["Infra", "AWS EKS, Terraform, GitHub Actions"],
    ["Secrets", "AWS Secrets Manager + KMS"],
]
ts = Table(stack, colWidths=[5 * cm, 11 * cm])
ts.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3D91")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 11),
    ("FONT", (0, 1), (-1, -1), "Helvetica", 10),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FB")]),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
]))
story.append(ts)

story.append(PageBreak())

# Page 6: Tools, sequence, compliance, rollout
story.append(Paragraph("Agent Tool Surface", H1))
story.append(hr())
tools = [
    ("fetch_credit_bureau", "Experian / Equifax / TransUnion pulls."),
    ("extract_document", "IDP wrapper, schema-validated."),
    ("categorize_transactions", "Plaid + transaction classifier."),
    ("compute_ratios", "Deterministic DTI, DSCR, LTV."),
    ("lookup_policy", "RAG over the policy manual."),
    ("score_pd", "Calls the PD ML model service."),
    ("run_kyc_aml", "Sanctions, PEP, adverse media."),
    ("request_stipulation", "Asks the borrower for a missing doc."),
    ("submit_memo", "Terminal action — writes to system of record."),
]
for name, desc in tools:
    story.append(Paragraph(f"<b><font color='#0B3D91'>{name}</font></b> — {desc}", BULLET))

story.append(Spacer(1, 10))
story.append(Paragraph("Happy-Path Sequence", H1))
story.append(hr())
seq = [
    "Loan officer uploads packet → S3; event on Kafka.",
    "Temporal workflow: IDP extracts each doc; structured fields validated.",
    "Bureau + KYC tools called in parallel; results cached.",
    "Agent run starts: planner builds task list — verify identity → assemble income → compute ratios → policy check → score → draft memo.",
    "Agent executes tools; every call logged with I/O and cost.",
    "Decision engine evaluates hard gates; agent receives verdict.",
    "Critic agent reviews draft; on pass, memo persisted and shown to underwriter.",
    "Underwriter approves / edits / declines; downstream booking system notified.",
]
for i, s in enumerate(seq, 1):
    story.append(Paragraph(f"<b>{i}.</b> {s}", BULLET))

story.append(PageBreak())

# Page 7: Compliance + rollout
story.append(Paragraph("Compliance, Risk &amp; Governance", H1))
story.append(hr())
for line in [
    "<b>SR 11-7 / OCC 2011-12</b> — model inventory, independent validation, ongoing PSI/KS/AUC monitoring.",
    "<b>Fair lending</b> — disparate-impact testing; prohibited-basis filter on inputs.",
    "<b>FCRA §615</b> — adverse-action reason codes attached to every decline.",
    "<b>Data</b> — PII tokenized at rest; access logged; per-jurisdiction retention.",
    "<b>Reproducibility</b> — prompts, model versions, and tool versions pinned per agent run; deterministic replay.",
    "<b>Change management</b> — prompt + policy changes flow through PR review, eval-gated CI, and staged rollout (shadow → canary → 100%).",
]:
    story.append(Paragraph("• " + line, BULLET))

story.append(Spacer(1, 10))
story.append(Paragraph("Phased Rollout", H1))
story.append(hr())
roll = [
    ["Phase", "Scope", "Exit criteria"],
    ["0. Spike", "Personal loan, 1 IDP doc type, read-only memo draft", "Memo factuality ≥ 95%"],
    ["1. Assistive", "Full doc set, agent drafts, human decides", "Underwriter time / file −30%"],
    ["2. Co-pilot", "Auto-approve low-risk band under thresholds", "Default ≤ baseline, override < 10%"],
    ["3. Expand", "SMB / mortgage, multi-language", "Per-product eval gates"],
]
rt = Table(roll, colWidths=[3 * cm, 8 * cm, 5.5 * cm])
rt.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3D91")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 11),
    ("FONT", (0, 1), (-1, -1), "Helvetica", 10),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FB")]),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
]))
story.append(rt)

story.append(Spacer(1, 10))
story.append(Paragraph("Open Questions", H1))
story.append(hr())
for q in [
    "Build vs. buy for IDP (Textract vs. Hyperscience vs. in-house Donut)?",
    "On-prem deployment requirement for any jurisdictions? If yes, evaluate Claude on Bedrock + private VPC.",
    "Tolerance for fully-automated decisions in any band, or always human-in-the-loop at launch?",
    "Source of truth for policy: PDF manual vs. structured DSL?",
]:
    story.append(Paragraph("• " + q, BULLET))


doc = SimpleDocTemplate(
    OUT, pagesize=A4,
    leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    topMargin=1.6 * cm, bottomMargin=1.4 * cm,
    title="Credit Co-Pilot — High-Level Design",
    author="Credit Co-Pilot Team",
)


def first_page(canv, d):
    cover_page(canv, d)


def later_pages(canv, d):
    header_footer(canv, d)


doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)
print(f"Wrote {OUT}")
