"""Extraction backend #1: native tool/function calling through our own LLM seam.

This uses `LLMClient.complete_structured`, which hands the model the target Pydantic schema as a
forced tool call and validates the result. It's the "by hand" version — we own the prompt, the
retry loop, and the validation — so we feel exactly what `instructor` is doing for us in the
other backend.

Grounding is enforced by the system prompt (extract only what's present; never invent) plus the
field descriptions on the models themselves.
"""

from __future__ import annotations

from ..llm import LLMClient, LLMError
from .models import Profile, Requirements

_GROUNDING = (
    "You are a meticulous information-extraction engine. Extract ONLY facts explicitly present "
    "in the source text. If a field is not stated, leave it null or empty — do NOT guess, infer "
    "beyond what's written, or invent employers, dates, skills, or numbers. Copy wording closely."
)


def _extract(
    client: LLMClient,
    *,
    system: str,
    prompt: str,
    model_cls,
    max_retries: int,
):
    """complete_structured with a small retry loop that feeds the error back on failure."""
    last_error: Exception | None = None
    attempt_prompt = prompt
    for _ in range(max_retries + 1):
        try:
            return client.complete_structured(
                attempt_prompt, model_cls, system=system, temperature=0.0
            )
        except LLMError as exc:
            last_error = exc
            attempt_prompt = (
                f"{prompt}\n\nYour previous attempt failed validation with: {exc}\n"
                "Return valid data matching the schema; use null/empty for anything not stated."
            )
    raise LLMError(f"Extraction failed after {max_retries + 1} attempts: {last_error}")


def extract_profile(resume_text: str, client: LLMClient | None = None, *, max_retries: int = 2) -> Profile:
    """Resume text → structured Profile (native tool-calling)."""
    client = client or LLMClient()
    prompt = f"Extract the candidate profile from this resume:\n\n---\n{resume_text}\n---"
    return _extract(client, system=_GROUNDING, prompt=prompt, model_cls=Profile, max_retries=max_retries)


def extract_requirements(jd_text: str, client: LLMClient | None = None, *, max_retries: int = 2) -> Requirements:
    """Job-description text → structured Requirements (native tool-calling)."""
    client = client or LLMClient()
    prompt = f"Extract the role requirements from this job description:\n\n---\n{jd_text}\n---"
    return _extract(
        client, system=_GROUNDING, prompt=prompt, model_cls=Requirements, max_retries=max_retries
    )
