"""Paste / file adapter — for one-off JDs I drop in by hand (read-only, local).

No network. Give it raw text (pasted or read from a file) plus the company and title, and it
produces a single `JobPosting`. This is the escape hatch for a role that isn't on any board I
poll — I still want it in the same pipeline as everything else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import JobSource
from .models import JobPosting
from .text import strip_html


class PasteSource(JobSource):
    source_name = "paste"

    def __init__(
        self,
        text: str,
        *,
        company: str,
        title: str,
        location: str | None = None,
        url: str | None = None,
    ) -> None:
        self.text = text
        self.company = company
        self.title = title
        self.location = location
        self.url = url

    @classmethod
    def from_file(cls, path: str | Path, *, company: str, title: str, **kwargs: Any) -> "PasteSource":
        return cls(Path(path).read_text(encoding="utf-8"), company=company, title=title, **kwargs)

    def fetch_raw(self) -> list[dict[str, Any]]:
        return [
            {
                "company": self.company,
                "title": self.title,
                "location": self.location,
                "url": self.url,
                "text": self.text,
            }
        ]

    def parse(self, record: dict[str, Any]) -> JobPosting:
        # A pasted blob may itself be HTML; strip it defensively.
        description = strip_html(record["text"]) if "<" in record["text"] else record["text"].strip()
        return JobPosting(
            source=self.source_name,
            source_id=f"paste:{record['company']}:{record['title']}".lower(),
            company=record["company"],
            title=record["title"],
            location=record.get("location"),
            url=record.get("url"),
            description=description,
        )
