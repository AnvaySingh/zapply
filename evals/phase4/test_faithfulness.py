"""Phase 4 program gate (offline, deterministic): the faithfulness checker itself.

This proves the *gate* works before it's pointed at live model output: a hand-written faithful
draft must pass clean, and a hand-written unfaithful draft must be caught with exactly the
violations we planted. No LLM, no network — this is the part the whole phase hinges on.
"""

from __future__ import annotations

import json
from pathlib import Path

from apply_copilot.draft import answer_addresses_question, check_draft
from apply_copilot.draft.models import DraftPacket
from apply_copilot.extract.models import Profile, Requirements

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _profile_and_reqs():
    return (
        Profile.model_validate(_load("profile.json")),
        Requirements.model_validate(_load("requirements.json")),
    )


def test_faithful_draft_passes_clean():
    profile, reqs = _profile_and_reqs()
    packet = DraftPacket.model_validate(_load("draft_faithful.json"))
    report = check_draft(packet, profile, reqs)
    assert report.is_faithful, [v.__dict__ for v in report.violations]
    assert report.bullets_checked == 3 and report.answers_checked == 2


def test_unfaithful_draft_is_caught_with_expected_violations():
    profile, reqs = _profile_and_reqs()
    packet = DraftPacket.model_validate(_load("draft_unfaithful.json"))
    report = check_draft(packet, profile, reqs)

    assert not report.is_faithful
    kinds = {v.kind for v in report.violations}
    # Every violation type we planted must be detected.
    assert kinds == {"tag_company", "tag_skill", "claimed_missing_skill", "claimed_unworked_company"}
    # 4 in the first bullet (Google tag, Rust tag, Rust in text, Stripe in text) + 2 in the answer.
    assert len(report.violations) == 6


def test_relevance_floor_catches_non_answers():
    q = "Describe your most relevant experience for this position."
    good = "At Acme Corp I designed payment APIs and led our Kubernetes migration for years."
    assert answer_addresses_question(q, good)  # substantive → passes the floor
    assert not answer_addresses_question(q, "Yes.")  # one-word non-answer
    assert not answer_addresses_question(q, "I don't know")  # stock non-answer
    assert not answer_addresses_question(q, "Great fit.")  # too short
    # NOTE: the floor deliberately can't judge topicality — an on-topic-looking but wrong answer
    # is the LLM judge's job. That split is the point.
