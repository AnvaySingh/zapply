"""Extraction backend #2: the `instructor` library.

Same targets (`Profile`, `Requirements`), but instructor owns the schema-injection, the
validation, and the retry loop for us. This is the "let the library do it" version — we build it
alongside the native one so NOTES.md can compare them honestly (what you gain, what you give up).

It talks to the provider *directly* (not through our `LLMClient`), so these calls are not routed
through our Langfuse tracer — a real tradeoff, noted in NOTES.md.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..config import get_settings
from .models import Profile, Requirements

_GROUNDING = (
    "You are a meticulous information-extraction engine. Extract ONLY facts explicitly present "
    "in the source text. If a field is not stated, leave it null or empty — never invent."
)


@lru_cache
def _client_and_model() -> tuple[Any, str]:
    """Build an instructor-patched client for the configured provider."""
    import instructor

    config = get_settings().resolve_provider()
    if config.kind == "anthropic":
        from anthropic import Anthropic

        return instructor.from_anthropic(Anthropic(api_key=config.api_key)), config.model

    # openai_compatible (Gemini, Groq, Ollama, OpenAI, ...)
    from openai import OpenAI

    oai = OpenAI(api_key=config.api_key or "not-needed", base_url=config.base_url)
    # JSON mode is the most portable across OpenAI-compatible endpoints (incl. Gemini).
    return instructor.from_openai(oai, mode=instructor.Mode.JSON), config.model


def _extract(model_cls, prompt: str, *, max_retries: int):
    client, model = _client_and_model()
    return client.chat.completions.create(
        model=model,
        response_model=model_cls,
        max_retries=max_retries,
        temperature=0.0,
        messages=[
            {"role": "system", "content": _GROUNDING},
            {"role": "user", "content": prompt},
        ],
    )


def extract_profile(resume_text: str, *, max_retries: int = 2) -> Profile:
    """Resume text → structured Profile (via instructor)."""
    prompt = f"Extract the candidate profile from this resume:\n\n---\n{resume_text}\n---"
    return _extract(Profile, prompt, max_retries=max_retries)


def extract_requirements(jd_text: str, *, max_retries: int = 2) -> Requirements:
    """Job-description text → structured Requirements (via instructor)."""
    prompt = f"Extract the role requirements from this job description:\n\n---\n{jd_text}\n---"
    return _extract(Requirements, prompt, max_retries=max_retries)
