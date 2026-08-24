"""Job loading for the demo web app.

For a live demo we don't want to depend on network calls mid-presentation, so postings are
snapshotted to disk once and loaded from there. `refresh_snapshot()` re-ingests from the real
read-only sources (Greenhouse/Lever/Ashby/RSS) and rewrites the snapshot.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from zapply.ingest import deduplicate, load_sources
from zapply.ingest.models import JobPosting

_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = _ROOT / "data" / "jobs_snapshot.json"
VECTORS = _ROOT / "data" / "job_vectors.npy"
CONFIG = _ROOT / "companies.yaml"


def job_text(job: JobPosting) -> str:
    """The text we embed for a posting — title carries most of the signal."""
    return f"{job.title}\n{job.description[:1000]}"


SENIORITY_ORDER = ["Intern", "Junior", "Mid", "Senior", "Staff+", "Manager"]


def seniority_category(job: JobPosting) -> str:
    """Classify seniority from the title (local, no LLM). Defaults to Mid."""
    t = f" {job.title.lower()} "
    if any(k in t for k in ("intern", "internship")):
        return "Intern"
    if any(k in t for k in ("vp ", "vice president", "chief", "head of", "director", "manager")):
        return "Manager"
    if any(k in t for k in ("principal", "staff", "distinguished", "fellow")):
        return "Staff+"
    if any(k in t for k in ("senior", "sr.", " sr ", " lead", "lead ", " iii", " iv", "architect")):
        return "Senior"
    if any(k in t for k in ("junior", "jr.", " jr ", "entry", "new grad", "graduate", "associate", "early career")):
        return "Junior"
    return "Mid"


def workplace_category(job: JobPosting) -> str:
    """Classify a posting as Remote / Hybrid / On-site / Unknown.

    Signal order: an explicit `remote` flag (Lever/Ashby set it), then keywords in the location
    and title. 'hybrid' wins over 'remote' because a hybrid role often mentions both.
    """
    text = f"{job.location or ''} {job.title}".lower()
    if "hybrid" in text:
        return "Hybrid"
    if job.remote is True or any(k in text for k in ("remote", "wfh", "work from home", "distributed")):
        return "Remote"
    if job.remote is False or job.location:
        return "On-site"
    return "Unknown"


def load_or_build_vectors(jobs: list[JobPosting], embedder) -> np.ndarray:
    """Embed all postings, cached to disk so app startup is instant after the first build."""
    if VECTORS.exists():
        vecs = np.load(VECTORS)
        if vecs.shape[0] == len(jobs):
            return vecs
    vecs = embedder.encode([job_text(j) for j in jobs])
    VECTORS.parent.mkdir(parents=True, exist_ok=True)
    np.save(VECTORS, vecs)
    return vecs


def refresh_snapshot(config: Path = CONFIG) -> list[JobPosting]:
    """Ingest live from all configured sources, dedup, and write the snapshot."""
    postings: list[JobPosting] = []
    for source in load_sources(config):
        try:
            postings.extend(source.fetch())
        except Exception:  # noqa: BLE001 - one flaky board shouldn't stop the snapshot
            pass
    postings = deduplicate(postings)
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(
        json.dumps([p.model_dump(mode="json") for p in postings], indent=2), encoding="utf-8"
    )
    VECTORS.unlink(missing_ok=True)  # stale — force a rebuild against the new feed
    return postings


def load_jobs() -> list[JobPosting]:
    """Load postings from the snapshot, falling back to a live ingest if there isn't one."""
    if SNAPSHOT.exists():
        raw = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        return [JobPosting.model_validate(r) for r in raw]
    return refresh_snapshot()
