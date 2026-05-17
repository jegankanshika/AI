"""Simple file-based policy RAG over training_data/policy_snippets/*.md.

Uses TF-IDF style scoring (token overlap with IDF). Good enough for the
vertical slice; swap for pgvector + reranker in production.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path

from app.schemas import PolicyHit, PolicyResult

POLICY_DIR = Path(__file__).resolve().parents[2] / "training_data" / "policy_snippets"
_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]+")


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


@lru_cache(maxsize=1)
def _index() -> dict[str, dict]:
    docs: dict[str, dict] = {}
    if not POLICY_DIR.exists():
        return docs
    df: dict[str, int] = {}
    for path in sorted(POLICY_DIR.glob("*.md")):
        text = path.read_text()
        toks = _tokens(text)
        tf: dict[str, int] = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        for t in tf:
            df[t] = df.get(t, 0) + 1
        docs[path.stem] = {"path": path, "text": text, "tf": tf}
    n = max(len(docs), 1)
    idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}
    for d in docs.values():
        d["idf"] = idf
    return docs


def lookup_policy(query: str, k: int = 3) -> PolicyResult:
    docs = _index()
    q_toks = _tokens(query)
    scored: list[PolicyHit] = []
    for policy_id, d in docs.items():
        idf = d["idf"]
        score = 0.0
        for t in q_toks:
            if t in d["tf"]:
                score += d["tf"][t] * idf.get(t, 1.0)
        if score > 0:
            snippet = d["text"]
            if len(snippet) > 800:
                snippet = snippet[:800] + "…"
            scored.append(PolicyHit(policy_id=policy_id, snippet=snippet, score=round(score, 3)))
    scored.sort(key=lambda h: h.score, reverse=True)
    return PolicyResult(query=query, hits=scored[:k])
