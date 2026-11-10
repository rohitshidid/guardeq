"""Figures and tables built from saved results. No model calls happen here."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .config import ATTACK_LABELS, ATTACKS, ENTRY_LABELS, ENTRY_POINTS, GUARD_LABELS, GUARDRAILS, Config  # noqa: E402
from .solver import POLICY_LABELS, POLICY_NAMES  # noqa: E402

COLORS = {"sse": "#57068C", "none": "#9A9AA5", "classifier": "#D98A0B", "judge": "#0B7A75",
          "random": "#3B7DD8", "greedy": "#C1121F"}
GUARD_COLORS = {"none": "#D9D2E4", "classifier": "#D98A0B", "judge": "#0B7A75"}

plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#EBE5F3", "figure.dpi": 130})


def load(cfg: Config) -> dict:
    res = cfg.results_dir
    out = {}
    for name in ("payoffs", "sweep", "eval_summary", "robustness", "payoffs_second_model"):
        path = res / f"{name}.json"
        out[name] = json.loads(path.read_text()) if path.exists() else None
    return out


def fig_security_cost(data: dict, path: Path) -> None:
    fine = data["sweep"]["fine"]
    lam = "0.5" if "0.5" in fine else next(iter(fine))
    steps = fine[lam]
    xs = [s["fraction"] for s in steps]
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    for name in ("random", "greedy", "sse"):
        ax.plot(xs, [s["policies"][name]["worst_case"] for s in steps], color=COLORS[name],
                lw=2.4 if name == "sse" else 1.6, label=POLICY_LABELS[name])
    full = data["sweep"]["judge_everywhere_cost"] or 1.0
    for name in ("none", "classifier", "judge"):
        p = steps[0]["policies"][name]
        ax.scatter([p["cost"] / full], [p["worst_case"]], color=COLORS[name], zorder=5, s=46,
                   label=POLICY_LABELS[name])
    ax.set_xlabel("Budget (fraction of 'LLM judge everywhere' cost)")
    ax.set_ylabel("Predicted worst-case damage")
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def fig_payoffs(data: dict, path: Path) -> None:
    P = data["payoffs"]["P"]
    fig, axes = plt.subplots(1, 3, figsize=(9.2, 3.1), sharey=True)
    for ax, l in zip(axes, GUARDRAILS):
        grid = [[P[t][l][a] for a in ATTACKS] for t in ENTRY_POINTS]
        im = ax.imshow(grid, vmin=0, vmax=1, cmap="Purples", aspect="auto")
        ax.set_title(GUARD_LABELS[l], fontsize=10)
        ax.set_xticks(range(len(ATTACKS)), [ATTACK_LABELS[a] for a in ATTACKS], rotation=30, ha="right", fontsize=8)
        ax.set_yticks(range(len(ENTRY_POINTS)), [ENTRY_LABELS[t] for t in ENTRY_POINTS], fontsize=9)
        ax.grid(False)
        for i, row in enumerate(grid):
            for j, v in enumerate(row):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8,
                        color="white" if v > 0.55 else "#1C1B22")
    fig.colorbar(im, ax=axes, shrink=0.8, label="Attack success rate")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def fig_policy_mix(data: dict, path: Path) -> None:
    sweep = data["sweep"]["sweep"]
    fig, axes = plt.subplots(1, len(ENTRY_POINTS), figsize=(9.2, 2.9), sharey=True)
    for ax, t in zip(axes, ENTRY_POINTS):
        bottom = [0.0] * len(sweep)
        for l in GUARDRAILS:
            vals = [s["policies"]["sse"]["policy"][t][l] for s in sweep]
            ax.bar(range(len(sweep)), vals, bottom=bottom, color=GUARD_COLORS[l], label=GUARD_LABELS[l], width=0.75)
            bottom = [b + v for b, v in zip(bottom, vals)]
        ax.set_title(ENTRY_LABELS[t], fontsize=10)
        ax.set_xticks(range(len(sweep)), [f"{s['fraction']:.1f}" for s in sweep], fontsize=8)
        ax.set_xlabel("Budget fraction", fontsize=8)
        ax.grid(False)
    axes[0].set_ylabel("Probability")
    axes[-1].legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def fig_eval(data: dict, path: Path) -> None:
    rows = data["eval_summary"]
    fracs = sorted({r["budget_fraction"] for r in rows})
    fig, axes = plt.subplots(1, len(fracs), figsize=(3.3 * len(fracs), 3.5), sharey=True, squeeze=False)
    for ax, f in zip(axes[0], fracs):
        cell = {r["policy"]: r for r in rows if r["budget_fraction"] == f}
        names = [n for n in POLICY_NAMES if n in cell]
        vals = [cell[n]["realized_damage"] for n in names]
        err = [[max(0.0, cell[n]["realized_damage"] - cell[n]["realized_damage_ci"][0]) for n in names],
               [max(0.0, cell[n]["realized_damage_ci"][1] - cell[n]["realized_damage"]) for n in names]]
        ax.bar(range(len(names)), vals, yerr=err, color=[COLORS[n] for n in names], capsize=3, width=0.7)
        ax.scatter(range(len(names)), [cell[n]["predicted_worst_case"] for n in names], marker="_", s=260,
                   color="#1C1B22", zorder=5, label="Predicted worst case")
        ax.set_title(f"Budget {f:.2f}", fontsize=10)
        ax.set_xticks(range(len(names)), [POLICY_LABELS[n].split(" (")[0].replace(" everywhere", "\neverywhere")
                                          .replace(", same", ",\nsame").replace(" by", "\nby") for n in names],
                      fontsize=7)
    axes[0][0].set_ylabel("Damage against the LLM attacker")
    axes[0][-1].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def fig_attacker(data: dict, path: Path) -> None:
    rows = data["eval_summary"]
    names = [n for n in POLICY_NAMES if any(r["policy"] == n for r in rows)]
    rate = []
    for n in names:
        cell = [r for r in rows if r["policy"] == n]
        total = sum(r["n"] for r in cell)
        rate.append(sum(r["best_response_rate"] * r["n"] for r in cell) / total if total else 0.0)
    fig, ax = plt.subplots(figsize=(6.0, 3.3))
    ax.bar(range(len(names)), rate, color=[COLORS[n] for n in names], width=0.65)
    ax.set_xticks(range(len(names)), [POLICY_LABELS[n].split(" (")[0] for n in names], rotation=20, ha="right",
                  fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Share of runs where the attacker\npicked a predicted best response")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def fig_sensitivity(data: dict, path: Path) -> None:
    s = data["robustness"]["sensitivity"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(8.6, 3.2))
    a.plot([r["lam"] for r in s["lambda"]], [r["worst_case"] for r in s["lambda"]], "o-", color=COLORS["sse"],
           label="Worst-case damage")
    a.plot([r["lam"] for r in s["lambda"]], [r["false_block_harm"] for r in s["lambda"]], "s--",
           color=COLORS["classifier"], label="False-block harm")
    a.set_xlabel("lambda (weight on false blocks)")
    a.legend(frameon=False, fontsize=8)
    labels = [f"{ENTRY_LABELS[r['entry_point']]}\nx{r['scale']}" for r in s["damage"]]
    b.bar(range(len(labels)), [r["worst_case"] for r in s["damage"]], color=COLORS["sse"], width=0.7)
    b.axhline(s["base_worst_case"], color="#1C1B22", lw=1, ls=":", label="Baseline")
    b.set_xticks(range(len(labels)), labels, fontsize=7)
    b.set_ylabel("Worst-case damage")
    b.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def make_figures(cfg: Config) -> list[Path]:
    data = load(cfg)
    figs = cfg.results_dir / "figures"
    figs.mkdir(parents=True, exist_ok=True)
    made = []
    plan = [("payoffs", "payoffs.png", fig_payoffs), ("sweep", "security_cost.png", fig_security_cost),
            ("sweep", "policy_mix.png", fig_policy_mix), ("eval_summary", "eval_damage.png", fig_eval),
            ("eval_summary", "attacker_choice.png", fig_attacker), ("robustness", "sensitivity.png", fig_sensitivity)]
    for need, name, fn in plan:
        if data.get(need):
            fn(data, figs / name)
            made.append(figs / name)
    return made
