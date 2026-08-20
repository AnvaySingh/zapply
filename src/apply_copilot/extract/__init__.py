"""Structured extraction: resume → Profile, JD → Requirements.

Two interchangeable backends over the same Pydantic targets:
* ``native``     — hand-rolled tool/function calling through our LLM seam (traced).
* ``instructor`` — the `instructor` library (talks to the provider directly).

Use `extract_profile` / `extract_requirements` with `backend=` to pick, or import a backend
module directly.
"""

from __future__ import annotations

from ..llm import LLMClient
from . import instructor_impl, native
from .models import Education, Experience, Profile, Requirements, Seniority

Backend = str  # "native" | "instructor"


def extract_profile(
    resume_text: str, *, backend: Backend = "native", client: LLMClient | None = None
) -> Profile:
    if backend == "instructor":
        return instructor_impl.extract_profile(resume_text)
    return native.extract_profile(resume_text, client)


def extract_requirements(
    jd_text: str, *, backend: Backend = "native", client: LLMClient | None = None
) -> Requirements:
    if backend == "instructor":
        return instructor_impl.extract_requirements(jd_text)
    return native.extract_requirements(jd_text, client)


__all__ = [
    "Profile",
    "Requirements",
    "Experience",
    "Education",
    "Seniority",
    "extract_profile",
    "extract_requirements",
    "native",
    "instructor_impl",
]
