"""Generate a grounded DraftPacket from a Profile + Requirements.

One structured call produces both tailored bullets and screening answers — deliberately a single
call (grounded context in, structured draft out) to keep it cheap and traced through our seam.
The generation is only half the job; the caller runs `check_draft` (the program gate) on the
result.
"""

from __future__ import annotations

from ..llm import LLMClient
from ..extract.models import Profile, Requirements
from .context import DEFAULT_QUESTIONS, GROUNDING_SYSTEM, build_draft_prompt
from .models import DraftPacket


def draft(
    profile: Profile,
    requirements: Requirements,
    *,
    questions: list[str] | None = None,
    client: LLMClient | None = None,
    n_bullets: int = 3,
    max_tokens: int = 2048,
) -> DraftPacket:
    """Draft grounded bullets + screening answers. Grounding lives in the context, not hope."""
    client = client or LLMClient()
    questions = questions if questions is not None else DEFAULT_QUESTIONS
    prompt = build_draft_prompt(profile, requirements, questions, n_bullets)
    return client.complete_structured(
        prompt,
        DraftPacket,
        system=GROUNDING_SYSTEM,
        temperature=0.2,
        max_tokens=max_tokens,
    )
