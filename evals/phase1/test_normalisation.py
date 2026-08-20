"""Program gate (a): every source normalises to a schema-valid JobPosting.

Runs each adapter's PURE `parse()` over recorded real payloads — no network. A record that
fails Pydantic validation raises on construction, so "parsed without raising" == "schema-valid".
We also assert the obvious field mappings landed, so a parser that silently returns blanks is
caught.
"""

from __future__ import annotations

import json
from pathlib import Path

from apply_copilot.ingest import (
    AshbySource,
    GreenhouseSource,
    JobPosting,
    LeverSource,
    RSSSource,
    entries_from_feed,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _postings_by_source() -> dict[str, list[JobPosting]]:
    gh = GreenhouseSource("Stripe")
    greenhouse = [gh.parse(j) for j in load_json("greenhouse_stripe.json")["jobs"]]

    lv = LeverSource("Spotify")
    lever = [lv.parse(j) for j in load_json("lever_spotify.json")]

    ash = AshbySource("Ramp")
    ashby = [ash.parse(j) for j in load_json("ashby_ramp.json")["jobs"]]

    rss = RSSSource("https://example.test/feed", company="We Work Remotely")
    rss_posts = [rss.parse(e) for e in entries_from_feed(load_text("rss_wwr.xml"))]

    return {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "rss": rss_posts}


def test_every_source_yields_schema_valid_postings():
    by_source = _postings_by_source()

    # (a) each fixture produced the expected number of postings, all valid JobPostings.
    expected_counts = {"greenhouse": 2, "lever": 2, "ashby": 2, "rss": 2}
    for name, postings in by_source.items():
        assert postings, f"{name}: no postings parsed"
        assert len(postings) == expected_counts[name], f"{name}: unexpected count"
        for p in postings:
            assert isinstance(p, JobPosting)
            assert p.source == name
            assert p.company.strip()
            assert p.title.strip()


def test_key_fields_are_mapped_not_blank():
    by_source = _postings_by_source()

    # ATS sources should carry a posting URL and a stable source_id.
    for name in ("greenhouse", "lever", "ashby"):
        for p in by_source[name]:
            assert p.url and p.url.startswith("http"), f"{name}: missing url"
            assert p.source_id, f"{name}: missing source_id"

    # Greenhouse maps department + strips HTML description to plain text.
    gh = by_source["greenhouse"][0]
    assert gh.department
    assert "<" not in gh.description  # HTML was stripped

    # RSS carries a title + link at minimum.
    for p in by_source["rss"]:
        assert p.title and p.url
