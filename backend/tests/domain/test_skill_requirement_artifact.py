"""Synthetic P7.3 envelope validation; no real skill or level assertions."""

import json

import pytest
from pydantic import ValidationError

from competition_copilot.domain.skill import Skill
from competition_copilot.domain.skill_requirement_artifact import (
    SkillRequirementSetEnvelope,
)


def artifact_data(*, edition_id="synthetic-edition", track_id=None, coverage="partial"):
    """Explicitly synthetic reviewed facts, never production competition data."""
    return {
        "schema_version": "1.0", "artifact_type": "skill_requirement_set",
        "requirement_version": "synthetic-v1", "review_note": "Test-only review assessment.",
        "skills": [Skill(id="synthetic-skill", name="Synthetic Skill").model_dump()],
        "requirement_set": {
            "target": {
                "competition_id": "synthetic-competition", "edition_id": edition_id,
                "track_id": track_id, "scope": "track" if track_id else "edition",
            },
            "coverage": coverage, "coverage_note": "Test-only system coverage assessment.",
            "requirements": [{
                "skill_id": "synthetic-skill", "required_level": "intermediate",
                "requirement_type": "required", "evidence": [{
                    "code": "SYNTHETIC_REQUIREMENT", "message": "Test-only exact level fact.",
                    "field": "requirements.synthetic-skill.required_level", "value": "intermediate",
                    "source": {
                        "source_url": "https://example.org/synthetic-official-requirement",
                        "source_type": "official", "observed_at": "2026-01-01T00:00:00Z",
                        "verification_status": "verified",
                    },
                }],
            }],
        },
    }


@pytest.mark.parametrize("coverage", ["partial", "complete", "missing"])
def test_explicit_coverage_envelope_roundtrip_and_immutable_catalog(coverage):
    data = artifact_data(coverage=coverage)
    if coverage == "missing":
        data["skills"] = []
        data["requirement_set"]["requirements"] = []
    artifact = SkillRequirementSetEnvelope.model_validate(data)
    assert artifact.requirement_set.coverage.value == coverage
    assert artifact.model_dump(mode="json") == json.loads(artifact.model_dump_json())
    assert SkillRequirementSetEnvelope.model_validate_json(artifact.model_dump_json()) == artifact
    with pytest.raises(ValidationError, match="frozen"):
        artifact.requirement_version = "mutated"
    with pytest.raises(TypeError):
        artifact.model_copy(update={"requirement_version": "mutated"})
    with pytest.raises(AttributeError):
        artifact.skills.append(None)
    if artifact.skills:
        with pytest.raises(ValidationError, match="frozen"):
            artifact.skills[0].id = "other"
        assert isinstance(artifact.skills[0].aliases, tuple)


@pytest.mark.parametrize("field, value", [
    ("schema_version", "2.0"), ("artifact_type", "seed"),
    ("requirement_version", " "), ("review_note", ""),
    ("student_profile", {}), ("typo", True),
])
def test_strict_envelope_metadata_rejected(field, value):
    with pytest.raises(ValidationError):
        SkillRequirementSetEnvelope.model_validate(artifact_data() | {field: value})


@pytest.mark.parametrize("field, value", [
    ("competition_id", " "), ("edition_id", ""), ("track_id", " "),
    ("scope", "competition"), ("scope", "track"),
])
def test_invalid_exact_target_rejected(field, value):
    data = artifact_data()
    data["requirement_set"]["target"][field] = value
    with pytest.raises(ValidationError):
        SkillRequirementSetEnvelope.model_validate(data)


@pytest.mark.parametrize("field, value", [
    ("coverage", "automatic"), ("coverage", "missing"), ("coverage_note", " "),
])
def test_invalid_coverage_rejected(field, value):
    data = artifact_data()
    data["requirement_set"][field] = value
    with pytest.raises(ValidationError):
        SkillRequirementSetEnvelope.model_validate(data)


@pytest.mark.parametrize("field, value", [
    ("field", "skills.synthetic-skill.level"),
    ("field", "requirements.other.required_level"),
    ("field", None), ("value", "beginner"), ("value", None), ("source", None),
])
def test_invalid_requirement_fact_evidence_rejected(field, value):
    data = artifact_data()
    data["requirement_set"]["requirements"][0]["evidence"][0][field] = value
    with pytest.raises(ValidationError):
        SkillRequirementSetEnvelope.model_validate(data)


@pytest.mark.parametrize("field, value", [
    ("source_type", "manual"), ("verification_status", "pending"),
])
def test_artifact_requires_verified_official_source(field, value):
    data = artifact_data()
    data["requirement_set"]["requirements"][0]["evidence"][0]["source"][field] = value
    with pytest.raises(ValidationError):
        SkillRequirementSetEnvelope.model_validate(data)


@pytest.mark.parametrize("field, value", [
    ("required_level", "unknown"), ("required_level", "expert"),
    ("required_level", 0.8), ("requirement_type", "mandatory"),
])
def test_invalid_level_or_type_rejected(field, value):
    data = artifact_data()
    data["requirement_set"]["requirements"][0][field] = value
    with pytest.raises(ValidationError):
        SkillRequirementSetEnvelope.model_validate(data)


@pytest.mark.parametrize("catalog", [
    [], [{"id": "other", "name": "Other"}],
    [{"id": "synthetic-skill", "name": "X"}, {"id": "synthetic-skill", "name": "X"}],
])
def test_unresolved_or_duplicate_skill_identity_rejected(catalog):
    with pytest.raises(ValidationError):
        SkillRequirementSetEnvelope.model_validate(artifact_data() | {"skills": catalog})


def test_duplicate_requirement_rejected():
    data = artifact_data()
    data["requirement_set"]["requirements"] *= 2
    with pytest.raises(ValidationError, match="duplicate"):
        SkillRequirementSetEnvelope.model_validate(data)


def test_catalog_and_requirement_inputs_detached():
    data = artifact_data()
    data["skills"][0]["aliases"] = ["Synthetic Alias"]
    before = SkillRequirementSetEnvelope.model_validate(data)
    data["skills"][0]["aliases"].append("Changed")
    data["requirement_set"]["requirements"][0]["evidence"][0]["message"] = "Changed"
    assert before.skills[0].aliases == ("Synthetic Alias",)
    assert before.requirement_set.requirements[0].evidence[0].message != "Changed"
