"""FastAPI service exposing POST /underwrite.

Run locally:  uvicorn app.api.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from app.agent.runner import run_agent
from app.schemas import LoanApplication, UnderwritingMemo

app = FastAPI(title="Credit Co-Pilot", version="0.1.0")


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
        },
    )
