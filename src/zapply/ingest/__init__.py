"""Automated ingestion: heterogeneous read-only sources → one normalised, deduped feed.

Phase 1. No AI, no scraping, no login — public ATS JSON endpoints, RSS, and local paste only.
"""

from .ashby import AshbySource
from .base import JobSource, SourceError
from .dedup import deduplicate, select_new
from .greenhouse import GreenhouseSource
from .lever import LeverSource
from .models import JobPosting
from .paste import PasteSource
from .rss import RSSSource, entries_from_feed
from .service import IngestResult, IngestService, build_sources, load_sources
from .state import SeenStore

__all__ = [
    "JobPosting",
    "JobSource",
    "SourceError",
    "GreenhouseSource",
    "LeverSource",
    "AshbySource",
    "RSSSource",
    "PasteSource",
    "entries_from_feed",
    "deduplicate",
    "select_new",
    "SeenStore",
    "IngestService",
    "IngestResult",
    "build_sources",
    "load_sources",
]
