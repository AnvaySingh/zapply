"""LLM-as-judge — a faithfulness *signal*, explicitly not the gate.

The judge reads the fact sheet and each generated claim and labels it supported / unsupported.
It's useful (it catches subtle drift the programmatic checker can't, like an invented metric),
but it is only a signal: the model judging model output is exactly the kind of loop the project
refuses to *close* with an opinion. The program (`check_draft`) is what passes or fails the phase.
One structured call judges all claims at once to stay within quota.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from apply_copilot.draft.context import build_fact_sheet
from apply_copilot.extract.instructor_impl import _client_and_model
from apply_copilot.extract.models import Profile


class Judgment(BaseModel):
    claim: str
    supported: bool = Field(description="True iff the claim is fully supported by the fact sheet.")
    reason: str = Field(description="Brief justification.")


class Judgments(BaseModel):
    judgments: list[Judgment]


_JUDGE_SYSTEM = (
    "You are a strict faithfulness auditor. Given a candidate's FACT SHEET and a list of claims "
    "written for their job application, decide for EACH claim whether it is fully supported by the "
    "fact sheet. A claim that names a skill, employer, credential, or metric not present in the "
    "fact sheet is UNSUPPORTED, even if plausible. Be conservative."
)


def judge_claims(profile: Profile, claims: list[str]) -> Judgments:
    # Uses instructor (JSON mode) — more reliable than forced tool-calling on Gemini for this shape.
    client, model = _client_and_model()
    fact_sheet = build_fact_sheet(profile)
    numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(claims))
    prompt = f"{fact_sheet}\n\n=== CLAIMS TO AUDIT ===\n{numbered}\n\nJudge every claim."
    return client.chat.completions.create(
        model=model,
        response_model=Judgments,
        max_retries=2,
        temperature=0.0,
        messages=[
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
    )
