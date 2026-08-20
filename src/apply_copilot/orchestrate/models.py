"""The unit of work that flows through the pipeline: an Application.

An `Application` accumulates the output of every stage (requirements, match, draft, faithfulness)
for one posting, and carries a `status` that the review gate mutates. The status is the linchpin
of the maker-checker discipline: a packet can only be built from an `approved` Application, and an
Application can only be approved if it passed the (program) faithfulness gate first.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..draft.faithfulness import FaithfulnessReport
from ..draft.models import DraftPacket
from ..extract.models import Requirements
from ..ingest.models import JobPosting
from ..match.matcher import MatchResult


class ApplicationStatus(str, Enum):
    pending_review = "pending_review"  # awaiting the human
    approved = "approved"  # human said yes (only reachable if faithful)
    rejected = "rejected"  # human said no
    blocked = "blocked"  # failed the program faithfulness gate — human can't approve


@dataclass
class Application:
    posting: JobPosting
    prefilter_score: float
    requirements: Requirements
    match: MatchResult
    draft: DraftPacket
    faithfulness: FaithfulnessReport
    status: ApplicationStatus = ApplicationStatus.pending_review

    @property
    def is_faithful(self) -> bool:
        return self.faithfulness.is_faithful

    @property
    def label(self) -> str:
        return f"{self.requirements.company or self.posting.company} · {self.requirements.title}"
