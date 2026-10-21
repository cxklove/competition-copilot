"""Offline data foundation checks; overlap is identity only, never a score."""

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from competition_copilot.application.eligibility import CompetitionEligibilityEvaluator
from competition_copilot.domain.skill_requirement_artifact import (
    SkillRequirementSetEnvelope,
)
from competition_copilot.domain.student import StudentProfile
from competition_copilot.infrastructure.eligibility_policy_json import (
    JsonEligibilityPolicyProvider,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.infrastructure.skill_requirement_json import (
    JsonSkillRequirementProvider,
)

ROOT = Path(__file__).resolve().parents[3]


def data():
    fixture = json.loads((ROOT / "data/local_runtime/recommendation_demo.json").read_text(encoding="utf-8"))
    return fixture, StudentProfile.model_validate(fixture["profile"])


def provider():
    return JsonSkillRequirementProvider(ROOT / "data/skill_requirements")


def test_fixed_profile_explicit_fixture_stable_and_all_skills_resolve():
    fixture, profile = data()
    assert fixture["fixture_kind"] == "LOCAL DEMO FIXTURE"
    assert profile.id == "local-recommendation-demo"
    assert profile.skills and all("LOCAL DEMO FIXTURE" in s.note for s in profile.skills)
    assert profile == data()[1] == StudentProfile.model_validate_json(profile.model_dump_json())
    taxonomy = {skill.id for artifact in provider().list_artifacts() for skill in artifact.skills}
    assert {skill.skill_id for skill in profile.skills} <= taxonomy
    assert profile.skills[0].skill_id == "mathematical-modeling"


def test_curated_targets_verified_and_partial_requirements_keep_null_levels():
    fixture, _ = data()
    repository = JsonSeedCompetitionRepository(ROOT / "data/seed")
    requirements = provider()
    assert len(fixture["curated_candidates"]) == 4
    for candidate in fixture["curated_candidates"]:
        competition = repository.get_competition(candidate["competition_id"])
        edition = repository.get_edition(candidate["edition_id"])
        assert edition.competition_id == competition.id and candidate["track_id"] is None
        assert edition.source.verification_status == "verified"
        value = requirements.get_requirements(competition.id, edition.id)
        if value is None:
            continue  # No invention for candidates without reviewed artifacts.
        assert value.target.competition_id == competition.id and value.target.edition_id == edition.id
        assert value.target.track_id is None and value.coverage == "partial"
        ids = [r.skill_id for r in value.requirements]
        assert len(ids) == len(set(ids))
        for requirement in value.requirements:
            assert requirement.required_level is None and requirement.evidence == ()
            for fact in requirement.presence_evidence:
                assert fact.source.source_type == "official" and fact.source.verification_status == "verified"
                assert fact.field == f"requirements.{requirement.skill_id}.present" and fact.value is True
    assert requirements.get_requirements("gcxl-engineering-practice-innovation",
        "gcxl-engineering-practice-innovation-2027") is None
    assert requirements.get_requirements("unreviewed-candidate", "unreviewed-edition") is None
    # A name resembling an approved skill does not resolve as a target.
    assert requirements.get_requirements("mathematical-modeling", "machine-learning-modeling") is None


def test_existing_taxonomy_consistency_and_invalid_sources_or_duplicates_rejected():
    catalog = {}
    for artifact in provider().list_artifacts():
        assert SkillRequirementSetEnvelope.model_validate_json(artifact.model_dump_json()) == artifact
        for skill in artifact.skills:
            if skill.id in catalog:
                assert skill == catalog[skill.id]
            catalog[skill.id] = skill
    artifact = provider().list_artifacts()[0].model_dump(mode="json")
    duplicate = json.loads(json.dumps(artifact))
    duplicate["requirement_set"]["requirements"] *= 2
    with pytest.raises(ValidationError, match="duplicate"):
        SkillRequirementSetEnvelope.model_validate(duplicate)
    artifact["requirement_set"]["requirements"][0]["presence_evidence"][0]["source"]["verification_status"] = "pending"
    with pytest.raises(ValidationError):
        SkillRequirementSetEnvelope.model_validate(artifact)


@pytest.mark.parametrize("student,expected", [("local-undergraduate", "unknown"),
    ("local-graduate", "ineligible"), ("local-unknown", "unknown"),
    ("local-recommendation-demo", "unknown")])
def test_real_runtime_profiles_preserve_p5_and_only_explicit_skill_overlap_scores(student, expected):
    pytest.importorskip("langgraph")
    from competition_copilot.integrations.local_runtime.composition import (
        create_local_host,
    )

    target = {"student_id": student, "competition_id": "gcxl-engineering-practice-innovation",
              "edition_id": "gcxl-engineering-practice-innovation-2027"}
    host = create_local_host(ROOT)
    def invoke(message):
        return asyncio.run(host.invoke({"request": {"request_id": "fixture-" + message,
            "user_message": message, "context": target}}))
    eligibility = invoke("eligibility")
    assert eligibility["runtime"]["response"]["outcome"] == "COMPLETED"
    assert next(a["value"] for a in eligibility["presentation"]["artifacts"]
                if a["model"] == "EligibilityDecision")["status"] == expected
    result = invoke("recommend")
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    ranking = next(a["value"] for a in result["presentation"]["artifacts"]
                   if a["model"] == "RecommendationRankingResult")
    evaluations = [r["evaluation"] for bucket in ("confirmed", "uncertain") for r in ranking[bucket]] + ranking["blocked"]
    assert len(evaluations) == 12
    matched = {"comap-mcm", "china-graduate-math-modeling"}
    for evaluation in evaluations:
        should_score = student == "local-recommendation-demo" and evaluation["candidate"]["competition_id"] in matched
        assert evaluation["suitability_score"] == (1.0 if should_score else None)
        assert len(evaluation["score_components"]) == (1 if should_score else 0)
        if should_score:
            assert evaluation["status"] == "eligibility_uncertain"
            assert evaluation["score_components"][0]["component_id"] == "verified-skill-overlap-v1"


def test_curated_demo_p5_remains_uncertain_and_overlap_is_not_an_eligibility_grant():
    fixture, profile = data()
    repository = JsonSeedCompetitionRepository(ROOT / "data/seed")
    evaluator = CompetitionEligibilityEvaluator(repository, JsonEligibilityPolicyProvider(ROOT / "data/eligibility"))
    for candidate in fixture["curated_candidates"]:
        assert evaluator.evaluate(profile, **candidate).status == "unknown"


def test_exact_approved_scope_three_curated_facts_and_overlap_not_scoring():
    review = ROOT / "data/review/p6-skill-route"
    assert "APPROVE both facts and the new Skill ID" in (review / "README.md").read_text(encoding="utf-8")
    assert not list(review.glob("*.json"))
    fixture, profile = data()
    present = {s.skill_id for s in profile.skills}
    overlap = {}
    for candidate in fixture["curated_candidates"]:
        requirements = provider().get_requirements(**candidate)
        if requirements is not None:
            overlap[candidate["competition_id"]] = present & {r.skill_id for r in requirements.requirements}
    assert overlap == {"comap-mcm": {"mathematical-modeling"},
        "china-graduate-math-modeling": {"mathematical-modeling"}, "c4-big-data-challenge": set()}
    # Empty intersection is missing profile evidence, never known zero proficiency.
    artifacts = {a.requirement_set.target.competition_id: a for a in provider().list_artifacts()}
    for identity, skill in (("c4-big-data-challenge", "machine-learning-modeling"),
                            ("china-graduate-math-modeling", "mathematical-modeling")):
        artifact = artifacts[identity]
        assert "HUMAN DECISION: APPROVE" in artifact.review_note
        assert artifact.requirement_version == "1.0"
        assert [r.skill_id for r in artifact.requirement_set.requirements] == [skill]
        assert len(artifact.skills) == 1
    new_skill = artifacts["c4-big-data-challenge"].skills[0]
    assert new_skill.id == "machine-learning-modeling" and new_skill.aliases == ()
    assert "distinct from mathematical modeling" in new_skill.description
