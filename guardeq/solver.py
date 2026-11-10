"""The Stackelberg security game: equilibrium solver, baseline policies, and policy evaluation.

Notation follows the proposal. A policy `c` maps entry point -> guardrail -> probability.
  P[t][l][a]  chance attack type a succeeds at entry point t under guardrail l
  R[t][l]     chance a normal task at t fails because guardrail l blocked safe content
  V[t]        damage value of entry point t          F[t]  traffic weight (checks per task)
  K[l]        cost of one check with guardrail l     B     average cost budget per task
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import linprog

TOL = 1e-7
TIE_EPS = 1e-6          # tiny cost penalty so the solver prefers the cheapest optimal policy


def _sets(P):
    entries = list(P)
    guards = list(P[entries[0]])
    attacks = list(P[entries[0]][guards[0]])
    return entries, guards, attacks


def _to_policy(x, entries, guards):
    return {t: {l: float(max(0.0, x[i * len(guards) + j])) for j, l in enumerate(guards)}
            for i, t in enumerate(entries)}


def policy_cost(c, F, K) -> float:
    return sum(F[t] * sum(c[t][l] * K[l] for l in c[t]) for t in c)


def false_block_harm(c, R, F) -> float:
    return sum(F[t] * sum(c[t][l] * R[t][l] for l in c[t]) for t in c)


def evaluate_policy(c, P, R, V, F, K, lam: float = 0.0) -> dict:
    """Predicted outcome of a policy against a best-responding attacker."""
    entries, guards, attacks = _sets(P)
    damages = {t: {a: V[t] * sum(c[t][l] * P[t][l][a] for l in guards) for a in attacks} for t in entries}
    z = max(d for row in damages.values() for d in row.values())
    best = [(t, a) for t in entries for a in attacks if damages[t][a] >= z - TOL]
    harm = false_block_harm(c, R, F)
    return {"worst_case": z, "best_responses": best, "damages": damages, "cost": policy_cost(c, F, K),
            "false_block_harm": harm, "objective": z + lam * harm}


def solve_sse(P, R, V, F, K, B: float, lam: float = 0.0) -> dict:
    """Strong Stackelberg equilibrium of the zero-sum-in-damage game, by one linear program.

        min  z + lam * sum_t F_t sum_l c_tl R_tl
        s.t. z >= V_t sum_l c_tl P_tla        for every t, a
             sum_l c_tl = 1                   for every t
             sum_t F_t sum_l c_tl K_l <= B,   c >= 0
    """
    entries, guards, attacks = _sets(P)
    nT, nL = len(entries), len(guards)
    n = nT * nL + 1                                   # the last variable is z
    idx = lambda i, j: i * nL + j

    obj = np.zeros(n)
    obj[-1] = 1.0
    for i, t in enumerate(entries):
        for j, l in enumerate(guards):
            obj[idx(i, j)] = lam * F[t] * R[t][l] + TIE_EPS * F[t] * K[l]

    A_ub, b_ub = [], []
    for i, t in enumerate(entries):
        for a in attacks:
            row = np.zeros(n)
            for j, l in enumerate(guards):
                row[idx(i, j)] = V[t] * P[t][l][a]
            row[-1] = -1.0
            A_ub.append(row)
            b_ub.append(0.0)
    row = np.zeros(n)
    for i, t in enumerate(entries):
        for j, l in enumerate(guards):
            row[idx(i, j)] = F[t] * K[l]
    A_ub.append(row)
    b_ub.append(B)

    A_eq = np.zeros((nT, n))
    for i in range(nT):
        A_eq[i, i * nL:(i + 1) * nL] = 1.0

    res = linprog(obj, A_ub=np.array(A_ub), b_ub=b_ub, A_eq=A_eq, b_eq=np.ones(nT),
                  bounds=[(0, 1)] * (n - 1) + [(0, None)], method="highs")
    if not res.success:
        raise RuntimeError(f"LP failed: {res.message}")
    c = _to_policy(res.x, entries, guards)
    out = evaluate_policy(c, P, R, V, F, K, lam)
    out["policy"] = c
    return out


def solve_general_sum(P, R, V, U, F, K, B: float, lam: float = 0.0) -> dict:
    """Strong Stackelberg equilibrium when the attacker values entry points by U instead of V.

    Multiple-LP method (Conitzer and Sandholm, 2006): for each attacker pure strategy (t*, a*),
    find the defender's best policy that makes it a best response, then keep the best of those.
    """
    entries, guards, attacks = _sets(P)
    nT, nL = len(entries), len(guards)
    n = nT * nL
    idx = lambda i, j: i * nL + j
    budget = np.zeros(n)
    fp = np.zeros(n)
    for i, t in enumerate(entries):
        for j, l in enumerate(guards):
            budget[idx(i, j)] = F[t] * K[l]
            fp[idx(i, j)] = lam * F[t] * R[t][l] + TIE_EPS * F[t] * K[l]
    A_eq = np.zeros((nT, n))
    for i in range(nT):
        A_eq[i, i * nL:(i + 1) * nL] = 1.0

    best = None
    for i_s, t_s in enumerate(entries):
        for a_s in attacks:
            obj = fp.copy()
            for j, l in enumerate(guards):
                obj[idx(i_s, j)] += V[t_s] * P[t_s][l][a_s]
            A_ub, b_ub = [budget], [B]
            for i, t in enumerate(entries):
                for a in attacks:
                    if (t, a) == (t_s, a_s):
                        continue
                    row = np.zeros(n)                 # U_t dmg(t,a) - U_t* dmg(t*,a*) <= 0
                    for j, l in enumerate(guards):
                        row[idx(i, j)] += U[t] * P[t][l][a]
                        row[idx(i_s, j)] -= U[t_s] * P[t_s][l][a_s]
                    A_ub.append(row)
                    b_ub.append(0.0)
            res = linprog(obj, A_ub=np.array(A_ub), b_ub=b_ub, A_eq=A_eq, b_eq=np.ones(nT),
                          bounds=[(0, 1)] * n, method="highs")
            if res.success and (best is None or res.fun < best[0] - 1e-12):
                best = (res.fun, res.x, (t_s, a_s))
    if best is None:
        raise RuntimeError("no feasible attacker target")
    c = _to_policy(best[1], entries, guards)
    t_s, a_s = best[2]
    damage = V[t_s] * sum(c[t_s][l] * P[t_s][l][a_s] for l in guards)
    harm = false_block_harm(c, R, F)
    return {"policy": c, "attacker_target": best[2], "defender_damage": damage, "false_block_harm": harm,
            "objective": damage + lam * harm, "cost": policy_cost(c, F, K)}


# --- baselines ------------------------------------------------------------------------

def fixed_policy(entries, guards, level: str) -> dict:
    return {t: {l: 1.0 if l == level else 0.0 for l in guards} for t in entries}


def random_policy(entries, guards, F, K, B: float, strong: str = "judge") -> dict:
    """Same mix at every entry point: the strong guardrail with probability q, nothing otherwise."""
    full = sum(F[t] * K[strong] for t in entries)
    q = 1.0 if full <= 0 else min(1.0, max(0.0, B / full))
    return {t: {l: q if l == strong else (1.0 - q if l == "none" else 0.0) for l in guards} for t in entries}


def greedy_policy(entries, guards, V, F, K, B: float, strong: str = "judge") -> dict:
    """Spend the budget on the strong guardrail at the most valuable entry points first."""
    c = fixed_policy(entries, guards, "none")
    left = B
    for t in sorted(entries, key=lambda e: -V[e]):
        need = F[t] * K[strong]
        q = 1.0 if need <= 0 else min(1.0, max(0.0, left / need))
        c[t] = {l: q if l == strong else (1.0 - q if l == "none" else 0.0) for l in guards}
        left -= q * need
    return c


POLICY_NAMES = ("sse", "none", "classifier", "judge", "random", "greedy")
POLICY_LABELS = {"sse": "GuardEQ (equilibrium)", "none": "No guardrails", "classifier": "Classifier everywhere",
                 "judge": "LLM judge everywhere", "random": "Random, same budget", "greedy": "Greedy by value"}


def all_policies(P, R, V, F, K, B: float, lam: float) -> dict:
    """The equilibrium policy and the five baselines at budget B, each with its predicted outcome."""
    entries, guards, _ = _sets(P)
    policies = {
        "sse": solve_sse(P, R, V, F, K, B, lam)["policy"],
        "none": fixed_policy(entries, guards, "none"),
        "classifier": fixed_policy(entries, guards, "classifier"),
        "judge": fixed_policy(entries, guards, "judge"),
        "random": random_policy(entries, guards, F, K, B),
        "greedy": greedy_policy(entries, guards, V, F, K, B),
    }
    return {name: {"policy": c, **evaluate_policy(c, P, R, V, F, K, lam)} for name, c in policies.items()}


def judge_everywhere_cost(P, F, K) -> float:
    entries, _, _ = _sets(P)
    return sum(F[t] * K["judge"] for t in entries)
