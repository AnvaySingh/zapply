"""Spearman rank correlation — the measuring instrument for the Phase 3 gate.

Hand-rolled (no scipy) so the metric is legible and unit-tested. Spearman's rho is just
Pearson's correlation computed on the *ranks* of the two series, so it measures whether the
system orders the roles the same way my hand-ranking does — which is exactly the question for a
matcher: not "is the number right?" but "is the ordering right?".
"""

from __future__ import annotations

from collections.abc import Sequence


def rankdata(values: Sequence[float]) -> list[float]:
    """Average ranks (1-based), ties share the mean of their positions."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1  # positions i..j (0-based) → average 1-based rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def pearson(x: Sequence[float], y: Sequence[float]) -> float:
    n = len(x)
    if n == 0 or n != len(y):
        raise ValueError("x and y must be same non-zero length")
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    vx = sum((a - mx) ** 2 for a in x)
    vy = sum((b - my) ** 2 for b in y)
    if vx == 0 or vy == 0:
        return 0.0
    return cov / (vx**0.5 * vy**0.5)


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    return pearson(rankdata(x), rankdata(y))
