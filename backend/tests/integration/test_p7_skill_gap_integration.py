"""Real reviewed competition requirements with TEST-ONLY SYNTHETIC students.

Only Repository Seed and Requirement Provider artifacts are read. No source
collection, eligibility, recommendation, application service or planning runs.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.skill import SkillLevel, StudentSkill
from competition_copilot.domain.skill_gap import (
    SkillFactRole,
    SkillGapContext,
    SkillGapDecision,
    SkillGapItemStatus,
    SkillGapReasonCode,
    SkillGapStatus,
    SkillRequirementCoverage,
    SkillRequirementScope,
    SkillRequirementType,
    requirement_presence_field,
    skill_fact_field,
    skill_fact_value,
)
from competition_copilot.domain.skill_gap_engine import SkillGapEngine
from competition_copilot.domain.student import StudentProfile
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.infrastructure.skill_requirement_json import (
    JsonSkillRequirementProvider,
)

ROOT = Path(__file__).resolve().parents[3]
SEED_DIR = ROOT / "data" / "seed"
REQUIREMENT_DIR = ROOT / "data" / "skill_requirements"
SKILL_ID = "mathematical-modeling"


@pytest.fixture(autouse=True)
def restrict_data_reads_to_integration_inputs(monkeypatch):
    """Reject Raw, Manifest, eligibility-policy reads or writes in this chain."""
    original_open = Path.open

    def guarded_open(path, mode="r", *args, **kwargs):
        resolved = path.resolve()
        # Domain timezone validation may read installed tzdata outside project
        # data. Restrict business artifacts without blocking library resources.
        if resolved.is_relative_to(ROOT / "data"):
            assert any(resolved.is_relative_to(root) for root in (SEED_DIR, REQUIREMENT_DIR))
            assert mode in ("r", "rb")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)


@pytest.mark.parametrize("known_student", [True, False], ids=["student-a-known", "student-b-missing"])
def test_real_comap_skill_gap_preserves_uncertainty_and_audit(known_student):
    files = tuple(SEED_DIR.glob("*.json")) + tuple(REQUIREMENT_DIR.glob("*.json"))
    file_snapshots = {path: path.read_bytes() for path in files}
    repository = JsonSeedCompetitionRepository(SEED_DIR)
    provider = JsonSkillRequirementProvider(REQUIREMENT_DIR)
    competition = repository.get_competition("comap-mcm")
    edition = repository.get_edition("comap-mcm-2027")
    assert edition.competition_id == competition.id
    requirements = provider.get_requirements(competition.id, edition.id, None)
    assert requirements is not None
    target = requirements.target
    assert (target.competition_id, target.edition_id, target.track_id) == (
        competition.id, edition.id, None
    )
    assert target.scope is SkillRequirementScope.EDITION
    assert requirements.coverage is SkillRequirementCoverage.PARTIAL
    requirement = next(r for r in requirements.requirements if r.skill_id == SKILL_ID)
    assert requirement.requirement_type is SkillRequirementType.REQUIRED
    assert requirement.required_level is None
    assert requirement.evidence == ()
    assert requirement.presence_evidence
    for fact in requirement.presence_evidence:
        assert fact.field == requirement_presence_field(SKILL_ID)
        assert fact.value is True
        assert fact.source.source_type.value == "official"
        assert fact.source.verification_status.value == "verified"
        assert str(fact.source.source_url) == (
            "https://contest.comap.com/undergraduate/contests/mcm/instructions.php"
        )

    # These student facts originate solely in this test, not an official source
    # or a real student record. Canonical binding still follows the P7 contract.
    skills = [StudentSkill(skill_id=SKILL_ID, level=SkillLevel.ADVANCED)] if known_student else []
    student = StudentProfile(id="test-only-synthetic-student", skills=skills)
    student_evidence = (Evidence(
        code="TEST_ONLY_SYNTHETIC_STUDENT_LEVEL",
        message="TEST-ONLY SYNTHETIC student level supplied by the integration fixture.",
        field=skill_fact_field(SkillFactRole.STUDENT_SKILL, SKILL_ID),
        value=skill_fact_value(SkillLevel.ADVANCED),
    ),) if known_student else ()
    context = SkillGapContext(
        competition=competition,
        edition=edition,
        track=None,
        requirements=requirements,
        student_profile=student,
        student_skill_evidence=student_evidence,
    )
    inputs = (competition, edition, requirements, student, *student_evidence, context)
    before = tuple(model.model_dump_json() for model in inputs)
    engine = SkillGapEngine()
    decision = engine.evaluate(context)
    assert decision.model_dump_json() == engine.evaluate(context).model_dump_json()
    assert tuple(model.model_dump_json() for model in inputs) == before
    assert {path: path.read_bytes() for path in files} == file_snapshots
    assert provider.get_requirements(competition.id, edition.id, None) == requirements

    assert decision.target == target
    assert decision.requirements == requirements
    assert decision.requirements.coverage is SkillRequirementCoverage.PARTIAL
    assert decision.gap_status is SkillGapStatus.UNDETERMINED
    assert SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE in decision.reason_codes
    assert [i.requirement.skill_id for i in decision.items] == [
        r.skill_id for r in requirements.requirements
    ]
    item = next(i for i in decision.items if i.requirement.skill_id == SKILL_ID)
    assert item.requirement == requirement
    assert item.requirement.presence_evidence == requirement.presence_evidence
    assert item.status is SkillGapItemStatus.UNKNOWN
    expected_reasons = (SkillGapReasonCode.REQUIREMENT_PROFICIENCY_UNSPECIFIED,)
    if known_student:
        assert item.student_level is SkillLevel.ADVANCED
        assert item.student_evidence == context.student_skill_evidence
        assert tuple(e.model_dump(mode="json") for e in item.student_evidence) == tuple(
            e.model_dump(mode="json") for e in student_evidence
        )
        assert SkillGapReasonCode.STUDENT_SKILL_DATA_MISSING not in item.reason_codes
    else:
        assert item.student_level is None
        assert item.student_evidence == ()
        expected_reasons += (SkillGapReasonCode.STUDENT_SKILL_DATA_MISSING,)
    assert item.reason_codes == expected_reasons
    assert set(expected_reasons).issubset(decision.reason_codes)
    # Engine system audit is explicitly source-free; source facts above originate
    # in the artifact or test-supplied student input and remain separate.
    assert decision.audit_evidence
    assert all(e.source is None for e in decision.audit_evidence)
    payload = decision.model_dump(mode="json")
    assert payload == json.loads(decision.model_dump_json())
    serialized_item = next(i for i in payload["items"] if i["requirement"]["skill_id"] == SKILL_ID)
    assert serialized_item["requirement"]["required_level"] is None
    assert serialized_item["requirement"]["presence_evidence"] == [
        e.model_dump(mode="json") for e in requirement.presence_evidence
    ]
    assert serialized_item["reason_codes"] == [r.value for r in expected_reasons]
    assert SkillGapDecision.model_validate_json(decision.model_dump_json()) == decision
    with pytest.raises(ValidationError):
        decision.gap_status = SkillGapStatus.NO_GAP
    with pytest.raises(ValidationError):
        item.status = SkillGapItemStatus.SATISFIED


def test_other_real_target_has_no_requirement_fallback():
    repository = JsonSeedCompetitionRepository(SEED_DIR)
    provider = JsonSkillRequirementProvider(REQUIREMENT_DIR)
    missing_edition = next(
        edition for edition in repository.list_editions()
        if provider.get_requirements(edition.competition_id, edition.id, None) is None
    )
    assert repository.get_competition(missing_edition.competition_id).id == missing_edition.competition_id
    assert repository.get_edition(missing_edition.id).competition_id == missing_edition.competition_id
    assert provider.get_requirements(missing_edition.competition_id, missing_edition.id, None) is None
    # No application mapping exists here: absence is never replaced with an
    # invented COMPLETE requirement set or a NO_GAP decision.
    assert provider.get_requirements("comap-mcm", "comap-mcm-2027", "nonexistent-track") is None
