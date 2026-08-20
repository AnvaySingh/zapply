"""A programmatic *floor* on relevance: is this a substantive answer at all?

Deliberately humble. Keyword-overlap "relevance" is unreliable — a perfectly on-topic answer
("At Acme Corp I designed payment APIs…") often shares no literal word with the question
("Describe your most relevant experience…"), so requiring overlap produces false negatives.
So the program only catches what it *can* catch deterministically: empty, one-word, or stock
non-answers. Judging whether a substantive answer is actually *on topic* is the LLM judge's job
in the eval — a signal, not this hard floor. NOTES.md explains why the split.
"""

from __future__ import annotations

import re

_NON_ANSWER = re.compile(
    r"^\s*(yes|no|n/?a|idk|maybe|i\s+don'?t\s+know|not\s+sure|no\s+comment)\b[.!]?\s*$",
    re.IGNORECASE,
)


def answer_addresses_question(question: str, answer: str, *, min_words: int = 8) -> bool:
    """True if the answer is a substantive attempt (not empty / one-word / stock non-answer)."""
    ans = answer.strip()
    if _NON_ANSWER.match(ans):
        return False
    return len(ans.split()) >= min_words
