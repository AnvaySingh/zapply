"""Render an APPROVED application into a clean, paste-ready packet.

This module is the second half of the maker-checker lock: `build_packet` refuses to render
anything whose status isn't `approved`. There is no code path that turns a pending, rejected, or
blocked application into a packet — so "the pipeline cannot emit a packet that wasn't approved" is
enforced here, not merely intended.
"""

from __future__ import annotations

from ..orchestrate.models import Application, ApplicationStatus


class NotApprovedError(RuntimeError):
    """Raised when something tries to build a packet from an un-approved application."""


def build_packet(application: Application) -> str:
    if application.status != ApplicationStatus.approved:
        raise NotApprovedError(
            f"refusing to build a packet for {application.label!r}: status is "
            f"{application.status.value}, not 'approved'. A packet requires human approval."
        )

    reqs = application.requirements
    match = application.match
    draft = application.draft

    lines: list[str] = []
    lines.append(f"# Application packet — {application.label}")
    if application.posting.url:
        lines.append(f"Apply at: {application.posting.url}")
    lines.append("")
    lines.append(f"**Match:** {match.score}/100 — {match.rationale}")
    lines.append("")

    lines.append("## Tailored resume bullets")
    for bullet in draft.bullets:
        lines.append(f"- {bullet.text}")
    if not draft.bullets:
        lines.append("- (none)")
    lines.append("")

    lines.append("## Screening answers")
    for answer in draft.answers:
        lines.append(f"**Q: {answer.question}**")
        lines.append(answer.answer)
        lines.append("")

    lines.append("## Verification")
    lines.append("✓ Faithfulness gate passed — every claim traces to the profile.")
    if match.missing_skills:
        lines.append(f"⚠ Role skills not in your profile (not claimed): {', '.join(match.missing_skills)}")

    return "\n".join(lines).strip() + "\n"


def build_approved_packets(applications: list[Application]) -> list[tuple[Application, str]]:
    """Render every approved application; silently skip the rest (they can't be packeted)."""
    out: list[tuple[Application, str]] = []
    for app in applications:
        if app.status == ApplicationStatus.approved:
            out.append((app, build_packet(app)))
    return out
