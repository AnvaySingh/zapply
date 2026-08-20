"""Turn structured Profile / Requirements into the text we embed.

An embedding model sees *text*, not fields. How we serialise a `Profile` or `Requirements` into
a string is a real modelling choice — include the right signal (titles, skills, seniority),
leave out noise (emails, URLs, dates). This is the quiet lever that most affects match quality,
and the first knob NOTES.md flags for tuning.
"""

from __future__ import annotations

from ..extract.models import Profile, Requirements


def profile_to_text(profile: Profile) -> str:
    parts: list[str] = []
    if profile.seniority and profile.seniority.value != "unknown":
        parts.append(f"Seniority: {profile.seniority.value}.")
    if profile.summary:
        parts.append(profile.summary)
    if profile.skills:
        parts.append("Skills: " + ", ".join(profile.skills) + ".")
    titles = [e.title for e in profile.experiences if e.title]
    if titles:
        parts.append("Roles held: " + "; ".join(titles) + ".")
    # A little signal from what they actually did.
    highlights = [h for e in profile.experiences for h in e.highlights][:5]
    if highlights:
        parts.append(" ".join(highlights))
    return "\n".join(parts).strip()


def requirements_to_text(reqs: Requirements) -> str:
    parts: list[str] = [f"Role: {reqs.title}."]
    if reqs.seniority and reqs.seniority.value != "unknown":
        parts.append(f"Seniority: {reqs.seniority.value}.")
    if reqs.required_skills:
        parts.append("Required skills: " + ", ".join(reqs.required_skills) + ".")
    if reqs.preferred_skills:
        parts.append("Preferred skills: " + ", ".join(reqs.preferred_skills) + ".")
    if reqs.responsibilities:
        parts.append("Responsibilities: " + " ".join(reqs.responsibilities))
    return "\n".join(parts).strip()
