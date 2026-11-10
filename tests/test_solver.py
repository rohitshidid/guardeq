"""The solver must reproduce the worked example from the proposal before anything else is trusted."""
import unittest

from guardeq.solver import (all_policies, evaluate_policy, fixed_policy, greedy_policy, policy_cost,
                            random_policy, solve_general_sum, solve_sse)

# Two entry points, one attack type. No guardrail: every attack works. Judge: 80% are stopped, cost 1.
P = {t: {"none": {"x": 1.0}, "judge": {"x": 0.2}} for t in ("A", "B")}
R = {t: {"none": 0.0, "judge": 0.0} for t in ("A", "B")}
F = {"A": 1.0, "B": 1.0}
K = {"none": 0.0, "judge": 1.0}


class WorkedExample(unittest.TestCase):
    def test_fixed_policies_have_worst_case_one(self):
        for covered in ("A", "B"):
            c = {t: {"none": 0.0 if t == covered else 1.0, "judge": 1.0 if t == covered else 0.0} for t in ("A", "B")}
            self.assertAlmostEqual(evaluate_policy(c, P, R, {"A": 1, "B": 1}, F, K)["worst_case"], 1.0)

    def test_equal_values_mix_half_half(self):
        s = solve_sse(P, R, {"A": 1.0, "B": 1.0}, F, K, B=1.0)
        self.assertAlmostEqual(s["policy"]["A"]["judge"], 0.5, places=4)
        self.assertAlmostEqual(s["policy"]["B"]["judge"], 0.5, places=4)
        self.assertAlmostEqual(s["worst_case"], 0.6, places=4)

    def test_double_value_shifts_to_three_quarters(self):
        s = solve_sse(P, R, {"A": 2.0, "B": 1.0}, F, K, B=1.0)
        self.assertAlmostEqual(s["policy"]["A"]["judge"], 0.75, places=4)
        self.assertAlmostEqual(s["policy"]["B"]["judge"], 0.25, places=4)

    def test_budget_extremes(self):
        self.assertAlmostEqual(solve_sse(P, R, {"A": 1, "B": 1}, F, K, B=0.0)["worst_case"], 1.0, places=5)
        self.assertAlmostEqual(solve_sse(P, R, {"A": 1, "B": 1}, F, K, B=2.0)["worst_case"], 0.2, places=5)

    def test_more_budget_never_hurts(self):
        zs = [solve_sse(P, R, {"A": 2, "B": 1}, F, K, B=b / 10)["worst_case"] for b in range(0, 21)]
        self.assertTrue(all(a >= b - 1e-9 for a, b in zip(zs, zs[1:])))


class Structure(unittest.TestCase):
    def setUp(self):
        self.entries, self.guards, self.attacks = ("e", "w", "f"), ("none", "classifier", "judge"), ("a1", "a2")
        base = {"none": 0.9, "classifier": 0.5, "judge": 0.15}
        self.P = {t: {l: {a: min(1.0, base[l] * (1.0 + 0.2 * i - 0.3 * j)) for j, a in enumerate(self.attacks)}
                      for l in self.guards} for i, t in enumerate(self.entries)}
        self.R = {t: {"none": 0.0, "classifier": 0.02, "judge": 0.06} for t in self.entries}
        self.V = {"e": 1.0, "w": 0.5, "f": 0.8}
        self.F = {"e": 1.0, "w": 2.0, "f": 0.5}
        self.K = {"none": 0.0, "classifier": 0.05, "judge": 1.0}

    def test_policy_is_a_distribution_within_budget(self):
        for B in (0.0, 0.7, 1.9, 5.0):
            s = solve_sse(self.P, self.R, self.V, self.F, self.K, B, lam=0.5)
            for t in self.entries:
                self.assertAlmostEqual(sum(s["policy"][t].values()), 1.0, places=6)
                self.assertTrue(all(v >= -1e-9 for v in s["policy"][t].values()))
            self.assertLessEqual(s["cost"], B + 1e-6)

    def test_equilibrium_beats_every_baseline_within_budget(self):
        B, lam = 1.2, 0.5
        pol = all_policies(self.P, self.R, self.V, self.F, self.K, B, lam)
        for name in ("none", "random", "greedy"):
            self.assertLessEqual(pol["sse"]["objective"], pol[name]["objective"] + 1e-6, name)

    def test_baselines_respect_budget(self):
        B = 1.2
        for c in (random_policy(self.entries, self.guards, self.F, self.K, B),
                  greedy_policy(self.entries, self.guards, self.V, self.F, self.K, B)):
            self.assertLessEqual(policy_cost(c, self.F, self.K), B + 1e-9)
        self.assertAlmostEqual(policy_cost(fixed_policy(self.entries, self.guards, "none"), self.F, self.K), 0.0)

    def test_general_sum_matches_zero_sum_when_values_agree(self):
        for B in (0.5, 1.5):
            zs = solve_sse(self.P, self.R, self.V, self.F, self.K, B, lam=0.5)
            gs = solve_general_sum(self.P, self.R, self.V, self.V, self.F, self.K, B, lam=0.5)
            self.assertAlmostEqual(zs["objective"], gs["objective"], places=4)

    def test_general_sum_attacker_target_is_a_best_response(self):
        U = {"e": 0.2, "w": 1.0, "f": 0.4}
        gs = solve_general_sum(self.P, self.R, self.V, U, self.F, self.K, 1.0, lam=0.5)
        ev = evaluate_policy(gs["policy"], self.P, self.R, U, self.F, self.K)
        self.assertIn(tuple(gs["attacker_target"]), [tuple(b) for b in ev["best_responses"]])


if __name__ == "__main__":
    unittest.main()
