"""Lightweight, local enrichment for job cards: salary and posted-date.

Both are derived with zero extra API calls:
* **salary** — a regex over the job's text (pay-transparency laws mean ranges are often in the
  description regardless of source).
* **posted date** — from the `posted_at` / `updated_at` we already ingest, rendered relative.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from apply_copilot.ingest.models import JobPosting

# Matches $120,000 - $160,000  /  $120K–$160K  /  $120,000 to $160,000
_SALARY = re.compile(
    r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?\s?[kK]?\s?(?:-|–|—|to)\s?\$?\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?\s?[kK]?"
)


def parse_salary(text: str | None) -> str | None:
    if not text:
        return None
    m = _SALARY.search(text)
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else None


def posted_ago(job: JobPosting) -> str | None:
    dt = job.posted_at or job.updated_at
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - dt).days
    if days <= 0:
        return "today"
    if days == 1:
        return "1 day ago"
    if days < 30:
        return f"{days} days ago"
    months = days // 30
    return "1 month ago" if months == 1 else f"{months} months ago"
