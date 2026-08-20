"""RSS / Atom adapter — for job feeds published as syndication (read-only).

Many boards and aggregators publish an RSS/Atom feed built to be pulled. `feedparser` handles
both formats and their many dialects. We keep a pure ``entries_from_feed(text)`` helper so the
eval can turn a recorded XML fixture into entries without any network.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import feedparser

from .base import JobSource
from .models import JobPosting
from .text import strip_html


def entries_from_feed(text: str) -> list[dict[str, Any]]:
    """Parse an RSS/Atom document (as text) into a list of entry dicts. Pure."""
    parsed = feedparser.parse(text)
    return [dict(entry) for entry in parsed.entries]


def _struct_to_dt(struct: Any) -> datetime | None:
    if not struct:
        return None
    try:
        return datetime(*struct[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


class RSSSource(JobSource):
    source_name = "rss"

    def __init__(self, url: str, company: str) -> None:
        self.url = url
        # RSS entries rarely carry a clean company field, so the feed is labelled in config.
        self.company = company

    def fetch_raw(self) -> list[dict[str, Any]]:
        text = self._get(self.url, headers={"Accept": "application/rss+xml, application/xml"}).text
        return entries_from_feed(text)

    def parse(self, record: dict[str, Any]) -> JobPosting:
        link = record.get("link")
        summary = record.get("summary") or record.get("description")
        return JobPosting(
            source=self.source_name,
            source_id=str(record.get("id") or link or record["title"]),
            company=self.company,
            title=record["title"],
            url=link,
            description=strip_html(summary),
            posted_at=_struct_to_dt(record.get("published_parsed"))
            or _struct_to_dt(record.get("updated_parsed")),
        )
