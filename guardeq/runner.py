"""Run single trials and keep an append-only log of every one."""
from __future__ import annotations

import json
import sys
import time
import zlib
from pathlib import Path

from . import llm
from .agent import attack_succeeded, run_agent, task_done
from .attacks import build_attack, goal_for
from .config import Config
from .workspace import make_task, plant


def stable_seed(*parts) -> int:
    return zlib.crc32("/".join(map(str, parts)).encode()) % (2 ** 31)


class RunLog:
    """JSONL log of trials, keyed by trial id, so interrupted runs resume where they stopped."""

    def __init__(self, path: Path):
        self.path = path
        self.records: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.records[rec["id"]] = rec

    def __contains__(self, trial_id: str) -> bool:
        return trial_id in self.records

    def add(self, rec: dict) -> None:
        self.records[rec["id"]] = rec
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")

    def all(self) -> list[dict]:
        return list(self.records.values())


def run_trial(cfg: Config, *, trial_id: str, entry_point: str, guardrail: str, seed: int,
              attack_type: str | None = None, split: str = "tune", agent_model: str | None = None,
              payload: list[str] | None = None, goal: str | None = None, extra: dict | None = None) -> dict:
    """Run one normal task (attack_type None) or one attacked task, and return its record."""
    agent_model = agent_model or cfg.agent_model
    task = make_task(entry_point, seed, split)
    if attack_type:
        goal = goal or goal_for(seed)
        payload = payload or build_attack(attack_type, goal, seed, split)
        task = plant(task, payload, seed)
    out = run_agent(task, guardrail, agent_model=agent_model, judge_model=cfg.judge_model, seed=seed,
                    temperature=cfg.agent_temperature, max_steps=cfg.agent_max_steps)
    answer_blocked = any(c["flagged"] for c in out.checks if c["kind"] == "answer")
    benign_blocked = any(c["flagged"] for c in out.checks if c["kind"] != "inject")
    done = task_done(task, out.final)
    rec = {
        "id": trial_id,
        "kind": "attack" if attack_type else "normal",
        "entry_point": entry_point,
        "guardrail": guardrail,
        "attack_type": attack_type,
        "goal": goal if attack_type else None,
        "split": split,
        "seed": seed,
        "agent_model": agent_model,
        "judge_model": cfg.judge_model if guardrail == "judge" else None,
        "template": task.template,
        "question": task.question,
        "document": task.render(),
        "payload": payload if attack_type else None,
        "final": out.final,
        "tool_calls": out.tool_calls,
        "transcript": out.transcript,
        "checks": out.checks,
        "read_target": out.read_target,
        "steps": out.steps,
        "guard_latency": round(out.guard_latency, 5),
        "task_done": done,
        "attack_success": attack_succeeded(task, out.tool_calls, goal) if attack_type else None,
        "inject_blocked": any(c["flagged"] for c in out.checks if c["kind"] == "inject") if attack_type else None,
        "benign_blocked": benign_blocked,
        # A false block: a normal task failed and the guardrail had removed the content it needed.
        "false_block": (not attack_type) and (not done) and answer_blocked,
        "time": time.time(),
    }
    if extra:
        rec.update(extra)
    return rec


def run_many(cfg: Config, log: RunLog, specs: list[dict], label: str) -> None:
    """Run every spec not already in the log, printing progress."""
    todo = [s for s in specs if s["trial_id"] not in log]
    done_before = len(specs) - len(todo)
    if not todo:
        print(f"  {label}: all {len(specs)} trials already logged")
        return
    print(f"  {label}: {len(todo)} trials to run ({done_before} already logged)")
    start = time.time()
    for i, spec in enumerate(todo, 1):
        log.add(run_trial(cfg, **spec))
        if i % 5 == 0 or i == len(todo):
            rate = (time.time() - start) / i
            eta = rate * (len(todo) - i)
            sys.stdout.write(f"\r    {i}/{len(todo)}  {rate:.1f}s/trial  ETA {eta / 60:.1f} min   ")
            sys.stdout.flush()
    print(f"\n    cache hits so far: {llm.stats['cached']}/{llm.stats['calls']} model calls")
