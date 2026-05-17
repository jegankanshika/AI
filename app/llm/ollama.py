"""Ollama client shim with the small API surface the agent graph uses.

Surface:
    client.messages.create(model=..., max_tokens=..., system=..., tools=..., messages=...)
    -> object with:
         .content       list of Block objects (.type, .text|.id+.name+.input)
         .usage         object with .input_tokens, .output_tokens
         .stop_reason   "tool_use" | "end_turn"

The graph and critic were originally built against the Anthropic
message/tool format, so this shim translates that format to and from
Ollama's OpenAI-compatible `/api/chat` shape:

  Tools:
    {name, description, input_schema}
       -> {type:"function", function:{name, description, parameters}}

  Messages:
    assistant content blocks: text + tool_use
       -> assistant message with `content` (concatenated text) and
          `tool_calls: [{id, type:"function", function:{name, arguments}}]`
    user content blocks: tool_result
       -> separate {role:"tool", tool_call_id, content} messages
    everything else passes through as-is.

The shim is intentionally minimal — it only supports the features the
agent graph and critic actually call. Streaming and citations are not
modeled here.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Block:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class Response:
    content: list[Block]
    usage: Usage
    stop_reason: str


class _Messages:
    def __init__(self, parent: "OllamaClient") -> None:
        self._parent = parent

    def create(self, *, model: str, max_tokens: int, system: str,
               messages: list[dict], tools: list[dict] | None = None) -> Response:
        return self._parent._create(model, max_tokens, system, messages, tools)


class OllamaClient:
    def __init__(self, host: str | None = None) -> None:
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.messages = _Messages(self)

    # ---- translation helpers ---------------------------------------------

    @staticmethod
    def _translate_tools(tools: list[dict] | None) -> list[dict] | None:
        if not tools:
            return None
        out = []
        for t in tools:
            out.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
                },
            })
        return out

    @staticmethod
    def _attr(b: Any, key: str, default=None):
        if isinstance(b, dict):
            return b.get(key, default)
        return getattr(b, key, default)

    @classmethod
    def _translate_messages(cls, system: str, messages: list[dict]) -> list[dict]:
        out: list[dict] = []
        if system:
            out.append({"role": "system", "content": system})

        for m in messages:
            role = m["role"]
            content = m["content"]
            if isinstance(content, str):
                out.append({"role": role, "content": content})
                continue

            if role == "assistant":
                texts: list[str] = []
                tool_calls: list[dict] = []
                for b in content:
                    btype = cls._attr(b, "type")
                    if btype == "text":
                        texts.append(cls._attr(b, "text", "") or "")
                    elif btype == "tool_use":
                        tool_calls.append({
                            "id": cls._attr(b, "id", "") or f"toolu_{uuid.uuid4().hex[:16]}",
                            "type": "function",
                            "function": {
                                "name": cls._attr(b, "name", ""),
                                "arguments": cls._attr(b, "input", {}) or {},
                            },
                        })
                msg: dict = {"role": "assistant", "content": "".join(texts)}
                if tool_calls:
                    msg["tool_calls"] = tool_calls
                out.append(msg)
                continue

            # role == "user"; content is a list of blocks
            spare_text: list[str] = []
            for b in content:
                btype = cls._attr(b, "type")
                if btype == "tool_result":
                    c = cls._attr(b, "content", "")
                    if not isinstance(c, str):
                        c = json.dumps(c)
                    out.append({
                        "role": "tool",
                        "tool_call_id": cls._attr(b, "tool_use_id", "") or "",
                        "content": c,
                    })
                elif btype == "text":
                    spare_text.append(cls._attr(b, "text", "") or "")
            if spare_text:
                out.append({"role": "user", "content": "".join(spare_text)})

        return out

    # ---- transport --------------------------------------------------------

    def _post_chat(self, body: dict) -> dict:
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"ollama request to {self.host}/api/chat failed: {e}"
            ) from e

    def _create(self, model: str, max_tokens: int, system: str,
                messages: list[dict], tools: list[dict] | None) -> Response:
        body: dict = {
            "model": model,
            "messages": self._translate_messages(system, messages),
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        otools = self._translate_tools(tools)
        if otools:
            body["tools"] = otools

        data = self._post_chat(body)

        msg = data.get("message") or {}
        blocks: list[Block] = []
        text = msg.get("content") or ""
        if text:
            blocks.append(Block(type="text", text=text))
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            blocks.append(Block(
                type="tool_use",
                id=tc.get("id") or f"toolu_{uuid.uuid4().hex[:16]}",
                name=fn.get("name", ""),
                input=args or {},
            ))

        stop_reason = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
        usage = Usage(
            input_tokens=int(data.get("prompt_eval_count") or 0),
            output_tokens=int(data.get("eval_count") or 0),
        )
        return Response(content=blocks, usage=usage, stop_reason=stop_reason)
