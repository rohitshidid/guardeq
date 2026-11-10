"""Small statistics helpers."""
from __future__ import annotations

import math


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion."""
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def mean_ci(values: list[float], z: float = 1.96) -> tuple[float, float, float]:
    """Mean with a normal-approximation 95% interval."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0
    m = sum(values) / n
    if n == 1:
        return m, m, m
    var = sum((v - m) ** 2 for v in values) / (n - 1)
    half = z * math.sqrt(var / n)
    return m, m - half, m + half
