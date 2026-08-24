"""Program gate (c): incremental refresh over a before/after pair yields exactly the new items.

'before' has 2 roles; 'after' re-lists those 2 and adds 1. Re-polling must surface exactly the
1 genuinely new posting — the already-seen ones stay quiet. We test both the pure `select_new`
and the full `SeenStore` round-trip (persistence across "runs").
"""

from __future__ import annotations

import json
from pathlib import Path

from zapply.ingest import GreenhouseSource, SeenStore, deduplicate, select_new

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _parse(name: str):
    gh = GreenhouseSource("Acme")
    return [gh.parse(j) for j in load_json(name)["jobs"]]


def test_select_new_returns_only_the_added_posting():
    before = deduplicate(_parse("incremental_before.json"))
    after = deduplicate(_parse("incremental_after.json"))

    seen = {p.dedup_key for p in before}
    new = select_new(after, seen)

    assert len(new) == 1
    assert new[0].title == "Data Scientist"


def test_seen_store_round_trip(tmp_path):
    store = SeenStore(tmp_path / "state.json")

    # First run: everything in 'before' is new, then persisted.
    before = deduplicate(_parse("incremental_before.json"))
    first_new = select_new(before, store.load())
    assert len(first_new) == 2
    store.save({p.dedup_key for p in before})

    # Second run over 'after': only the added posting is new.
    after = deduplicate(_parse("incremental_after.json"))
    second_new = select_new(after, store.load())
    assert len(second_new) == 1
    assert second_new[0].title == "Data Scientist"

    # Third run with no changes: nothing new.
    store.save(store.load() | {p.dedup_key for p in after})
    assert select_new(after, store.load()) == []
