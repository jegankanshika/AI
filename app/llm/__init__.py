"""LLM provider selection.

Two providers are supported:

  * `anthropic` (default) — uses the Anthropic SDK.
  * `ollama`              — calls a local Ollama server's /api/chat
                            endpoint via a thin shim that mimics the
                            Anthropic SDK surface used in app/agent/.

Switch via env:
    LLM_PROVIDER=ollama
    LLM_MODEL=llama3.1
    LLM_CRITIC_MODEL=llama3.2:3b
    OLLAMA_HOST=http://localhost:11434
"""
from __future__ import annotations

import os


def provider() -> str:
    return os.environ.get("LLM_PROVIDER", "anthropic").lower()


def get_client():
    if provider() == "ollama":
        from app.llm.ollama import OllamaClient
        return OllamaClient()
    import anthropic
    return anthropic.Anthropic()


def have_credentials() -> bool:
    """True iff we can run the live path. Ollama is assumed reachable —
    a missing server surfaces as a clear connection error on first call."""
    if provider() == "ollama":
        return True
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def model_name() -> str:
    if provider() == "ollama":
        return os.environ.get("LLM_MODEL", "llama3.1")
    return os.environ.get("LLM_MODEL", "claude-opus-4-7")


def critic_model_name() -> str:
    if provider() == "ollama":
        return os.environ.get("LLM_CRITIC_MODEL", os.environ.get("LLM_MODEL", "llama3.1"))
    return os.environ.get("LLM_CRITIC_MODEL", "claude-haiku-4-5")
