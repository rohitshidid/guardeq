"""Build the data file for the static replay demo in docs/. The demo makes no model calls."""
from __future__ import annotations

import json
import time

from .analysis import load
from .config import (ATTACK_LABELS, ATTACKS, ENTRY_LABELS, ENTRY_POINTS, GUARD_LABELS, GUARDRAILS, ROOT, Config)
from .runner import RunLog
from .solver import POLICY_LABELS, POLICY_NAMES

MAX_RUNS = 80


def _slim_policy(p: dict) -> dict:
    return {"policy": p["policy"], "worst_case": p["worst_case"], "cost": p["cost"],
            "false_block_harm": p["false_block_harm"], "damages": p["damages"],
            "best_responses": p["best_responses"]}


def _slim_run(r: dict) -> dict:
    return {
        "id": r["id"], "kind": r["kind"], "phase": r["id"].split("/")[0], "entry_point": r["entry_point"],
        "guardrail": r["guardrail"], "attack_type": r["attack_type"], "goal": r["goal"],
        "agent_model": r["agent_model"], "question": r["question"], "document": r["document"],
        "payload": r["payload"], "final": r["final"][:600], "tool_calls": r["tool_calls"],
        "transcript": [{"role": m["role"], "content": m["content"][:1500]} for m in r["transcript"]],
        "checks": r["checks"], "task_done": r["task_done"], "attack_success": r["attack_success"],
        "inject_blocked": r["inject_blocked"], "false_block": r["false_block"],
        "policy_name": r.get("policy_name"), "budget_fraction": r.get("budget_fraction"),
        "attacker": r.get("attacker"), "chose_best_response": r.get("chose_best_response"),
    }


def _pick_runs(records: list[dict]) -> list[dict]:
    """A varied sample: attacker-evaluation runs first, then payoff runs across settings."""
    evals = [r for r in records if r["id"].startswith("eval/")]
    attacks = [r for r in records if r["id"].startswith("payoff/") and r["kind"] == "attack"]
    normals = [r for r in records if r["id"].startswith("payoff/") and r["kind"] == "normal"]
    picked, seen = [], set()

    def take(pool, key, limit):
        for r in pool:
            k = key(r)
            if k in seen or len(picked) >= limit:
                continue
            seen.add(k)
            picked.append(r)

    take(evals, lambda r: ("e", r["policy_name"], r["budget_fraction"], r["attack_success"]), 30)
    take(attacks, lambda r: ("a", r["entry_point"], r["guardrail"], r["attack_type"], r["attack_success"]), 68)
    take(normals, lambda r: ("n", r["entry_point"], r["guardrail"], r["task_done"]), MAX_RUNS)
    return [_slim_run(r) for r in picked]


def build(cfg: Config):
    data = load(cfg)
    if not data["payoffs"] or not data["sweep"]:
        raise SystemExit(f"No results for profile {cfg.profile!r} yet. Run: python -m guardeq all --profile {cfg.profile}")
    log = RunLog(cfg.data_dir / "runs.jsonl")
    pay = data["payoffs"]
    payload = {
        "meta": {"profile": cfg.profile, "built": time.strftime("%Y-%m-%d %H:%M"), "trials": len(log.all()),
                 "agent_model": pay["agent_model"], "judge_model": pay["judge_model"],
                 "attacker_model": cfg.attacker_model, "attacker_info": cfg.attacker_info,
                 "n_attack": cfg.n_attack, "n_normal": cfg.n_normal, "n_eval": cfg.n_eval, "lam": cfg.lam},
        "sets": {"entries": ENTRY_POINTS, "guards": GUARDRAILS, "attacks": ATTACKS, "policies": POLICY_NAMES,
                 "entry_labels": ENTRY_LABELS, "guard_labels": GUARD_LABELS, "attack_labels": ATTACK_LABELS,
                 "policy_labels": POLICY_LABELS},
        "game": {"V": cfg.damage, "F": cfg.traffic},
        "payoffs": {k: pay[k] for k in ("P", "P_detail", "R", "R_detail", "K", "task_success", "checks")},
        "judge_everywhere_cost": data["sweep"]["judge_everywhere_cost"],
        "budget_to_match_judge": data["sweep"]["budget_to_match_judge"],
        "fine": {lam: [{"fraction": s["fraction"], "budget": s["budget"],
                        "policies": {n: _slim_policy(p) for n, p in s["policies"].items()}} for s in steps]
                 for lam, steps in data["sweep"]["fine"].items()},
        "eval": data["eval_summary"] or [],
        "robustness": data["robustness"],
        "runs": _pick_runs(log.all()),
    }
    out = ROOT / "docs" / "data.js"
    out.parent.mkdir(exist_ok=True)
    out.write_text("window.GUARDEQ = " + json.dumps(payload, separators=(",", ":")) + ";\n")
    return out
