"""Phase 3 program gate: does the matcher's ordering agree with my hand-ranking?

Loads one profile and 15 roles I ranked by true fit, scores every role against the profile with
the real local embedder, and asserts the Spearman correlation between the system's scores and my
gold ranking clears a threshold. Deterministic (embeddings are fixed for a given model), no API
cost — but the FIRST run downloads the ~80MB `all-MiniLM-L6-v2` model, so it needs network once.
"""

from __future__ import annotations

import json
from pathlib import Path

from zapply.extract.models import Profile, Requirements
from zapply.match import Matcher

from rank_metrics import spearman

FIXTURES = Path(__file__).parent / "fixtures"
THRESHOLD = 0.6


def _load():
    data = json.loads((FIXTURES / "ranking.json").read_text(encoding="utf-8"))
    profile = Profile.model_validate(data["profile"])
    jobs = [(j["gold_rank"], Requirements.model_validate(j["requirements"])) for j in data["jobs"]]
    return profile, jobs


def test_matching_ranks_correlate_with_labels(capsys):
    profile, jobs = _load()
    matcher = Matcher()

    scored = []
    for gold_rank, reqs in jobs:
        result = matcher.score(profile, reqs)
        scored.append((gold_rank, reqs.title, result.score))

    system_scores = [s for _, _, s in scored]
    gold_fit = [-gr for gr, _, _ in scored]  # higher fit = smaller gold_rank
    rho = spearman(system_scores, gold_fit)

    with capsys.disabled():
        print(f"\n[Phase 3 gate] Spearman rho = {rho:.3f} (threshold {THRESHOLD})")
        for gold_rank, title, score in sorted(scored, key=lambda t: -t[2]):
            print(f"  gold#{gold_rank:<2d} score {score:3d}  {title}")

    assert rho >= THRESHOLD, f"rank correlation {rho:.3f} < threshold {THRESHOLD}"
