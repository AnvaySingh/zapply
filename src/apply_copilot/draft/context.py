"""Context construction — the actual anti-hallucination mechanism.

Grounding isn't a polite request bolted onto a prompt; it's how you *build the context*. We hand
the model an explicit fact sheet — the only employers, skills, and credentials it's allowed to
use — and frame the task as "reframe these real facts toward the role", never "write something
impressive". The tighter and more explicit the fact sheet, the less room to invent. This is the
strategy NOTES.md documents.
"""

from __future__ import annotations

from ..extract.models import Profile, Requirements

GROUNDING_SYSTEM = (
    "You are a careful application assistant helping a real candidate. You draft resume bullets "
    "and screening answers that are TAILORED to a target role but STRICTLY TRUTHFUL to the "
    "candidate's fact sheet. Absolute rules:\n"
    "1. Use ONLY employers, titles, skills, and credentials that appear in the fact sheet.\n"
    "2. NEVER introduce a skill the candidate doesn't have — not even if the role requires it. "
    "If the role wants a skill they lack, simply don't mention it.\n"
    "3. NEVER claim to have worked at the hiring company or anywhere not in the fact sheet.\n"
    "4. Do not invent metrics, dates, or achievements. Reframe real ones; don't fabricate.\n"
    "5. For a screening question the fact sheet can't support, say the background doesn't cover it "
    "rather than making something up.\n"
    "Tailoring means emphasis and phrasing, never invention."
)


def build_fact_sheet(profile: Profile) -> str:
    """Render the profile as the explicit, closed set of allowed facts."""
    lines: list[str] = ["=== CANDIDATE FACT SHEET (the only facts you may use) ==="]
    if profile.name:
        lines.append(f"Name: {profile.name}")
    if profile.seniority and profile.seniority.value != "unknown":
        lines.append(f"Seniority: {profile.seniority.value}")
    if profile.years_experience is not None:
        lines.append(f"Years of experience: {profile.years_experience}")

    lines.append("\nEmployers & roles (the ONLY employers you may name):")
    if profile.experiences:
        for exp in profile.experiences:
            span = " – ".join(x for x in (exp.start_date, exp.end_date) if x)
            header = f"  - {exp.title} at {exp.company}" + (f" ({span})" if span else "")
            lines.append(header)
            for hl in exp.highlights:
                lines.append(f"      • {hl}")
    else:
        lines.append("  (none listed)")

    lines.append("\nSkills (the ONLY skills you may claim):")
    lines.append("  " + (", ".join(profile.skills) if profile.skills else "(none listed)"))

    if profile.education:
        lines.append("\nEducation:")
        for ed in profile.education:
            bits = ", ".join(x for x in (ed.degree, ed.field_of_study, ed.institution) if x)
            year = f" ({ed.graduation_year})" if ed.graduation_year else ""
            lines.append(f"  - {bits}{year}")

    return "\n".join(lines)


def build_draft_prompt(
    profile: Profile, requirements: Requirements, questions: list[str], n_bullets: int
) -> str:
    """Assemble the user prompt: fact sheet + target role + the specific tasks."""
    fact_sheet = build_fact_sheet(profile)
    role = [
        "=== TARGET ROLE ===",
        f"Title: {requirements.title}",
    ]
    if requirements.company:
        role.append(f"Company (you have NOT worked here): {requirements.company}")
    if requirements.required_skills:
        role.append("Required skills: " + ", ".join(requirements.required_skills))
    if requirements.preferred_skills:
        role.append("Preferred skills: " + ", ".join(requirements.preferred_skills))
    if requirements.responsibilities:
        role.append("Responsibilities: " + " ".join(requirements.responsibilities))

    q_block = "\n".join(f"  - {q}" for q in questions) if questions else "  (none)"

    return (
        f"{fact_sheet}\n\n"
        + "\n".join(role)
        + "\n\n=== TASKS ===\n"
        f"1. Write {n_bullets} tailored resume bullets that reframe the candidate's REAL "
        "experience toward this role. Each bullet must tag the employer it's about and the "
        "profile skills it uses.\n"
        "2. Answer each screening question below, grounded only in the fact sheet:\n"
        f"{q_block}\n"
    )


DEFAULT_QUESTIONS = [
    "Why are you a good fit for this role?",
    "Describe your most relevant experience for this position.",
]
