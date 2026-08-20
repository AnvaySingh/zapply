"""Wire sources → dedup → incremental refresh into one run, and build sources from config.

This is the aggregator: poll every configured source, collapse cross-source duplicates, and
surface only what's genuinely new since last time. No AI anywhere in Phase 1 — this is pure
data plumbing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .ashby import AshbySource
from .base import JobSource, SourceError
from .dedup import deduplicate, select_new
from .greenhouse import GreenhouseSource
from .lever import LeverSource
from .models import JobPosting
from .rss import RSSSource
from .state import SeenStore

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    fetched: int  # total postings pulled across all sources (pre-dedup)
    unique: int  # after collapsing cross-source duplicates
    new: list[JobPosting] = field(default_factory=list)  # genuinely new since last run
    postings: list[JobPosting] = field(default_factory=list)  # all unique postings this run


class IngestService:
    """Runs a batch of sources, dedupes, and filters to new postings."""

    def __init__(self, sources: list[JobSource], store: SeenStore | None = None) -> None:
        self.sources = sources
        self.store = store

    def run(self, *, persist: bool = True) -> IngestResult:
        collected: list[JobPosting] = []
        for source in self.sources:
            try:
                collected.extend(source.fetch())
            except SourceError as exc:
                # A single flaky board shouldn't abort the whole run.
                logger.warning("source %s failed: %s", source.source_name, exc)

        unique = deduplicate(collected)

        seen = self.store.load() if self.store else set()
        new = select_new(unique, seen)

        if self.store and persist:
            self.store.save(seen | {p.dedup_key for p in unique})

        return IngestResult(
            fetched=len(collected), unique=len(unique), new=new, postings=unique
        )


# -- building sources from companies.yaml --------------------------------------

_BUILDERS = {
    "greenhouse": lambda e: GreenhouseSource(company=e["company"], board_token=e.get("board_token")),
    "lever": lambda e: LeverSource(company=e["company"]),
    "ashby": lambda e: AshbySource(company=e["company"], board_name=e.get("board_name")),
    "rss": lambda e: RSSSource(url=e["url"], company=e["company"]),
}


def build_sources(config: dict[str, Any]) -> list[JobSource]:
    """Turn a parsed companies.yaml dict into concrete source adapters."""
    sources: list[JobSource] = []
    for entry in config.get("sources", []):
        kind = str(entry.get("type", "")).lower()
        builder = _BUILDERS.get(kind)
        if builder is None:
            logger.warning("unknown source type %r — skipping", entry.get("type"))
            continue
        try:
            sources.append(builder(entry))
        except KeyError as exc:
            logger.warning("source entry %r missing field %s — skipping", entry, exc)
    return sources


def load_sources(config_path: str | Path) -> list[JobSource]:
    """Read companies.yaml from disk and build its sources."""
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    return build_sources(config)
