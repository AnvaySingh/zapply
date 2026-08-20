"""Ashby adapter — public posting-API job board (read-only, built to be consumed).

Endpoint: https://api.ashbyhq.com/posting-api/job-board/<board-name>
Docs: https://developers.ashbyhq.com/reference/getpublishedjobposts
"""

from __future__ import annotations

from typing import Any

from .base import JobSource
from .models import JobPosting
from .text import strip_html


class AshbySource(JobSource):
    source_name = "ashby"

    def __init__(self, company: str, board_name: str | None = None) -> None:
        self.company = company
        self.board_name = board_name or company

    def fetch_raw(self) -> list[dict[str, Any]]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{self.board_name}"
        return self._get(url).json().get("jobs", [])

    def parse(self, record: dict[str, Any]) -> JobPosting:
        return JobPosting(
            source=self.source_name,
            source_id=str(record["id"]),
            company=self.company,
            title=record["title"],
            location=record.get("location"),
            department=record.get("department") or record.get("team"),
            employment_type=record.get("employmentType"),
            remote=record.get("isRemote"),
            url=record.get("jobUrl") or record.get("applyUrl"),
            description=strip_html(record.get("descriptionHtml")),
            posted_at=record.get("publishedAt"),
            updated_at=record.get("updatedAt"),
        )
