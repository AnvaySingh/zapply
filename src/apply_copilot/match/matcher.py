"""Score a Profile against a role's Requirements, with a short rationale.

Two distinct signals, kept separate on purpose:

* **The score** is pure embedding cosine similarity, scaled to 0–100. This is the naive version
  the roadmap asks for — and keeping it pure is what makes the "cosine confidently lies" failure
  case (documented in NOTES.md) visible instead of papered over.
* **The rationale** is *programmatic*, not model-written: it reports concrete skill overlap,
  missing required skills, and seniority alignment computed from the structured fields. It's
  grounded by construction (every claim comes from the data), and it deliberately does NOT feed
  back into the score — so you can see when a high cosine score disagrees with a thin overlap.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..extract.models import Profile, Requirements
from ..ingest.text import normalise_key_part
from .embed import Embedder, cosine
from .represent import profile_to_text, requirements_to_text

_SENIORITY_RANK = {
    "intern": 0, "junior": 1, "mid": 2, "senior": 3,
    "lead": 4, "staff": 4, "principal": 5, "manager": 4, "director": 6,
}


@dataclass
class MatchResult:
    score: int  # 0–100, from embedding cosine similarity
    similarity: float  # raw cosine
    rationale: str
    overlapping_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    seniority_note: str = ""


class Matcher:
    """Embeds and scores a profile against requirements."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or Embedder()

    def score(self, profile: Profile, requirements: Requirements) -> MatchResult:
        p_vec = self.embedder.encode_one(profile_to_text(profile))
        r_vec = self.embedder.encode_one(requirements_to_text(requirements))
        sim = cosine(p_vec, r_vec)
        score = max(0, min(100, round(sim * 100)))

        overlap, missing = self._skill_overlap(profile, requirements)
        seniority_note = self._seniority_note(profile, requirements)
        rationale = self._rationale(score, overlap, missing, seniority_note)

        return MatchResult(
            score=score,
            similarity=sim,
            rationale=rationale,
            overlapping_skills=overlap,
            missing_skills=missing,
            seniority_note=seniority_note,
        )

    def rank(self, profile: Profile, roles: list[Requirements]) -> list[tuple[Requirements, MatchResult]]:
        scored = [(r, self.score(profile, r)) for r in roles]
        scored.sort(key=lambda pair: pair[1].score, reverse=True)
        return scored

    # -- programmatic rationale helpers ---------------------------------------

    @staticmethod
    def _skill_overlap(profile: Profile, reqs: Requirements) -> tuple[list[str], list[str]]:
        have = {normalise_key_part(s): s for s in profile.skills}
        overlap, missing = [], []
        for req_skill in reqs.required_skills:
            key = normalise_key_part(req_skill)
            if key in have:
                overlap.append(req_skill)
            else:
                missing.append(req_skill)
        return overlap, missing

    @staticmethod
    def _seniority_note(profile: Profile, reqs: Requirements) -> str:
        p = _SENIORITY_RANK.get(profile.seniority.value)
        r = _SENIORITY_RANK.get(reqs.seniority.value)
        if p is None or r is None:
            return "Seniority not comparable."
        if p >= r:
            return f"Seniority OK ({profile.seniority.value} ≥ {reqs.seniority.value})."
        return f"Seniority gap ({profile.seniority.value} < {reqs.seniority.value})."

    @staticmethod
    def _rationale(score: int, overlap: list[str], missing: list[str], seniority_note: str) -> str:
        bits = [f"Semantic match {score}/100."]
        if overlap:
            bits.append("Overlaps on " + ", ".join(overlap) + ".")
        if missing:
            bits.append("Missing required: " + ", ".join(missing) + ".")
        if not overlap and not missing:
            bits.append("No explicit required-skill list to compare.")
        bits.append(seniority_note)
        return " ".join(bits)
