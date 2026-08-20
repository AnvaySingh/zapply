"""Offline, deterministic tests of the Spearman instrument — no embeddings, no network."""

from __future__ import annotations

from pytest import approx

from rank_metrics import pearson, rankdata, spearman


def test_rankdata_with_ties():
    assert rankdata([10, 20, 30]) == [1.0, 2.0, 3.0]
    # two-way tie at the top averages ranks 2 and 3 → 2.5
    assert rankdata([10, 30, 30]) == [1.0, 2.5, 2.5]


def test_perfect_and_inverse_correlation():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == approx(1.0)
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == approx(-1.0)


def test_monotonic_but_nonlinear_is_still_one():
    # Spearman only cares about order, so a nonlinear-but-monotonic map is perfect.
    assert spearman([1, 2, 3, 4], [1, 4, 9, 16]) == approx(1.0)


def test_constant_series_is_zero():
    assert pearson([1, 1, 1], [1, 2, 3]) == 0.0
