"""The pipeline's stages, modelled as distinct agents with clear contracts.

Each agent does one job and has a typed input → output. Composing them (not entangling them) is
what makes the pipeline legible and the handoffs checkable. The agents are injected into the
`Pipeline`, so the eval can swap in deterministic stubs and the real ones stay untested-by-network.

The ordering embodies the cost strategy: **prefilter** is a cheap *local* embedding rank over ALL
postings; only the top-K survivors reach **extract** and **draft**, which cost LLM calls. This is
what keeps a 1,000-posting feed inside a 20-calls/day budget.
"""

from __future__ import annotations

from typing import Protocol

from ..draft.drafter import draft as draft_fn
from ..draft.faithfulness import FaithfulnessReport, check_draft
from ..draft.models import DraftPacket
from ..extract import extract_requirements
from ..extract.models import Requirements
from ..ingest.models import JobPosting
from ..llm import LLMClient
from ..match.embed import Embedder, cosine
from ..match.matcher import MatchResult, Matcher
from ..match.represent import profile_to_text, requirements_to_text
from ..extract.models import Profile


# -- contracts -----------------------------------------------------------------


class PrefilterAgentProto(Protocol):
    def run(self, profile: Profile, postings: list[JobPosting]) -> list[tuple[JobPosting, float]]: ...


class ExtractAgentProto(Protocol):
    def run(self, posting: JobPosting) -> Requirements: ...


class MatchAgentProto(Protocol):
    def run(self, profile: Profile, requirements: Requirements) -> MatchResult: ...


class DraftAgentProto(Protocol):
    def run(self, profile: Profile, requirements: Requirements) -> tuple[DraftPacket, FaithfulnessReport]: ...


# -- real implementations ------------------------------------------------------


class PrefilterAgent:
    """Cheap, LOCAL embedding rank over every posting — no LLM. Narrows to a shortlist."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or Embedder()

    def run(self, profile: Profile, postings: list[JobPosting]) -> list[tuple[JobPosting, float]]:
        if not postings:
            return []
        p_vec = self.embedder.encode_one(profile_to_text(profile))
        texts = [f"{p.title}\n{p.description[:2000]}" for p in postings]
        vecs = self.embedder.encode(texts)
        scored = [(post, cosine(p_vec, v)) for post, v in zip(postings, vecs)]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored


class ExtractAgent:
    """JobPosting → structured Requirements (LLM). Fills company/title from the posting if blank."""

    def __init__(self, client: LLMClient | None = None, backend: str = "native") -> None:
        self.client = client
        self.backend = backend

    def run(self, posting: JobPosting) -> Requirements:
        text = f"{posting.title}\n\n{posting.description}"
        reqs = extract_requirements(text, backend=self.backend, client=self.client)
        if not reqs.company:
            reqs.company = posting.company
        if not reqs.title:
            reqs.title = posting.title
        return reqs


class MatchAgent:
    """(Profile, Requirements) → MatchResult (local embeddings)."""

    def __init__(self, matcher: Matcher | None = None) -> None:
        self.matcher = matcher or Matcher()

    def run(self, profile: Profile, requirements: Requirements) -> MatchResult:
        return self.matcher.score(profile, requirements)


class DraftAgent:
    """(Profile, Requirements) → grounded DraftPacket + its faithfulness report (LLM + program)."""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client

    def run(self, profile: Profile, requirements: Requirements) -> tuple[DraftPacket, FaithfulnessReport]:
        packet = draft_fn(profile, requirements, client=self.client)
        report = check_draft(packet, profile, requirements)
        return packet, report
