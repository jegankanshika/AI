"""OllamaClient shim — translation tests.

Mocks `urllib.request.urlopen` so no Ollama server is needed. Verifies:
  * tools translation (Anthropic input_schema -> OpenAI function.parameters),
  * outgoing message translation: assistant tool_use -> tool_calls;
    user tool_result -> role:tool with tool_call_id,
  * response translation: Ollama tool_calls -> Block(type='tool_use', ...),
  * stop_reason mapping ('tool_use' vs 'end_turn'),
  * factory: LLM_PROVIDER=ollama returns OllamaClient, default returns
    the Anthropic SDK client.
"""
from __future__ import annotations

import io
import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from app.llm.ollama import OllamaClient


@contextmanager
def fake_ollama_response(payload: dict):
    captured: dict = {}

    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): self.close()

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        return _Resp(json.dumps(payload).encode())

    with patch("app.llm.ollama.urllib.request.urlopen", new=_fake_urlopen):
        yield captured


def test_tools_translation():
    out = OllamaClient._translate_tools([{
        "name": "compute_ratios",
        "description": "Compute DTI/PTI/LTV.",
        "input_schema": {"type": "object", "properties": {"x": {"type": "number"}}, "required": ["x"]},
    }])
    assert out == [{
        "type": "function",
        "function": {
            "name": "compute_ratios",
            "description": "Compute DTI/PTI/LTV.",
            "parameters": {"type": "object", "properties": {"x": {"type": "number"}}, "required": ["x"]},
        },
    }]


def test_messages_translation_assistant_tool_use_and_user_tool_result():
    # Mimic an Anthropic-style assistant block list (using duck-typed objects).
    class _B:
        def __init__(self, **kw): self.__dict__.update(kw)

    msgs = [
        {"role": "user", "content": "underwrite this"},
        {"role": "assistant", "content": [
            _B(type="text", text="Calling tool..."),
            _B(type="tool_use", id="toolu_1", name="compute_ratios", input={"x": 1}),
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_1", "content": json.dumps({"dti": 0.3})},
        ]},
    ]
    out = OllamaClient._translate_messages("SYSTEM", msgs)
    assert out[0] == {"role": "system", "content": "SYSTEM"}
    assert out[1] == {"role": "user", "content": "underwrite this"}
    assert out[2]["role"] == "assistant"
    assert out[2]["content"] == "Calling tool..."
    assert out[2]["tool_calls"] == [{
        "id": "toolu_1", "type": "function",
        "function": {"name": "compute_ratios", "arguments": {"x": 1}},
    }]
    assert out[3] == {
        "role": "tool", "tool_call_id": "toolu_1",
        "content": json.dumps({"dti": 0.3}),
    }


def test_create_with_tool_calls_returns_tool_use_blocks():
    payload = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "function": {"name": "score_pd", "arguments": {"dti": 0.3, "pti": 0.05}},
            }],
        },
        "prompt_eval_count": 42,
        "eval_count": 7,
    }
    with fake_ollama_response(payload) as captured:
        client = OllamaClient(host="http://example:11434")
        resp = client.messages.create(
            model="llama3.1", max_tokens=500, system="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "score_pd", "description": "", "input_schema": {"type": "object"}}],
        )

    assert captured["url"] == "http://example:11434/api/chat"
    assert captured["body"]["model"] == "llama3.1"
    assert captured["body"]["stream"] is False
    assert captured["body"]["options"]["num_predict"] == 500
    assert captured["body"]["tools"][0]["function"]["name"] == "score_pd"

    assert resp.stop_reason == "tool_use"
    assert resp.usage.input_tokens == 42
    assert resp.usage.output_tokens == 7
    assert len(resp.content) == 1
    b = resp.content[0]
    assert b.type == "tool_use"
    assert b.name == "score_pd"
    assert b.input == {"dti": 0.3, "pti": 0.05}
    assert b.id.startswith("toolu_")


def test_create_text_only_returns_end_turn():
    payload = {
        "message": {"role": "assistant", "content": "hello there"},
        "prompt_eval_count": 10, "eval_count": 3,
    }
    with fake_ollama_response(payload):
        resp = OllamaClient().messages.create(
            model="llama3.1", max_tokens=100, system="", messages=[],
        )
    assert resp.stop_reason == "end_turn"
    assert resp.content[0].type == "text"
    assert resp.content[0].text == "hello there"


def test_factory_picks_ollama_when_env_set(monkeypatch):
    from app.llm import get_client, have_credentials, model_name, critic_model_name, provider
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "llama3.1")
    monkeypatch.setenv("LLM_CRITIC_MODEL", "llama3.2:3b")

    assert provider() == "ollama"
    assert have_credentials() is True
    assert model_name() == "llama3.1"
    assert critic_model_name() == "llama3.2:3b"
    assert isinstance(get_client(), OllamaClient)


def test_factory_default_is_anthropic(monkeypatch):
    from app.llm import have_credentials, model_name, provider
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert provider() == "anthropic"
    assert have_credentials() is False
    assert model_name() == "claude-opus-4-7"
