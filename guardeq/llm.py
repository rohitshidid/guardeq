"""Model clients (Ollama, Groq) behind one cached `chat` call.

Every request is hashed and stored in a local SQLite cache together with its
measured latency, so any run can be replayed without new model calls. Set
GUARDEQ_OFFLINE=1 to forbid new calls entirely.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request

from .config import ROOT

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_URL.startswith("http"):
    OLLAMA_URL = "http://" + OLLAMA_URL
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

_conn: sqlite3.Connection | None = None
_no_think: set[str] = set()      # Ollama models that reject the `think` option
stats = {"calls": 0, "cached": 0}


class LLMError(RuntimeError):
    pass


def _cache() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = ROOT / "data" / "cache"
        path.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(path / "llm.sqlite")
        _conn.execute(
            "CREATE TABLE IF NOT EXISTS calls (key TEXT PRIMARY KEY, spec TEXT, request TEXT,"
            " response TEXT, latency REAL, created REAL)"
        )
    return _conn


def _post(url: str, body: dict, headers: dict, timeout: float = 600) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _ollama(model: str, messages: list, temperature: float, seed: int, max_tokens: int, json_mode: bool) -> str:
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": temperature, "seed": seed, "num_predict": max_tokens},
    }
    if json_mode:
        body["format"] = "json"
    if model not in _no_think:
        body["think"] = False
    try:
        out = _post(f"{OLLAMA_URL}/api/chat", body, {})
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        if "think" in detail.lower() and "think" in body:
            _no_think.add(model)
            return _ollama(model, messages, temperature, seed, max_tokens, json_mode)
        raise LLMError(f"Ollama error for {model}: {e.code} {detail[:300]}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"Cannot reach Ollama at {OLLAMA_URL} ({e.reason}). Is `ollama serve` running?") from e
    return out["message"]["content"]


def _groq(model: str, messages: list, temperature: float, seed: int, max_tokens: int, json_mode: bool) -> str:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise LLMError("GROQ_API_KEY is not set. Export a valid key or use the local judge (--judge local).")
    body = {"model": model, "messages": messages, "temperature": temperature, "seed": seed, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {key}", "User-Agent": "guardeq/0.1"}
    for attempt in range(8):
        try:
            out = _post(GROQ_URL, body, headers, timeout=120)
            return out["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            if e.code == 401:
                raise LLMError("Groq rejected GROQ_API_KEY (invalid key). Fix the key or use --judge local.") from e
            if e.code in (429, 500, 502, 503):
                wait = float(e.headers.get("retry-after") or min(60, 2 ** attempt))
                time.sleep(wait)
                continue
            raise LLMError(f"Groq error for {model}: {e.code} {detail[:300]}") from e
        except urllib.error.URLError as e:
            time.sleep(min(30, 2 ** attempt))
            last = e
    raise LLMError(f"Groq request for {model} kept failing (rate limit or network).")


def chat(spec: str, messages: list, *, temperature: float = 0.0, seed: int = 0, max_tokens: int = 256,
         json_mode: bool = False) -> tuple[str, float, bool]:
    """Return (text, latency_seconds, was_cached). Latency of a cached call is the original one."""
    backend, _, model = spec.partition(":")
    request = {"spec": spec, "messages": messages, "temperature": temperature, "seed": seed,
               "max_tokens": max_tokens, "json_mode": json_mode}
    blob = json.dumps(request, sort_keys=True)
    key = hashlib.sha256(blob.encode()).hexdigest()
    db = _cache()
    row = db.execute("SELECT response, latency FROM calls WHERE key = ?", (key,)).fetchone()
    stats["calls"] += 1
    if row:
        stats["cached"] += 1
        return row[0], row[1], True
    if os.environ.get("GUARDEQ_OFFLINE"):
        raise LLMError("GUARDEQ_OFFLINE is set and this call is not in the cache.")
    start = time.time()
    if backend == "ollama":
        text = _ollama(model, messages, temperature, seed, max_tokens, json_mode)
    elif backend == "groq":
        text = _groq(model, messages, temperature, seed, max_tokens, json_mode)
    else:
        raise LLMError(f"unknown backend in model spec {spec!r}")
    latency = time.time() - start
    db.execute("INSERT OR REPLACE INTO calls VALUES (?,?,?,?,?,?)", (key, spec, blob, text, latency, time.time()))
    db.commit()
    return text, latency, False


def extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a model reply; None if there is none."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        pass
                    break
        start = text.find("{", start + 1)
    return None
