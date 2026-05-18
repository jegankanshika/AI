"""Pydantic schemas for the EV Charging agent."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

Intent = Literal[
    "registrations",
    "stations",
    "station_economics",
    "challenges",
    "future_locations",
    "partners",
    "setup_plan",
    "growth_forecast",
    "summary",
]


class Query(BaseModel):
    question: str = Field(..., description="Natural-language ask from the user.")
    district: str | None = None
    highway_only: bool = False
    top_n: int | None = 10


class ToolCall(BaseModel):
    name: str
    args: dict


class AgentResponse(BaseModel):
    intent: Intent
    summary: str
    data: dict | list
    tool_calls: list[ToolCall] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
