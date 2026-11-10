"""Experiment configuration: the game's sets, default parameters, and run profiles."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ENTRY_POINTS = ("email", "web", "file", "tool")
GUARDRAILS = ("none", "classifier", "judge")
ATTACKS = ("direct", "hidden", "roleplay", "split")

ENTRY_LABELS = {"email": "Email", "web": "Web page", "file": "File", "tool": "Tool output"}
GUARD_LABELS = {"none": "None", "classifier": "Classifier", "judge": "LLM judge"}
ATTACK_LABELS = {"direct": "Direct override", "hidden": "Hidden", "roleplay": "Role-play", "split": "Split"}

# Run sizes per profile. "full" is the study described in the proposal.
PROFILES = {
    #            attack trials/setting, normal trials/setting, attacker runs/policy/budget, robustness trials/setting
    "smoke":   dict(n_attack=2,  n_normal=2,  n_eval=3,  n_robust=1),
    "reduced": dict(n_attack=15, n_normal=15, n_eval=30, n_robust=5),
    "full":    dict(n_attack=20, n_normal=20, n_eval=50, n_robust=8),
}


@dataclass(frozen=True)
class Config:
    profile: str = "smoke"

    # Models. Specs are "<backend>:<model>", backend in {ollama, groq}.
    agent_model: str = "ollama:gemma4"
    second_agent_model: str = "ollama:llama3.2"
    attacker_model: str = "ollama:gemma4"
    judge_backend: str = "local"                      # "local" or "groq"
    judge_local_model: str = "ollama:gemma4"
    judge_groq_model: str = "groq:llama-3.3-70b-versatile"

    # Game parameters.
    damage: dict = field(default_factory=lambda: {"email": 0.8, "web": 0.6, "file": 0.7, "tool": 1.0})   # V_t
    traffic: dict = field(default_factory=lambda: {"email": 1.0, "web": 1.5, "file": 0.8, "tool": 1.2})  # f_t
    lam: float = 0.5                                  # weight on false-block harm
    budget_fractions: tuple = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)   # of "LLM judge everywhere" cost
    eval_budget_fractions: tuple = (0.25, 0.5, 0.75)
    attacker_info: str = "full"                       # "full": policy + measured success rates; "policy": policy only

    # Run sizes (filled from the profile).
    n_attack: int = 2
    n_normal: int = 2
    n_eval: int = 3
    n_robust: int = 1

    agent_temperature: float = 0.7
    agent_max_steps: int = 6

    @property
    def judge_model(self) -> str:
        return self.judge_groq_model if self.judge_backend == "groq" else self.judge_local_model

    @property
    def data_dir(self) -> Path:
        return ROOT / "data" / self.profile

    @property
    def results_dir(self) -> Path:
        return ROOT / "results" / self.profile


def load_config(profile: str | None = None, **overrides) -> Config:
    """Build a Config from a profile name, environment variables, and explicit overrides."""
    profile = profile or os.environ.get("GUARDEQ_PROFILE", "smoke")
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; choose from {sorted(PROFILES)}")
    cfg = Config(profile=profile, **PROFILES[profile])
    env = {
        "judge_backend": os.environ.get("GUARDEQ_JUDGE"),
        "agent_model": os.environ.get("GUARDEQ_AGENT"),
        "attacker_model": os.environ.get("GUARDEQ_ATTACKER"),
        "judge_local_model": os.environ.get("GUARDEQ_JUDGE_LOCAL_MODEL"),
        "judge_groq_model": os.environ.get("GUARDEQ_JUDGE_GROQ_MODEL"),
    }
    updates = {k: v for k, v in env.items() if v}
    updates.update({k: v for k, v in overrides.items() if v is not None})
    if updates.get("judge_backend") not in (None, "local", "groq"):
        raise ValueError("judge backend must be 'local' or 'groq'")
    return replace(cfg, **updates)
