"""Small, dependency-free text helpers shared by the ingest adapters.

Job boards hand us HTML descriptions and inconsistently-cased fields. Two jobs are keeping
this tidy: turn HTML into readable plain text, and produce a *normalised key* so the same role
from two feeds collapses to one.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    """Collect text nodes, insert breaks for block-level tags. Stdlib only — no bs4."""

    _BLOCK = {"p", "br", "li", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in self._BLOCK:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def strip_html(raw: str | None) -> str:
    """Convert an HTML (or HTML-escaped) blob into collapsed plain text."""
    if not raw:
        return ""
    # Greenhouse double-escapes: the payload is HTML entities wrapping real HTML.
    unescaped = html.unescape(raw)
    parser = _TextExtractor()
    parser.feed(unescaped)
    text = parser.text()
    # Collapse runs of blank lines / whitespace into something readable.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*", "\n\n", text)
    return text.strip()


def normalise_key_part(value: str | None) -> str:
    """Lowercase, strip punctuation, collapse whitespace — for building dedup keys."""
    if not value:
        return ""
    lowered = value.casefold().strip()
    lowered = re.sub(r"[^\w\s]", " ", lowered)  # drop punctuation
    return re.sub(r"\s+", " ", lowered).strip()


def dedup_key(company: str, title: str, location: str | None) -> str:
    """The canonical identity of a posting: same (company, title, location) → same key.

    Location is included so two genuinely different roles that happen to share a title don't
    collapse. The tradeoff (a role listed as "Remote" on one feed and "Remote - US" on another
    would not collapse) is documented in NOTES.md.
    """
    return "::".join(
        (normalise_key_part(company), normalise_key_part(title), normalise_key_part(location))
    )
