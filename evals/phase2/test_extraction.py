"""Phase 2 program gate: extraction accuracy against hand labels.

This one makes REAL model calls, so it's opt-in — set ``RUN_LLM_EVALS=1`` to run it. It runs
the native backend over every labelled fixture and asserts, in code:

  (a) 100% of outputs are schema-valid (`Profile` / `Requirements`), and
  (b) field-level accuracy vs. the gold labels clears a threshold.

The gate is a program comparing to labels — the model never grades itself. Non-determinism is
tamped down with temperature 0, and the threshold leaves headroom for judgment-call fields
(e.g. seniority).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from zapply.extract import extract_profile, extract_requirements
from zapply.extract.models import Profile, Requirements

from scoring import score_model

FIXTURES = Path(__file__).parent / "fixtures"
THRESHOLD = 0.75
BACKEND = os.environ.get("EVAL_BACKEND", "native")

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_LLM_EVALS"),
    reason="Makes real LLM calls; set RUN_LLM_EVALS=1 to run.",
)


def _cases(kind: str):
    for txt in sorted(FIXTURES.glob(f"{kind}_*.txt")):
        labels = json.loads((FIXTURES / f"{txt.stem}.labels.json").read_text(encoding="utf-8"))
        yield txt.stem, txt.read_text(encoding="utf-8"), labels


def test_extraction_gate(capsys):
    schema_valid = 0
    total = 0
    score_total = 0.0
    field_count = 0
    per_fixture: list[tuple[str, float]] = []

    for name, text, labels in _cases("resume"):
        total += 1
        model = extract_profile(text, backend=BACKEND)
        if isinstance(model, Profile):
            schema_valid += 1
        result = score_model(model, labels)
        score_total += result.total
        field_count += result.count
        per_fixture.append((name, result.accuracy))

    for name, text, labels in _cases("jd"):
        total += 1
        model = extract_requirements(text, backend=BACKEND)
        if isinstance(model, Requirements):
            schema_valid += 1
        result = score_model(model, labels)
        score_total += result.total
        field_count += result.count
        per_fixture.append((name, result.accuracy))

    accuracy = score_total / field_count if field_count else 0.0

    with capsys.disabled():
        print(f"\n[Phase 2 gate | backend={BACKEND}]")
        for name, acc in per_fixture:
            print(f"  {name:12s} {acc:6.2%}")
        print(f"  schema-valid : {schema_valid}/{total}")
        print(f"  field acc    : {accuracy:.2%} over {field_count} fields (threshold {THRESHOLD:.0%})")

    # (a) 100% schema-valid
    assert schema_valid == total, f"only {schema_valid}/{total} outputs were schema-valid"
    # (b) field-level accuracy clears the bar
    assert accuracy >= THRESHOLD, f"accuracy {accuracy:.2%} < threshold {THRESHOLD:.0%}"
