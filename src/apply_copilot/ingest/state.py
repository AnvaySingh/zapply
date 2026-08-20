"""Persistence of 'what we've already seen', so incremental refresh survives restarts.

Deliberately the naive version: a JSON file holding the set of canonical keys we've emitted.
No database. When (and only when) polling volume makes a flat file painful, this is the seam
where a real store would slot in — noted in NOTES.md. The pure `select_new` logic lives in
`dedup.py`; this class only handles load/save.
"""

from __future__ import annotations

import json
from pathlib import Path


class SeenStore:
    """A flat-file record of canonical posting keys already surfaced."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> set[str]:
        if not self.path.exists():
            return set()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return set()
        return set(data.get("seen_keys", []))

    def save(self, keys: set[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"seen_keys": sorted(keys)}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
