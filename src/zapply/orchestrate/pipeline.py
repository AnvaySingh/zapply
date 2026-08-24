"""Compose the agents into one pipeline, with contracts enforced at every handoff.

"No stage silently passing bad data" is a program, not a hope: after each stage the pipeline
asserts the handoff is well-formed and raises `PipelineError` otherwise. The result is a list of
`Application`s, each either `pending_review` (faithful, awaiting the human) or `blocked` (failed
the program faithfulness gate, so the human is never even offered it).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..extract.models import Profile, Requirements
from ..ingest.models import JobPosting
from ..match.matcher import MatchResult
from .agents import (
    DraftAgent,
    DraftAgentProto,
    ExtractAgent,
    ExtractAgentProto,
    MatchAgent,
    MatchAgentProto,
    PrefilterAgent,
    PrefilterAgentProto,
)
from .models import Application, ApplicationStatus


class PipelineError(RuntimeError):
    """Raised when a stage hands off malformed data to the next."""


@dataclass
class PipelineConfig:
    top_k: int = 3  # how many prefiltered postings get the (expensive) extract + draft treatment


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PipelineError(message)


class Pipeline:
    def __init__(
        self,
        prefilter: PrefilterAgentProto,
        extractor: ExtractAgentProto,
        matcher: MatchAgentProto,
        drafter: DraftAgentProto,
    ) -> None:
        self.prefilter = prefilter
        self.extractor = extractor
        self.matcher = matcher
        self.drafter = drafter

    def run(
        self, profile: Profile, postings: list[JobPosting], config: PipelineConfig | None = None
    ) -> list[Application]:
        config = config or PipelineConfig()

        ranked = self.prefilter.run(profile, postings)
        _require(isinstance(ranked, list), "prefilter must return a ranked list")
        shortlist = ranked[: config.top_k]

        applications: list[Application] = []
        for posting, pre_score in shortlist:
            requirements = self.extractor.run(posting)
            self._check_requirements(requirements, posting)

            match = self.matcher.run(profile, requirements)
            self._check_match(match)

            packet, report = self.drafter.run(profile, requirements)
            _require(packet is not None, f"drafter returned no packet for {posting.title!r}")

            status = (
                ApplicationStatus.pending_review if report.is_faithful else ApplicationStatus.blocked
            )
            applications.append(
                Application(
                    posting=posting,
                    prefilter_score=float(pre_score),
                    requirements=requirements,
                    match=match,
                    draft=packet,
                    faithfulness=report,
                    status=status,
                )
            )
        return applications

    # -- handoff contracts -----------------------------------------------------

    @staticmethod
    def _check_requirements(requirements: Requirements, posting: JobPosting) -> None:
        _require(
            isinstance(requirements, Requirements),
            f"extractor did not return Requirements for {posting.title!r}",
        )
        _require(
            bool(requirements.title and requirements.title.strip()),
            f"extracted Requirements has empty title for {posting.title!r}",
        )

    @staticmethod
    def _check_match(match: MatchResult) -> None:
        _require(isinstance(match, MatchResult), "matcher did not return a MatchResult")
        _require(0 <= match.score <= 100, f"match score out of range: {match.score}")


def default_pipeline(client=None, backend: str = "native") -> Pipeline:
    """The real pipeline: local prefilter/match + LLM extract/draft."""
    return Pipeline(
        prefilter=PrefilterAgent(),
        extractor=ExtractAgent(client=client, backend=backend),
        matcher=MatchAgent(),
        drafter=DraftAgent(client=client),
    )
