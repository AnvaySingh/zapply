"""Phase 5 program gate (offline, deterministic): contracts + the maker-checker lock.

Uses stub agents (no LLM, no network) so the orchestration logic is tested in isolation. The
assertions are the phase's real gate:

* every stage hands off well-formed data, and a stage that emits bad data raises `PipelineError`;
* an application that fails the faithfulness gate is `blocked` and **cannot** be approved;
* a packet **cannot** be built unless the application is `approved` — the human gate is a program.
"""

from __future__ import annotations

import pytest

from zapply.draft.faithfulness import FaithfulnessReport, Violation
from zapply.draft.models import DraftPacket, ScreeningAnswer, TailoredBullet
from zapply.extract.models import Profile, Requirements, Seniority
from zapply.ingest.models import JobPosting
from zapply.match.matcher import MatchResult
from zapply.orchestrate import (
    ApplicationStatus,
    Pipeline,
    PipelineConfig,
    PipelineError,
    ReviewError,
    approve,
)
from zapply.packet import NotApprovedError, build_approved_packets, build_packet

POISON_ID = "2"  # the posting whose stub draft is unfaithful


def _posting(source_id: str, title: str) -> JobPosting:
    return JobPosting(source="greenhouse", source_id=source_id, company="Acme", title=title,
                      description=f"{title} role at Acme.")


def _profile() -> Profile:
    return Profile(name="Jane", seniority=Seniority.senior, skills=["Python", "Go"])


# -- stub agents ---------------------------------------------------------------


class StubPrefilter:
    def run(self, profile, postings):
        return [(p, 1.0 - i * 0.1) for i, p in enumerate(postings)]


class StubExtract:
    def run(self, posting):
        return Requirements(title=posting.title, company="Acme", required_skills=["Python"])


class StubExtractEmptyTitle:
    def run(self, posting):
        return Requirements(title="", company="Acme")  # violates the handoff contract


class StubMatch:
    def run(self, profile, requirements):
        return MatchResult(score=72, similarity=0.72, rationale="stub match")


class StubDraft:
    def run(self, profile, requirements):
        packet = DraftPacket(
            bullets=[TailoredBullet(text="Built payment APIs in Python at Acme.", company="Acme", skills_used=["Python"])],
            answers=[ScreeningAnswer(question="Why?", answer="Seven years of Python at Acme, a strong match here.")],
        )
        # The poison posting produces an unfaithful draft → a real violation report.
        if requirements.title.endswith("(poison)"):
            report = FaithfulnessReport(
                violations=[Violation("claimed_missing_skill", "bullet[0]", "claims Rust")],
                bullets_checked=1, answers_checked=1,
            )
        else:
            report = FaithfulnessReport(bullets_checked=1, answers_checked=1)
        return packet, report


def _pipeline() -> Pipeline:
    return Pipeline(StubPrefilter(), StubExtract(), StubMatch(), StubDraft())


def _postings():
    return [_posting("1", "Backend Engineer"), _posting(POISON_ID, "Data Engineer (poison)"),
            _posting("3", "Platform Engineer")]


# -- tests ---------------------------------------------------------------------


def test_pipeline_runs_and_marks_statuses():
    apps = _pipeline().run(_profile(), _postings(), PipelineConfig(top_k=3))
    assert len(apps) == 3
    by_id = {a.posting.source_id: a for a in apps}

    # Contracts: every app carries valid stage outputs.
    for a in apps:
        assert a.requirements.title
        assert 0 <= a.match.score <= 100
        assert a.draft is not None

    # The poison one is blocked; the others await the human.
    assert by_id[POISON_ID].status == ApplicationStatus.blocked
    assert by_id["1"].status == ApplicationStatus.pending_review


def test_bad_handoff_raises_pipeline_error():
    pipe = Pipeline(StubPrefilter(), StubExtractEmptyTitle(), StubMatch(), StubDraft())
    with pytest.raises(PipelineError):
        pipe.run(_profile(), _postings(), PipelineConfig(top_k=1))


def test_cannot_approve_a_blocked_application():
    apps = _pipeline().run(_profile(), _postings(), PipelineConfig(top_k=3))
    blocked = next(a for a in apps if a.status == ApplicationStatus.blocked)
    with pytest.raises(ReviewError):
        approve(blocked)


def test_packet_requires_approval():
    apps = _pipeline().run(_profile(), _postings(), PipelineConfig(top_k=3))
    pending = next(a for a in apps if a.status == ApplicationStatus.pending_review)

    # Not approved yet → no packet.
    with pytest.raises(NotApprovedError):
        build_packet(pending)

    # Approve → packet renders with the real content.
    approve(pending)
    md = build_packet(pending)
    assert "# Application packet" in md
    assert "Built payment APIs in Python at Acme." in md
    assert "72/100" in md


def test_build_approved_packets_skips_the_rest():
    apps = _pipeline().run(_profile(), _postings(), PipelineConfig(top_k=3))
    # Approve exactly one faithful application.
    faithful = [a for a in apps if a.status == ApplicationStatus.pending_review]
    approve(faithful[0])
    built = build_approved_packets(apps)
    assert len(built) == 1
    assert built[0][0] is faithful[0]
