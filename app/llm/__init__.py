"""LLM provider.

Ollama is the only supported live provider. Configure via env:

    OLLAMA_HOST=http://localhost:11434   (default)
    LLM_MODEL=llama3.1                   (default)
    LLM_CRITIC_MODEL=llama3.2:3b         (defaults to LLM_MODEL)

`have_credentials()` returns True iff `OLLAMA_HOST` is set in the
environment — the runner uses that as the signal to take the live path
in auto mode. With no `OLLAMA_HOST`, auto mode stays on the
deterministic offline path.
"""
from __future__ import annotations

import os


def get_client():
    from app.llm.ollama import OllamaClient
    return OllamaClient()


def have_credentials() -> bool:
    return bool(os.environ.get("OLLAMA_HOST"))


def model_name() -> str:
    return os.environ.get("LLM_MODEL", "llama3.1")


def critic_model_name() -> str:
    return os.environ.get("LLM_CRITIC_MODEL", model_name())
