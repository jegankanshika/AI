"""FastAPI service exposing POST /underwrite + a minimal UI at /.

Run locally:  uvicorn app.api.main:app --reload
Then open http://localhost:8000/
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent.runner import run_agent
from app.idp.extractor import extract as extract_document
from app.idp.schemas import DocumentRef, DocumentType
from app.schemas import LoanApplication, UnderwritingMemo

UPLOADS_DIR = Path(os.environ.get("UPLOADS_DIR", "uploads")).resolve()
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Credit Co-Pilot", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev convenience; tighten in prod
    allow_methods=["*"],
    allow_headers=["*"],
)


class UnderwriteResponse(BaseModel):
    memo: UnderwritingMemo
    trace: dict


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/underwrite", response_model=UnderwriteResponse)
def underwrite(application: LoanApplication) -> UnderwriteResponse:
    memo, trace = run_agent(application)
    return UnderwriteResponse(
        memo=memo,
        trace={
            "tool_calls": trace.tool_calls,
            "tokens_in": trace.tokens_in,
            "tokens_out": trace.tokens_out,
            "latency_ms": trace.latency_ms,
            "revisions": trace.revisions,
            "critic_issues": trace.critic_issues,
            "extractions": trace.extractions,
            "income_verification": trace.income_verification,
        },
    )


class DocumentUploadResponse(BaseModel):
    doc_id: str
    doc_type: DocumentType
    path: str
    sha256: str | None
    extraction: dict


_ALLOWED_TYPES: tuple[DocumentType, ...] = ("paystub", "w2", "bank_statement", "photo_id")


@app.post("/documents", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
) -> DocumentUploadResponse:
    if doc_type not in _ALLOWED_TYPES:
        raise HTTPException(status_code=422, detail=f"unsupported doc_type {doc_type!r}")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="only .pdf is supported in this slice")

    doc_id = uuid.uuid4().hex[:12]
    dest = UPLOADS_DIR / f"{doc_id}.pdf"
    with dest.open("wb") as f:
        f.write(await file.read())

    ref = DocumentRef(doc_id=doc_id, doc_type=doc_type, path=str(dest))  # type: ignore[arg-type]
    extraction = extract_document(ref)
    return DocumentUploadResponse(
        doc_id=doc_id,
        doc_type=doc_type,  # type: ignore[arg-type]
        path=str(dest),
        sha256=extraction.fields.get("sha256"),
        extraction=extraction.model_dump(),
    )


# ---- UI ------------------------------------------------------------------

_UI_DIR = Path(__file__).resolve().parents[1] / "ui"


@app.get("/")
def root() -> FileResponse:
    return FileResponse(_UI_DIR / "index.html")


# Anything else under /ui/* serves static assets (currently just index.html;
# room to grow without changing the route table).
app.mount("/ui", StaticFiles(directory=_UI_DIR, html=True), name="ui")
