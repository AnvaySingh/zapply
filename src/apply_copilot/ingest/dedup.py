"""Deduplication and incremental-refresh logic — the aggregation muscle.

Both operations key off `JobPosting.dedup_key` (canonical company+title+location):

* ``deduplicate`` — collapse the *same* role surfacing on multiple feeds into one, preserving
  first-seen order. Which copy wins matters (one feed may have a richer description), so we
  keep the first occurrence and let the caller order sources by preference.
* ``select_new`` — given the set of keys we've already seen, return only genuinely new
  postings. This is what makes re-polling cheap and quiet.

Both are pure functions: no I/O, fully covered by the Phase 1 eval.
"""

from __future__ import annotations

from collections.abc import Iterable

from .models import JobPosting


def deduplicate(postings: Iterable[JobPosting]) -> list[JobPosting]:
    """Collapse duplicates by canonical key, keeping the first occurrence."""
    seen: set[str] = set()
    unique: list[JobPosting] = []
    for posting in postings:
        key = posting.dedup_key
        if key in seen:
            continue
        seen.add(key)
        unique.append(posting)
    return unique


def select_new(postings: Iterable[JobPosting], seen_keys: set[str]) -> list[JobPosting]:
    """Return only postings whose key isn't already known. Order preserved."""
    fresh: list[JobPosting] = []
    emitted: set[str] = set()
    for posting in postings:
        key = posting.dedup_key
        if key in seen_keys or key in emitted:
            continue
        emitted.add(key)
        fresh.append(posting)
    return fresh
