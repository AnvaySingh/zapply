"""Structured targets for grounded drafting.

The draft is structured, not free text, for a reason: each tailored bullet self-reports which
real company and which real skills it draws on, so a *program* can verify those tags against the
profile. The model proposes; the faithfulness checker disposes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TailoredBullet(BaseModel):
    """One resume bullet, reframed toward the target role from REAL experience."""

    text: str = Field(description="The bullet, one sentence. Uses only facts from the profile.")
    company: str | None = Field(
        default=None, description="Which profile employer this bullet is about (must be one of them)."
    )
    skills_used: list[str] = Field(
        default_factory=list,
        description="Skills referenced, each of which MUST be in the candidate's profile skills.",
    )


class ScreeningAnswer(BaseModel):
    """An answer to one screening question, grounded in the profile."""

    question: str
    answer: str = Field(
        description="Answer grounded only in the profile. If the profile doesn't cover it, say so."
    )
    grounded_in: list[str] = Field(
        default_factory=list, description="Profile facts (companies/skills) this answer relies on."
    )


class DraftPacket(BaseModel):
    """The full grounded draft: tailored bullets + screening answers."""

    bullets: list[TailoredBullet] = Field(default_factory=list)
    answers: list[ScreeningAnswer] = Field(default_factory=list)
