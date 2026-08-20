"""Program gate (b): the deduper collapses known duplicates to the expected count.

Greenhouse and Lever fixtures both list the same role for the same company ("Acme · Staff
Software Engineer · Remote"). Across the two feeds there are 4 raw postings; exactly one is a
cross-source duplicate, so dedup must yield 3.
"""

from __future__ import annotations

import json
from pathlib import Path

from apply_copilot.ingest import GreenhouseSource, LeverSource, deduplicate

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _acme_postings():
    gh = GreenhouseSource("Acme")
    lv = LeverSource("Acme")
    greenhouse = [gh.parse(j) for j in load_json("dedup_greenhouse.json")["jobs"]]
    lever = [lv.parse(j) for j in load_json("dedup_lever.json")]
    return greenhouse + lever


def test_dedup_collapses_cross_source_duplicate():
    postings = _acme_postings()
    assert len(postings) == 4  # 2 from each feed

    unique = deduplicate(postings)

    # Exactly one duplicate collapses -> 3 unique roles.
    assert len(unique) == 3

    titles = sorted(p.title for p in unique)
    assert titles == ["Data Scientist", "Product Designer", "Staff Software Engineer"]


def test_dedup_keeps_first_occurrence():
    postings = _acme_postings()
    unique = deduplicate(postings)

    # The shared role first appears via Greenhouse, so that copy is the one kept.
    staff = [p for p in unique if p.title == "Staff Software Engineer"]
    assert len(staff) == 1
    assert staff[0].source == "greenhouse"
