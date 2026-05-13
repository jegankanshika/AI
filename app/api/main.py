"""FastAPI service exposing POST /underwrite + a minimal UI at /.

Run locally:  uvicorn app.api.main:app --reload
Then open http://localhost:8000/
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent.runner import run_agent
from app.schemas import LoanApplication, UnderwritingMemo

app = FastAPI(title="Credit Co-Pilot", version="0.2.0")

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
        },
    )


# ---- UI ------------------------------------------------------------------

_UI_DIR = Path(__file__).resolve().parents[1] / "ui"


@app.get("/")
def root() -> FileResponse:
    return FileResponse(_UI_DIR / "index.html")


# Anything else under /ui/* serves static assets (currently just index.html;
# room to grow without changing the route table).
app.mount("/ui", StaticFiles(directory=_UI_DIR, html=True), name="ui")
