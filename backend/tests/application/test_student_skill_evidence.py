"""Explicit fixture provenance, never inferred evidence for profile records."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from competition_copilot.application.student_skill_evidence import (
    StudentSkillEvidenceDeclaration,
    prepare_student_skill_evidence,
)
from competition_copilot.domain.skill_gap import SkillGapContext
from competition_copilot.domain.student import StudentProfile
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.infrastructure.skill_requirement_json import (
    JsonSkillRequirementProvider,
)

ROOT = Path(__file__).resolve().parents[3]


def fixture():
    data = json.loads((ROOT / "data/local_runtime/recommendation_demo.json").read_text(encoding="utf-8"))
    return StudentProfile.model_validate(data["profile"]), data["student_skill_evidence"]


def context(profile, evidence):
    repo = JsonSeedCompetitionRepository(ROOT / "data/seed")
    provider = JsonSkillRequirementProvider(ROOT / "data/skill_requirements")
    return SkillGapContext(student_profile=profile,
        competition=repo.get_competition("comap-mcm"), edition=repo.get_edition("comap-mcm-2027"),
        requirements=provider.get_requirements("comap-mcm", "comap-mcm-2027"),
        student_skill_evidence=evidence)


def test_explicit_fixture_fact_is_bound_and_stable_without_external_provenance():
    profile, raw = fixture()
    declarations = tuple(StudentSkillEvidenceDeclaration.model_validate(v) for v in raw)
    before = profile.model_dump_json()
    facts = prepare_student_skill_evidence(profile, declarations)
    assert facts == prepare_student_skill_evidence(profile, declarations)
    assert facts[0] is not declarations[0].evidence
    assert facts[0].source is None
    assert facts[0].field == "skills.mathematical-modeling.level"
    assert facts[0].value == "intermediate"
    for marker in ("student_id=local-recommendation-demo;", "skill_id=mathematical-modeling;",
                   "self_assessed=true;", "LOCAL DEMO FIXTURE"):
        assert marker in facts[0].message
    assert context(profile, facts).student_skill_evidence[0].source is None
    assert profile.model_dump_json() == before


def test_missing_explicit_evidence_is_not_generated_and_domain_still_rejects():
    profile, _ = fixture()
    assert prepare_student_skill_evidence(profile, ()) == ()
    with pytest.raises(ValidationError, match="known relevant student skill needs student evidence"):
        context(profile, ())


@pytest.mark.parametrize("change", [
    {"student_id": "another-student"},
    {"skill_id": "machine-learning-modeling"},
    {"self_assessed": False},
    {"evidence_change": {"field": "skills.machine-learning-modeling.level"}},
    {"evidence_change": {"value": "advanced"}},
    {"evidence_change": {"message": "Generic mathematical ability"}},
    {"evidence_change": {"source": {"source_url": "https://example.invalid/skill",
        "source_type": "official", "verification_status": "verified",
        "observed_at": "2026-10-21T00:00:00Z"}}},
])
def test_mismatched_or_falsely_verified_declarations_fail_closed(change):
    profile, raw = fixture()
    item = raw[0]
    if "evidence_change" in change:
        item["evidence"].update(change["evidence_change"])
    else:
        item.update(change)
    with pytest.raises(ValueError):
        prepare_student_skill_evidence(profile, (StudentSkillEvidenceDeclaration.model_validate(item),))


def test_unknown_or_absent_profile_skill_cannot_be_evidenced():
    profile, raw = fixture()
    declarations = (StudentSkillEvidenceDeclaration.model_validate(raw[0]),)
    for skills in ([], [{**profile.skills[0].model_dump(), "level": "unknown"}]):
        changed = StudentProfile.model_validate({**profile.model_dump(), "skills": skills})
        with pytest.raises(ValueError, match="existing known skill"):
            prepare_student_skill_evidence(changed, declarations)
