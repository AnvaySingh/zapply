"""The programmatic faithfulness gate — the part that actually decides.

Per the project's core principle, faithfulness is decided by a program, not by the model
asserting it was faithful. Given a `DraftPacket`, the profile it must stay true to, and the
target role, this flags every concrete way the draft strayed:

* **Tag violations** — a bullet self-reports a company or skill that isn't in the profile.
* **Claimed-missing-skill** — the draft's TEXT names a skill the *role* wants but the candidate
  does NOT have (the classic "invent a skill to match the JD" hallucination).
* **Claimed-unworked-company** — a resume bullet names the hiring company as if it were a past
  employer.

The skill scan is bounded to the *relevant* vocabulary (profile skills ∪ role skills), so within
the set of skills that matter here, every skill named in a bullet must be one the candidate has.
Skills entirely outside that vocabulary can't be detected without NLP — a documented limitation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..extract.models import Profile, Requirements
from ..ingest.text import normalise_key_part
from .models import DraftPacket


@dataclass
class Violation:
    kind: str  # tag_company | tag_skill | claimed_missing_skill | claimed_unworked_company
    where: str  # e.g. "bullet[0]" / "answer[1]"
    detail: str


@dataclass
class FaithfulnessReport:
    violations: list[Violation] = field(default_factory=list)
    bullets_checked: int = 0
    answers_checked: int = 0

    @property
    def is_faithful(self) -> bool:
        return not self.violations


def _mentions(text: str, phrase: str) -> bool:
    """Whole-word, case-insensitive substring match on the raw text."""
    if not phrase.strip():
        return False
    return re.search(rf"\b{re.escape(phrase)}\b", text, flags=re.IGNORECASE) is not None


def check_draft(packet: DraftPacket, profile: Profile, requirements: Requirements) -> FaithfulnessReport:
    allowed_skills = {normalise_key_part(s) for s in profile.skills}
    allowed_companies = {normalise_key_part(e.company) for e in profile.experiences}

    role_skills_raw = list(requirements.required_skills) + list(requirements.preferred_skills)
    # Skills the role wants that the candidate does NOT have → must never be claimed.
    forbidden_skills_raw = [
        s for s in role_skills_raw if normalise_key_part(s) not in allowed_skills
    ]
    hiring_company = requirements.company

    report = FaithfulnessReport()

    for i, bullet in enumerate(packet.bullets):
        report.bullets_checked += 1
        where = f"bullet[{i}]"

        # (1) structured tags must point at real profile facts
        if bullet.company and normalise_key_part(bullet.company) not in allowed_companies:
            report.violations.append(
                Violation("tag_company", where, f"tagged employer {bullet.company!r} not in profile")
            )
        for skill in bullet.skills_used:
            if normalise_key_part(skill) not in allowed_skills:
                report.violations.append(
                    Violation("tag_skill", where, f"tagged skill {skill!r} not in profile")
                )

        # (2) free-text must not claim a skill the candidate lacks
        for skill in forbidden_skills_raw:
            if _mentions(bullet.text, skill):
                report.violations.append(
                    Violation("claimed_missing_skill", where, f"text claims absent skill {skill!r}")
                )

        # (3) a resume bullet must not name the hiring company as a past employer
        if hiring_company and _mentions(bullet.text, hiring_company):
            report.violations.append(
                Violation("claimed_unworked_company", where, f"bullet names hiring company {hiring_company!r}")
            )

    for i, answer in enumerate(packet.answers):
        report.answers_checked += 1
        where = f"answer[{i}]"
        for skill in forbidden_skills_raw:
            if _mentions(answer.answer, skill):
                report.violations.append(
                    Violation("claimed_missing_skill", where, f"answer claims absent skill {skill!r}")
                )

    return report
