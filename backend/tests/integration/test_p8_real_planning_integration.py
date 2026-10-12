"""Reviewed COMAP requirements to baseline plans with TEST-ONLY SYNTHETIC students.

Every service in the real P7/P8 chain runs; no requirement, need or plan is
manually substituted. No deadline selection, resources or adaptive planning.
"""

import json
import socket
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from competition_copilot.domain.baseline_plan_builder import (
    BaselineCompetitionPlanBuilder,
)
from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.plan import (
    CompetitionPlan,
    PlanningNeed,
    PlanningNeedType,
)
from competition_copilot.domain.planning_inputs import PlanningInputDeriver
from competition_copilot.domain.skill import SkillLevel, StudentSkill
from competition_copilot.domain.skill_gap import (
    SkillFactRole,
    SkillGapContext,
    SkillGapDecision,
    SkillGapItemStatus,
    SkillGapReasonCode,
    SkillGapStatus,
    SkillRequirementCoverage,
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
# Explicit test creation metadata, unrelated to official observation/deadlines.
CREATED_AT = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def offline_read_only_data_boundary(monkeypatch):
    original_open = Path.open

    def guarded_open(path, mode="r", *args, **kwargs):
        resolved = path.resolve()
        if resolved.is_relative_to(ROOT / "data"):
            assert any(resolved.is_relative_to(root) for root in (SEED_DIR, REQUIREMENT_DIR))
            assert mode in ("r", "rb")
        return original_open(path, mode, *args, **kwargs)

    def reject_network(*args, **kwargs):
        pytest.fail("P8.4 integration must run offline")

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(socket.socket, "connect", reject_network)
    files = tuple(SEED_DIR.glob("*.json")) + tuple(REQUIREMENT_DIR.glob("*.json"))
    before = {path: path.read_bytes() for path in files}
    yield
    assert {path: path.read_bytes() for path in files} == before


@pytest.fixture
def real_inputs():
    repository = JsonSeedCompetitionRepository(SEED_DIR)
    provider = JsonSkillRequirementProvider(REQUIREMENT_DIR)
    competition = repository.get_competition("comap-mcm")
    edition = repository.get_edition("comap-mcm-2027")
    assert edition.competition_id == competition.id
    requirements = provider.get_requirements(competition.id, edition.id, None)
    assert requirements is not None
    assert requirements.target.competition_id == competition.id
    assert requirements.target.edition_id == edition.id
    assert requirements.target.track_id is None
    assert requirements.target.scope.value == "edition"
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
        assert fact.source.observed_at.utcoffset() is not None
        assert str(fact.source.source_url) == (
            "https://contest.comap.com/undergraduate/contests/mcm/instructions.php"
        )
    return competition, edition, requirements


def run_pipeline(real_inputs, known_student, services):
    competition, edition, requirements = real_inputs
    engine, deriver, builder = services
    student = StudentProfile(
        id="test-only-synthetic-student-a" if known_student else "test-only-synthetic-student-b",
        skills=[StudentSkill(skill_id=SKILL_ID, level=SkillLevel.ADVANCED)] if known_student else [],
    )
    student_evidence = (Evidence(
        code="TEST_ONLY_SYNTHETIC_STUDENT_LEVEL",
        message="TEST-ONLY SYNTHETIC student fact supplied by the integration fixture.",
        field=skill_fact_field(SkillFactRole.STUDENT_SKILL, SKILL_ID),
        value=skill_fact_value(SkillLevel.ADVANCED),
    ),) if known_student else ()
    context = SkillGapContext(
        competition=competition, edition=edition, track=None, requirements=requirements,
        student_profile=student, student_skill_evidence=student_evidence,
    )
    inputs = (competition, edition, requirements, student, *student_evidence, context)
    before = tuple(model.model_dump_json() for model in inputs)
    decision = engine.evaluate(context)
    decision_before = decision.model_dump_json()
    needs = deriver.derive(decision)
    source_audit = deriver.source_audit(decision)
    needs_before = tuple(need.model_dump_json() for need in needs)
    audit_before = source_audit.model_dump_json()
    plan = builder.build(
        target=requirements.target, planning_needs=needs, student_id=student.id,
        created_at=CREATED_AT, source_audit=source_audit, planning_horizon=None,
    )
    assert tuple(model.model_dump_json() for model in inputs) == before
    assert decision.model_dump_json() == decision_before
    assert tuple(need.model_dump_json() for need in needs) == needs_before
    assert source_audit.model_dump_json() == audit_before
    return context, decision, needs, plan


@pytest.mark.parametrize("known_student", [True, False], ids=["student-a-known", "student-b-missing"])
def test_reviewed_comap_uncertainty_survives_real_planning_chain(real_inputs, known_student):
    services = SkillGapEngine(), PlanningInputDeriver(), BaselineCompetitionPlanBuilder()
    context, decision, needs, plan = run_pipeline(real_inputs, known_student, services)
    requirement = next(r for r in context.requirements.requirements if r.skill_id == SKILL_ID)
    item = next(i for i in decision.items if i.requirement.skill_id == SKILL_ID)
    assert item.status is SkillGapItemStatus.UNKNOWN
    assert item.requirement == requirement
    assert item.requirement.required_level is None
    assert item.requirement.evidence == ()
    assert decision.gap_status is SkillGapStatus.UNDETERMINED
    assert decision.requirements.coverage is SkillRequirementCoverage.PARTIAL
    expected_reasons = (SkillGapReasonCode.REQUIREMENT_PROFICIENCY_UNSPECIFIED,)
    if known_student:
        assert context.student_profile.skills[0].skill_id == SKILL_ID
        assert item.student_level is SkillLevel.ADVANCED
        assert item.student_evidence == context.student_skill_evidence
        assert item.student_evidence[0].field == skill_fact_field(SkillFactRole.STUDENT_SKILL, SKILL_ID)
        assert item.student_evidence[0].value == skill_fact_value(SkillLevel.ADVANCED)
        assert SkillGapReasonCode.STUDENT_SKILL_DATA_MISSING not in item.reason_codes
    else:
        assert not any(s.skill_id == SKILL_ID for s in context.student_profile.skills)
        assert context.student_skill_evidence == ()
        assert item.student_level is None
        assert item.student_evidence == ()
        expected_reasons += (SkillGapReasonCode.STUDENT_SKILL_DATA_MISSING,)
    assert item.reason_codes == expected_reasons
    skill_needs = [n for n in needs if n.source_item is not None and n.source_item.requirement.skill_id == SKILL_ID]
    assert len(skill_needs) == 1  # One need for this item, not a global artifact count.
    skill_need = skill_needs[0]
    assert skill_need.kind is PlanningNeedType.UNCERTAINTY_RESOLUTION
    assert skill_need.reason_codes == expected_reasons
    assert skill_need.source_item == item
    coverage_needs = [n for n in needs if n.source_item is None]
    assert len(coverage_needs) == 1
    coverage_need = coverage_needs[0]
    assert coverage_need.kind is PlanningNeedType.UNCERTAINTY_RESOLUTION
    assert coverage_need.reason_codes == (SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE,)
    assert not any(n.kind is PlanningNeedType.SKILL_IMPROVEMENT for n in needs)

    assert (plan.competition_id, plan.edition_id, plan.track_id) == ("comap-mcm", "comap-mcm-2027", None)
    assert plan.planning_horizon is None
    assert plan.planning_needs == needs
    assert plan.skill_gap_audit.target == context.requirements.target
    assert plan.skill_gap_audit.coverage is SkillRequirementCoverage.PARTIAL
    assert plan.skill_gap_audit.gap_status == decision.gap_status
    assert plan.skill_gap_audit.reason_codes == decision.reason_codes
    assert len(plan.milestones) == len(needs)
    assert [m.source_need_id for m in plan.milestones] == [n.id for n in needs]
    linked_needs = {n.id: n for n in plan.planning_needs}
    skill_milestone = next(m for m in plan.milestones if m.source_need_id == skill_need.id)
    coverage_milestone = next(m for m in plan.milestones if m.source_need_id == coverage_need.id)
    assert skill_milestone.title == "Resolve planning uncertainty for skill: " + SKILL_ID
    assert coverage_milestone.title == "Resolve competition requirement uncertainty"
    assert linked_needs[skill_milestone.source_need_id].source_item == item
    assert linked_needs[coverage_milestone.source_need_id].source_item is None
    for milestone in plan.milestones:
        assert linked_needs[milestone.source_need_id].kind is PlanningNeedType.UNCERTAINTY_RESOLUTION
        assert milestone.start_at is milestone.due_at is milestone.estimated_hours is None
        assert milestone.description is None
        assert milestone.dependency_ids == ()
    plan_item = linked_needs[skill_milestone.source_need_id].source_item
    assert plan_item.requirement.presence_evidence == requirement.presence_evidence
    assert plan_item.student_evidence == item.student_evidence
    assert plan_item.reason_codes == expected_reasons
    # System analysis audit remains source-free, separate from official facts.
    assert all(e.source is None for e in decision.audit_evidence)
    for model in (decision, *needs, plan):
        assert model.model_dump(mode="json") == json.loads(model.model_dump_json())
        assert type(model).model_validate_json(model.model_dump_json()) == model
    assert SkillGapDecision.model_validate_json(decision.model_dump_json()) == decision
    assert CompetitionPlan.model_validate_json(plan.model_dump_json()) == plan
    assert PlanningNeed.model_validate_json(skill_need.model_dump_json()) == skill_need
    payload = plan.model_dump(mode="json")
    assert payload["track_id"] is None
    assert payload["planning_horizon"] is None
    assert payload["skill_gap_audit"]["coverage"] == "partial"
    serialized_need = next(n for n in payload["planning_needs"] if n["id"] == skill_need.id)
    assert serialized_need["source_item"]["requirement"]["required_level"] is None
    assert serialized_need["reason_codes"] == [reason.value for reason in expected_reasons]
    assert serialized_need["source_item"]["requirement"]["presence_evidence"] == [
        e.model_dump(mode="json") for e in requirement.presence_evidence
    ]
    with pytest.raises(ValidationError):
        decision.gap_status = SkillGapStatus.NO_GAP
    with pytest.raises(ValidationError):
        skill_need.kind = PlanningNeedType.SKILL_IMPROVEMENT
    with pytest.raises(ValidationError):
        plan.track_id = "fake-track"
    with pytest.raises(ValidationError):
        skill_milestone.title = "changed"
    with pytest.raises(AttributeError):
        plan.milestones.append(skill_milestone)
    repeat = run_pipeline(real_inputs, known_student, services)
    assert decision.model_dump_json() == repeat[1].model_dump_json()
    assert tuple(n.model_dump_json() for n in needs) == tuple(n.model_dump_json() for n in repeat[2])
    assert plan.id == repeat[3].id
    assert [m.id for m in plan.milestones] == [m.id for m in repeat[3].milestones]
    assert plan.model_dump_json() == repeat[3].model_dump_json()


def test_reused_services_have_no_cross_student_state(real_inputs):
    services = SkillGapEngine(), PlanningInputDeriver(), BaselineCompetitionPlanBuilder()
    first_a = run_pipeline(real_inputs, True, services)
    before_a = first_a[3].model_dump_json()
    first_b = run_pipeline(real_inputs, False, services)
    second_a = run_pipeline(real_inputs, True, services)
    fresh_b = run_pipeline(real_inputs, False, (
        SkillGapEngine(), PlanningInputDeriver(), BaselineCompetitionPlanBuilder(),
    ))
    assert first_a[3].model_dump_json() == before_a == second_a[3].model_dump_json()
    assert first_b[3].model_dump_json() == fresh_b[3].model_dump_json()
    a_item = next(i for i in first_a[1].items if i.requirement.skill_id == SKILL_ID)
    b_item = next(i for i in first_b[1].items if i.requirement.skill_id == SKILL_ID)
    assert a_item.student_level is SkillLevel.ADVANCED
    assert b_item.student_level is None and b_item.student_evidence == ()


def test_missing_real_requirement_target_and_wrong_queries_have_no_fallback():
    repository = JsonSeedCompetitionRepository(SEED_DIR)
    provider = JsonSkillRequirementProvider(REQUIREMENT_DIR)
    missing = next(e for e in repository.list_editions()
                   if provider.get_requirements(e.competition_id, e.id, None) is None)
    assert repository.get_competition(missing.competition_id).id == missing.competition_id
    assert repository.get_edition(missing.id).competition_id == missing.competition_id
    assert provider.get_requirements(missing.competition_id, missing.id, None) is None
    for query in (
        ("not-a-competition", "comap-mcm-2027", None),
        ("comap-mcm", "not-an-edition", None),
        ("comap-mcm", "comap-mcm-2027", "not-a-track"),
    ):
        assert provider.get_requirements(*query) is None
