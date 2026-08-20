"""The one internal shape every source normalises into.

`JobPosting` is the contract for Phase 1: no matter how heterogeneous the source (Greenhouse
JSON, Lever JSON, Ashby JSON, an RSS feed, a pasted blob), the rest of the app only ever sees
this. Adapters do the messy per-vendor mapping; downstream code stays clean.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from .text import dedup_key


class JobPosting(BaseModel):
    """A single job opening, normalised across every source."""

    source: str = Field(description="Adapter that produced this, e.g. 'greenhouse'.")
    source_id: str = Field(description="The posting's id within that source.")
    company: str
    title: str
    location: str | None = None
    department: str | None = None
    employment_type: str | None = None
    remote: bool | None = None
    url: str | None = Field(default=None, description="Canonical posting / apply URL.")
    description: str = Field(default="", description="Plain-text description (HTML stripped).")
    posted_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("company", "title")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned

    @property
    def dedup_key(self) -> str:
        """Canonical identity used for cross-source dedup and incremental refresh."""
        return dedup_key(self.company, self.title, self.location)

    def __str__(self) -> str:  # friendly one-liner for the CLI
        where = self.location or "—"
        return f"{self.company} · {self.title} ({where}) [{self.source}]"
