"""The pluggable source interface.

Every adapter splits into two halves on purpose:

* ``fetch_raw()`` — the *impure* half: one read-only HTTP GET (or a file read). This is the
  only part that touches the network.
* ``parse(record)`` — the *pure* half: map one raw record into a `JobPosting`. No I/O, so it's
  trivially unit-testable against recorded fixtures — which is exactly what the Phase 1 eval
  does.

Keeping the seam here means the eval never needs the network: it feeds recorded payloads
straight into `parse()`.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import httpx

from .models import JobPosting

logger = logging.getLogger(__name__)

# A gentle, honest User-Agent. We are a read-only consumer of public endpoints.
USER_AGENT = "apply-copilot/0.1 (personal job-application copilot; read-only)"
DEFAULT_TIMEOUT = 20.0


class SourceError(RuntimeError):
    """Raised when a source can't be fetched or a record can't be parsed."""


class JobSource(ABC):
    """Base class for every ingestion adapter."""

    source_name: ClassVar[str]

    @abstractmethod
    def fetch_raw(self) -> list[dict[str, Any]]:
        """Return the source's raw records (network / file). Impure."""

    @abstractmethod
    def parse(self, record: dict[str, Any]) -> JobPosting:
        """Map one raw record into a normalised JobPosting. Pure — no I/O."""

    def fetch(self) -> list[JobPosting]:
        """Fetch + parse everything, skipping (and logging) records that won't parse."""
        postings: list[JobPosting] = []
        for record in self.fetch_raw():
            try:
                postings.append(self.parse(record))
            except Exception as exc:  # one bad record shouldn't sink the whole poll
                logger.warning("%s: skipping unparseable record: %s", self.source_name, exc)
        return postings

    # -- shared HTTP helper ----------------------------------------------------

    @staticmethod
    def _get(url: str, *, headers: dict[str, str] | None = None) -> httpx.Response:
        """A single, read-only GET with a gentle footprint."""
        merged = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if headers:
            merged.update(headers)
        try:
            response = httpx.get(
                url, headers=merged, timeout=DEFAULT_TIMEOUT, follow_redirects=True
            )
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise SourceError(f"GET {url} failed: {exc}") from exc
