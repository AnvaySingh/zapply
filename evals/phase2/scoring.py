"""Field-level scoring: compare extracted models against hand-written gold labels.

This is the *measuring instrument* for the Phase 2 gate. It is pure, deterministic code — the
model's output is judged by comparison to labels I wrote by hand, never by the model grading
itself. Each labelled field gets a score in [0, 1]; overall accuracy is their mean.

Label kinds:
* ``scalar``  — normalised exact match.
* ``contains``— gold appears within prediction (or vice-versa), normalised.
* ``enum``    — normalised exact match on an enum value.
* ``numeric`` — within a tolerance.
* ``list``    — recall: fraction of gold items found in the prediction (normalised).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


def _norm(value: Any) -> str:
    if value is None:
        return ""
    text = str(getattr(value, "value", value))  # unwrap enums
    text = text.casefold().strip()
    return re.sub(r"\s+", " ", text)


def _norm_set(items: Any) -> set[str]:
    if not items:
        return set()
    return {_norm(i) for i in items if _norm(i)}


# Derived predicted values that aren't plain attributes.
_DERIVED = {
    "companies": lambda m: [e.company for e in getattr(m, "experiences", [])],
    "titles": lambda m: [e.title for e in getattr(m, "experiences", [])],
    "institutions": lambda m: [e.institution for e in getattr(m, "education", [])],
}


def resolve(model: Any, key: str) -> Any:
    if key in _DERIVED:
        return _DERIVED[key](model)
    return getattr(model, key, None)


def score_field(predicted: Any, spec: dict[str, Any]) -> float:
    kind = spec["kind"]
    gold = spec["value"]

    if kind == "scalar":
        return 1.0 if _norm(predicted) == _norm(gold) else 0.0
    if kind == "contains":
        p, g = _norm(predicted), _norm(gold)
        return 1.0 if p and g and (g in p or p in g) else 0.0
    if kind == "enum":
        return 1.0 if _norm(predicted) == _norm(gold) else 0.0
    if kind == "numeric":
        if predicted is None:
            return 0.0
        try:
            return 1.0 if abs(float(predicted) - float(gold)) <= spec.get("tol", 0) else 0.0
        except (TypeError, ValueError):
            return 0.0
    if kind == "list":
        gold_set = _norm_set(gold)
        if not gold_set:
            return 1.0
        found = gold_set & _norm_set(predicted)
        return len(found) / len(gold_set)
    raise ValueError(f"unknown label kind: {kind!r}")


@dataclass
class ScoreResult:
    total: float
    count: int

    @property
    def accuracy(self) -> float:
        return self.total / self.count if self.count else 0.0


def score_model(model: Any, labels: dict[str, Any]) -> ScoreResult:
    """Score one extracted model against its labelled fields."""
    total = 0.0
    count = 0
    for key, spec in labels["fields"].items():
        total += score_field(resolve(model, key), spec)
        count += 1
    return ScoreResult(total=total, count=count)
