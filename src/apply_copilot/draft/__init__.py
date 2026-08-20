"""Grounded drafting: tailored resume bullets + screening answers, faithful to the profile.

The generation is grounded by context construction; the *program* (`check_draft`) decides whether
it stayed faithful. The LLM judge (used in the eval) is only a signal.
"""

from .context import DEFAULT_QUESTIONS, build_fact_sheet
from .drafter import draft
from .faithfulness import FaithfulnessReport, Violation, check_draft
from .models import DraftPacket, ScreeningAnswer, TailoredBullet
from .relevance import answer_addresses_question

__all__ = [
    "draft",
    "DraftPacket",
    "TailoredBullet",
    "ScreeningAnswer",
    "check_draft",
    "FaithfulnessReport",
    "Violation",
    "build_fact_sheet",
    "DEFAULT_QUESTIONS",
    "answer_addresses_question",
]
