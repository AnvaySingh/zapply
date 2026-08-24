"""Offline, deterministic tests of the scoring instrument itself.

The Phase 2 gate trusts `scoring.py` to judge extraction against labels. Before trusting it on
live model output, we prove the measuring stick is correct on synthetic inputs. These run with
no LLM and no network, so they're part of the default `pytest` suite.
"""

from __future__ import annotations

from zapply.extract.models import Education, Experience, Profile, Seniority

from scoring import score_field, score_model


def test_scalar_and_contains():
    assert score_field("Jane Doe", {"kind": "scalar", "value": "jane doe"}) == 1.0
    assert score_field("X", {"kind": "scalar", "value": "Y"}) == 0.0
    assert score_field("Senior Backend Engineer", {"kind": "contains", "value": "Backend"}) == 1.0


def test_numeric_tolerance():
    assert score_field(6.5, {"kind": "numeric", "value": 7, "tol": 1}) == 1.0
    assert score_field(3, {"kind": "numeric", "value": 7, "tol": 1}) == 0.0
    assert score_field(None, {"kind": "numeric", "value": 7, "tol": 1}) == 0.0


def test_list_recall_is_partial_credit():
    assert score_field(["Python", "Go"], {"kind": "list", "value": ["Python", "Go"]}) == 1.0
    assert score_field(["Python"], {"kind": "list", "value": ["Python", "Go"]}) == 0.5
    assert score_field([], {"kind": "list", "value": ["Python", "Go"]}) == 0.0


def test_enum_matches_on_value():
    assert score_field(Seniority.senior, {"kind": "enum", "value": "senior"}) == 1.0
    assert score_field(Seniority.junior, {"kind": "enum", "value": "senior"}) == 0.0


def test_score_model_perfect_profile():
    profile = Profile(
        name="Jane Doe",
        email="jane@x.com",
        location="San Francisco, CA",
        seniority=Seniority.senior,
        years_experience=7,
        skills=["Python", "Go"],
        experiences=[Experience(company="Acme Corp", title="Engineer")],
        education=[Education(institution="MIT")],
    )
    labels = {
        "fields": {
            "name": {"kind": "scalar", "value": "Jane Doe"},
            "seniority": {"kind": "enum", "value": "senior"},
            "years_experience": {"kind": "numeric", "value": 7, "tol": 1},
            "skills": {"kind": "list", "value": ["python", "go"]},
            "companies": {"kind": "list", "value": ["Acme Corp"]},
            "institutions": {"kind": "list", "value": ["MIT"]},
        }
    }
    result = score_model(profile, labels)
    assert result.count == 6
    assert result.accuracy == 1.0
