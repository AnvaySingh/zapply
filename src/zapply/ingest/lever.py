"""Lever adapter — public postings JSON API (read-only, built to be consumed).

Endpoint: https://api.lever.co/v0/postings/<company>?mode=json
Docs: https://github.com/lever/postings-api
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import JobSource
from .models import JobPosting
from .text import strip_html


def _from_ms(epoch_ms: Any) -> datetime | None:
    """Lever timestamps are milliseconds since the epoch."""
    if not epoch_ms:
        return None
    try:
        return datetime.fromtimestamp(int(epoch_ms) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


class LeverSource(JobSource):
    source_name = "lever"

    def __init__(self, company: str) -> None:
        self.company = company

    def fetch_raw(self) -> list[dict[str, Any]]:
        url = f"https://api.lever.co/v0/postings/{self.company}?mode=json"
        return self._get(url).json()  # Lever returns a top-level JSON array

    def parse(self, record: dict[str, Any]) -> JobPosting:
        categories = record.get("categories") or {}
        workplace = (record.get("workplaceType") or "").lower()
        return JobPosting(
            source=self.source_name,
            source_id=str(record["id"]),
            company=self.company,
            title=record["text"],
            location=categories.get("location"),
            department=categories.get("department") or categories.get("team"),
            employment_type=categories.get("commitment"),
            remote=True if workplace == "remote" else (False if workplace else None),
            url=record.get("hostedUrl") or record.get("applyUrl"),
            description=record.get("descriptionPlain") or strip_html(record.get("description")),
            posted_at=_from_ms(record.get("createdAt")),
        )
