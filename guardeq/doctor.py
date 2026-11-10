"""Environment checks: is everything this project needs actually available?"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from . import llm
from .config import PROFILES, Config
from .runner import RunLog


def _ollama_models() -> list[str] | None:
    try:
        with urllib.request.urlopen(f"{llm.OLLAMA_URL}/api/tags", timeout=5) as r:
            return [m["name"] for m in json.load(r).get("models", [])]
    except (urllib.error.URLError, OSError):
        return None


def _groq_ok() -> tuple[bool, str]:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return False, "GROQ_API_KEY is not set"
    req = urllib.request.Request("https://api.groq.com/openai/v1/models",
                                 headers={"Authorization": f"Bearer {key}", "User-Agent": "guardeq/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            names = [m["id"] for m in json.load(r).get("data", [])]
        return True, f"key accepted, {len(names)} models visible"
    except urllib.error.HTTPError as e:
        return False, "key rejected by Groq (invalid or expired)" if e.code == 401 else f"HTTP {e.code}"
    except (urllib.error.URLError, OSError) as e:
        return False, f"cannot reach Groq ({e})"


def run(cfg: Config) -> int:
    ok = True

    def line(good: bool, text: str, required: bool = True):
        nonlocal ok
        print(f"  [{'ok' if good else ('FAIL' if required else 'warn')}] {text}")
        ok = ok and (good or not required)

    print("GuardEQ environment check")
    for mod in ("numpy", "scipy", "matplotlib"):
        try:
            __import__(mod)
            line(True, f"python package {mod}")
        except ImportError:
            line(False, f"python package {mod} is missing  ->  pip install {mod}")
    models = _ollama_models()
    line(models is not None, f"Ollama reachable at {llm.OLLAMA_URL}" if models is not None
         else f"Ollama not reachable at {llm.OLLAMA_URL}  ->  start it with `ollama serve`")
    needed = {cfg.agent_model, cfg.second_agent_model, cfg.attacker_model}
    if cfg.judge_backend == "local":
        needed.add(cfg.judge_local_model)
    for spec in sorted(s for s in needed if s.startswith("ollama:")):
        name = spec.split(":", 1)[1]
        have = models is not None and any(m == name or m.split(":")[0] == name for m in models)
        line(have, f"Ollama model {name}" if have else f"Ollama model {name} missing  ->  ollama pull {name}")
    good, why = _groq_ok()
    line(good, f"Groq judge: {why}", required=cfg.judge_backend == "groq")
    print(f"  judge backend in use: {cfg.judge_backend} ({cfg.judge_model})")
    print("All required checks passed." if ok else "Some required checks failed; see above.")
    return 0 if ok else 1


def status(cfg: Config) -> int:
    for profile in PROFILES:
        path = cfg.data_dir.parent / profile / "runs.jsonl"
        if not path.exists():
            print(f"  {profile:8s} no runs yet")
            continue
        recs = RunLog(path).all()
        kinds = {}
        for r in recs:
            phase = r["id"].split("/")[0]
            kinds[phase] = kinds.get(phase, 0) + 1
        print(f"  {profile:8s} {len(recs)} trials logged  " + "  ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    return 0
