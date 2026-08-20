"""Structured targets for extraction — the shapes we pull out of free text.

`Profile` is *me*, extracted from a resume. `Requirements` is a *role*, extracted from a JD.
These are the contracts Phase 3 (matching) and Phase 4 (drafting) build on, so they're
deliberately explicit. Field descriptions matter here: with tool/function calling the model
reads them as instructions, so they double as the extraction spec.

Grounding rule baked into the descriptions: when a fact isn't present in the source, the field
is left null / empty — the model must not invent it. Phase 4 leans hard on this.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Seniority(str, Enum):
    intern = "intern"
    junior = "junior"
    mid = "mid"
    senior = "senior"
    staff = "staff"
    principal = "principal"
    lead = "lead"
    manager = "manager"
    director = "director"
    unknown = "unknown"


# -- Profile (from a resume) ---------------------------------------------------


class Experience(BaseModel):
    company: str
    title: str
    start_date: str | None = Field(default=None, description="As written, e.g. 'Jan 2021'.")
    end_date: str | None = Field(default=None, description="As written, or 'Present'.")
    highlights: list[str] = Field(
        default_factory=list, description="Bullet points / achievements, verbatim from the resume."
    )


class Education(BaseModel):
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    graduation_year: int | None = None


class Profile(BaseModel):
    """A candidate profile extracted verbatim from a resume. Do not invent facts."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    summary: str | None = Field(default=None, description="Professional summary, if present.")
    seniority: Seniority = Field(
        default=Seniority.unknown, description="Overall seniority inferred from titles/tenure."
    )
    years_experience: float | None = Field(
        default=None, description="Total years of professional experience, if statable."
    )
    skills: list[str] = Field(
        default_factory=list, description="Technical + professional skills named in the resume."
    )
    work_authorization: str | None = Field(
        default=None, description="Work authorization / visa status, only if stated."
    )
    experiences: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    links: list[str] = Field(
        default_factory=list, description="URLs: GitHub, LinkedIn, portfolio, etc."
    )


# -- Requirements (from a job description) --------------------------------------


class Requirements(BaseModel):
    """The requirements of a role, extracted verbatim from a job description. Do not invent."""

    title: str
    company: str | None = None
    location: str | None = None
    remote: bool | None = None
    employment_type: str | None = Field(
        default=None, description="e.g. Full-time, Contract, Internship — only if stated."
    )
    seniority: Seniority = Seniority.unknown
    min_years_experience: float | None = Field(
        default=None, description="Minimum years required, if a number is stated."
    )
    required_skills: list[str] = Field(
        default_factory=list, description="Skills/technologies listed as required."
    )
    preferred_skills: list[str] = Field(
        default_factory=list, description="Skills listed as nice-to-have / preferred."
    )
    responsibilities: list[str] = Field(
        default_factory=list, description="What the role does, as listed."
    )
    education_requirement: str | None = Field(
        default=None, description="Degree/education requirement, only if stated."
    )
    work_authorization: str | None = Field(
        default=None, description="Sponsorship / authorization notes, only if stated."
    )
