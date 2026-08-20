"""The review gate — the human maker-checker step, enforced as a program.

Two invariants live here, and they are the whole point of the phase:

1. You cannot approve an Application that failed the program faithfulness gate. `approve()` on a
   `blocked` application raises — the human is not allowed to wave through a draft the machine
   already caught lying.
2. Approval is an explicit, per-application act. Nothing reaches `approved` on its own.

`packet.build_packet` then refuses to render anything that isn't `approved`, so the two gates
compose: a packet requires human approval, which requires machine faithfulness.
"""

from __future__ import annotations

from .models import Application, ApplicationStatus


class ReviewError(RuntimeError):
    """Raised on an illegal review action (e.g. approving a blocked application)."""


def approve(application: Application) -> Application:
    if not application.is_faithful:
        raise ReviewError(
            f"cannot approve {application.label!r}: it failed the faithfulness gate "
            f"({len(application.faithfulness.violations)} violation(s))"
        )
    application.status = ApplicationStatus.approved
    return application


def reject(application: Application) -> Application:
    application.status = ApplicationStatus.rejected
    return application


def approvable(applications: list[Application]) -> list[Application]:
    """The applications a human may act on — faithful and still pending."""
    return [a for a in applications if a.status == ApplicationStatus.pending_review]
