"""Phase 4 live gate: draft for real, then let the PROGRAM decide faithfulness.

Opt-in (`RUN_LLM_EVALS=1`) because it calls the model. The role deliberately requires skills the
candidate lacks (Rust, Kafka) — the exact bait for hallucination. The hard assertions are all
programmatic:

  * `check_draft` finds **zero** violations (the real gate), and
  * every screening answer clears the relevance floor.

The LLM judge runs too, but only as a printed signal — the model never decides the phase.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from apply_copilot.draft import answer_addresses_question, check_draft, draft
from apply_copilot.extract.models import Profile, Requirements

from judge import judge_claims

FIXTURES = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_LLM_EVALS"),
    reason="Makes real LLM calls; set RUN_LLM_EVALS=1 to run.",
)


def test_live_draft_is_faithful(capsys):
    profile = Profile.model_validate(json.loads((FIXTURES / "profile.json").read_text()))
    reqs = Requirements.model_validate(json.loads((FIXTURES / "requirements.json").read_text()))

    # 1) Draft for real, then let the PROGRAM decide.
    packet = draft(profile, reqs)
    report = check_draft(packet, profile, reqs)
    relevance = [(a.question, answer_addresses_question(a.question, a.answer)) for a in packet.answers]

    # 2) The judge is a SIGNAL — if it errors, it must not break the gate.
    judge_line = "judge signal            : (unavailable)"
    try:
        claims = [b.text for b in packet.bullets] + [a.answer for a in packet.answers]
        judged = judge_claims(profile, claims)
        supported = sum(1 for j in judged.judgments if j.supported)
        rate = supported / len(judged.judgments) if judged.judgments else 1.0
        judge_line = f"judge signal            : {supported}/{len(judged.judgments)} supported ({rate:.0%})"
    except Exception as exc:  # noqa: BLE001 - signal only
        judge_line = f"judge signal            : (unavailable: {type(exc).__name__})"

    with capsys.disabled():
        print("\n[Phase 4 live gate]")
        for b in packet.bullets:
            print(f"  • {b.text}   [company={b.company}, skills={b.skills_used}]")
        for a in packet.answers:
            print(f"  Q: {a.question}\n  A: {a.answer}")
        print(f"  programmatic violations : {len(report.violations)} -> {[v.kind for v in report.violations]}")
        print(f"  relevance floor         : {sum(1 for _, ok in relevance if ok)}/{len(relevance)} answers")
        print(f"  {judge_line}")

    # HARD gate: the program, not the model.
    assert report.is_faithful, [v.__dict__ for v in report.violations]
    assert all(ok for _, ok in relevance), "an answer failed the relevance floor"
