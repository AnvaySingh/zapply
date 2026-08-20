"""Semantic matching: embed Profile vs Requirements → 0–100 score + rationale.

Naive-first: local sentence-transformers + in-memory cosine. No vector DB.
"""

from .embed import DEFAULT_MODEL, Embedder, cosine
from .matcher import Matcher, MatchResult
from .represent import profile_to_text, requirements_to_text

__all__ = [
    "Embedder",
    "cosine",
    "DEFAULT_MODEL",
    "Matcher",
    "MatchResult",
    "profile_to_text",
    "requirements_to_text",
]
