"""Greenhouse adapter — public job-board JSON API (read-only, built to be consumed).

Endpoint: https://boards-api.greenhouse.io/v1/boards/<company>/jobs?content=true
Docs: https://developers.greenhouse.io/job-board.html
"""

from __future__ import annotations

from typing import Any

from .base import JobSource
from .models import JobPosting
from .text import strip_html


class GreenhouseSource(JobSource):
    source_name = "greenhouse"

    def __init__(self, company: str, board_token: str | None = None) -> None:
        self.company = company
        # `board_token` is the slug in the URL; defaults to the company name.
        self.board_token = board_token or company

    def fetch_raw(self) -> list[dict[str, Any]]:
        url = (
            f"https://boards-api.greenhouse.io/v1/boards/{self.board_token}/jobs?content=true"
        )
        return self._get(url).json().get("jobs", [])

    def parse(self, record: dict[str, Any]) -> JobPosting:
        location = (record.get("location") or {}).get("name")
        departments = record.get("departments") or []
        department = departments[0]["name"] if departments else None
        return JobPosting(
            source=self.source_name,
            source_id=str(record["id"]),
            company=self.company,
            title=record["title"],
            location=location,
            department=department,
            url=record.get("absolute_url"),
            description=strip_html(record.get("content")),
            updated_at=record.get("updated_at"),
        )
