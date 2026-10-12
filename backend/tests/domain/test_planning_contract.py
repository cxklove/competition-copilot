"""P8.1 synthetic contracts only: no planner, engine, repository or artifacts."""

import ast
import inspect
import json

import pytest
from pydantic import ValidationError

from competition_copilot.domain import plan as plan_module
from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.plan import (
    CompetitionPlan,
    PlanMilestone,
    PlanningNeed,
    PlanningNeedType,
    SkillGapPlanningAudit,
)
from competition_copilot.domain.skill import SkillLevel
from competition_copilot.domain.skill_gap import (
    SkillFactRole,
    SkillGapItem,
    SkillGapItemStatus,
    SkillGapReasonCode,
    SkillRequirement,
    SkillRequirementTarget,
    requirement_presence_field,
    skill_fact_field,
    skill_fact_value,
)
from competition_copilot.domain.temporal import TimeWindow

GAP_REASON = SkillGapReasonCode.SKILL_BELOW_REQUIREMENT
UNKNOWN_REASON = SkillGapReasonCode.REQUIREMENT_PROFICIENCY_UNSPECIFIED
PARTIAL_REASON = SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE
STAMP = "2026-10-12T10:00:00Z"


def source_item(status="gap", kind="required"):
    """Supplied validated P7 conclusion; no P8 proficiency comparison runs."""
    required = None if status == "unknown" else SkillLevel.INTERMEDIATE
    student = SkillLevel.BEGINNER if status == "gap" else SkillLevel.ADVANCED
    requirement = SkillRequirement(
        skill_id="synthetic-skill", required_level=required, requirement_type=kind,
        presence_evidence=[Evidence(
            code="TEST_ONLY_PRESENCE", message="Synthetic reviewed skill presence.",
            field=requirement_presence_field("synthetic-skill"), value=True,
            source={"source_url": "https://example.org/test", "source_type": "manual",
                    "observed_at": STAMP, "verification_status": "verified"},
        )],
        evidence=[] if required is None else [Evidence(
            code="TEST_ONLY_THRESHOLD", message="Synthetic reviewed threshold.",
            field=skill_fact_field(SkillFactRole.REQUIREMENT, "synthetic-skill"),
            value=skill_fact_value(required),
            source={"source_url": "https://example.org/test", "source_type": "manual",
                    "observed_at": STAMP, "verification_status": "verified"},
        )],
    )
    reason = {"gap": GAP_REASON, "unknown": UNKNOWN_REASON,
              "satisfied": SkillGapReasonCode.REQUIREMENT_SATISFIED}[status]
    return SkillGapItem(
        requirement=requirement, student_level=student, status=status,
        reason_codes=(reason,), student_evidence=[Evidence(
            code="TEST_ONLY_STUDENT", message="Synthetic supplied student fact.",
            field=skill_fact_field(SkillFactRole.STUDENT_SKILL, "synthetic-skill"),
            value=skill_fact_value(student),
        )],
    )


def audit(coverage="partial", status="gap_identified", reasons=(GAP_REASON,), track_id=None):
    if coverage == "partial":
        reasons += (PARTIAL_REASON,)
    return SkillGapPlanningAudit(
        target=SkillRequirementTarget(
            competition_id="c", edition_id="e", track_id=track_id,
            scope="track" if track_id else "edition",
        ), coverage=coverage, gap_status=status, reason_codes=reasons,
    )


def make_plan(**updates):
    return CompetitionPlan(**{
        "id": "p", "student_id": "s", "competition_id": "c", "edition_id": "e",
        "created_at": STAMP, "updated_at": STAMP, **updates,
    })


@pytest.mark.parametrize("track_id", [None, "t"])
@pytest.mark.parametrize("kind", ["required", "desired"])
def test_confirmed_gap_need_target_and_source_audit(track_id, kind):
    item = source_item(kind=kind)
    need = PlanningNeed(id="n", kind="skill_improvement", reason_codes=item.reason_codes, source_item=item)
    plan = make_plan(
        track_id=track_id, skill_gap_audit=audit(track_id=track_id), planning_needs=[need],
        milestones=[PlanMilestone(id="m", title="Improve supplied skill", source_need_id=need.id)],
    )
    assert plan.planning_needs[0].source_item == item
    assert plan.planning_needs[0].source_item.requirement.requirement_type.value == kind
    assert plan.skill_gap_audit.coverage.value == "partial"
    assert plan.milestones[0].source_need_id == need.id
    assert plan.milestones[0].due_at is None
    assert plan.planning_horizon is None
    payload = plan.model_dump(mode="json")
    assert json.loads(plan.model_dump_json()) == payload
    assert CompetitionPlan.model_validate_json(plan.model_dump_json()) == plan


def test_unknown_is_information_need_not_skill_improvement():
    item = source_item("unknown")
    need = PlanningNeed(id="n", kind="uncertainty_resolution", reason_codes=item.reason_codes, source_item=item)
    plan = make_plan(skill_gap_audit=audit(status="undetermined", reasons=item.reason_codes), planning_needs=[need])
    assert plan.planning_needs[0].kind is PlanningNeedType.UNCERTAINTY_RESOLUTION
    assert plan.model_dump(mode="json")["planning_needs"][0]["source_item"]["requirement"]["required_level"] is None
    with pytest.raises(ValidationError, match="kind conflicts"):
        PlanningNeed(**{**need.model_dump(), "kind": "skill_improvement"})
    with pytest.raises(ValidationError):
        PlanningNeed(id="n", kind="skill_improvement", reason_codes=(PARTIAL_REASON,))


def test_dual_uncertainty_and_missing_student_are_preserved():
    data = source_item("unknown").model_dump()
    data.update(student_level=None, student_evidence=(), reason_codes=(
        UNKNOWN_REASON, SkillGapReasonCode.STUDENT_SKILL_DATA_MISSING,
    ))
    item = SkillGapItem.model_validate(data)
    need = PlanningNeed(id="n", kind="uncertainty_resolution", source_item=item, reason_codes=item.reason_codes)
    assert need.source_item.student_level is None
    assert len(need.reason_codes) == 2
    assert need.source_item.status is SkillGapItemStatus.UNKNOWN


@pytest.mark.parametrize("coverage, reason", [
    ("partial", PARTIAL_REASON), ("missing", SkillGapReasonCode.REQUIREMENT_DATA_MISSING),
])
def test_set_uncertainty_need_preserves_coverage(coverage, reason):
    need = PlanningNeed(id="n", kind="uncertainty_resolution", reason_codes=(reason,))
    projection = audit(coverage=coverage, status="undetermined", reasons=() if coverage == "partial" else (reason,))
    assert make_plan(skill_gap_audit=projection, planning_needs=[need]).skill_gap_audit.coverage.value == coverage


def test_no_gap_needs_no_fake_action_and_rejects_improvement():
    projection = audit(coverage="complete", status="no_gap", reasons=(SkillGapReasonCode.REQUIREMENT_SATISFIED,))
    plan = make_plan(skill_gap_audit=projection)
    assert plan.planning_needs == plan.milestones == ()
    need = PlanningNeed(id="n", kind="skill_improvement", reason_codes=(GAP_REASON,), source_item=source_item())
    with pytest.raises(ValidationError):
        make_plan(skill_gap_audit=projection, planning_needs=[need])


def test_known_gap_and_unknown_need_can_coexist_without_relabeling():
    gap, unknown = source_item(), source_item("unknown")
    needs = [
        PlanningNeed(id="improve", kind="skill_improvement", source_item=gap, reason_codes=gap.reason_codes),
        PlanningNeed(id="clarify", kind="uncertainty_resolution", source_item=unknown, reason_codes=unknown.reason_codes),
    ]
    plan = make_plan(skill_gap_audit=audit(reasons=(GAP_REASON, UNKNOWN_REASON)), planning_needs=needs)
    assert [n.kind.value for n in plan.planning_needs] == ["skill_improvement", "uncertainty_resolution"]
    assert plan.planning_needs[1].source_item.status is SkillGapItemStatus.UNKNOWN


def test_complete_coverage_does_not_erase_unspecified_threshold():
    item = source_item("unknown")
    need = PlanningNeed(id="n", kind="uncertainty_resolution", source_item=item, reason_codes=item.reason_codes)
    plan = make_plan(skill_gap_audit=audit(coverage="complete", status="undetermined", reasons=item.reason_codes), planning_needs=[need])
    assert plan.skill_gap_audit.coverage.value == "complete"
    assert plan.planning_needs[0].source_item.requirement.required_level is None


def test_known_threshold_missing_student_cannot_create_improvement():
    data = source_item().model_dump()
    data.update(student_level=None, student_evidence=(), status="unknown", reason_codes=(SkillGapReasonCode.STUDENT_SKILL_DATA_MISSING,))
    item = SkillGapItem.model_validate(data)
    need = PlanningNeed(id="n", kind="uncertainty_resolution", source_item=item, reason_codes=item.reason_codes)
    assert need.source_item.requirement.required_level is SkillLevel.INTERMEDIATE
    with pytest.raises(ValidationError):
        PlanningNeed(**{**need.model_dump(), "kind": "skill_improvement"})


@pytest.mark.parametrize("changes", [
    {"reason_codes": (GAP_REASON, GAP_REASON, PARTIAL_REASON)},
    {"coverage": "complete"},
    {"gap_status": "no_gap"},
    {"gap_status": "undetermined"},
])
def test_conflicting_source_summary_rejected(changes):
    with pytest.raises(ValidationError):
        SkillGapPlanningAudit.model_validate({**audit().model_dump(), **changes})


@pytest.mark.parametrize("status, kind", [("gap", "uncertainty_resolution"), ("satisfied", "skill_improvement"), ("satisfied", "uncertainty_resolution")])
def test_need_kind_cannot_relabel_p7_status(status, kind):
    item = source_item(status)
    with pytest.raises(ValidationError):
        PlanningNeed(id="n", kind=kind, source_item=item, reason_codes=item.reason_codes)


@pytest.mark.parametrize("field, value", [("competition_id", "other"), ("edition_id", "other"), ("track_id", "other")])
def test_plan_target_must_match_audit(field, value):
    with pytest.raises(ValidationError, match="target"):
        make_plan(skill_gap_audit=audit(), **{field: value})


def test_duplicate_ids_unknown_reference_and_absent_audit_rejected():
    need = PlanningNeed(id="n", kind="skill_improvement", reason_codes=(GAP_REASON,), source_item=source_item())
    with pytest.raises(ValidationError, match="duplicate ids"):
        make_plan(skill_gap_audit=audit(), planning_needs=[need, need])
    with pytest.raises(ValidationError, match="supplied P7 audit"):
        make_plan(planning_needs=[need])
    with pytest.raises(ValidationError, match="unknown planning need"):
        make_plan(milestones=[PlanMilestone(id="m", title="Task", source_need_id="missing")])
    with pytest.raises(ValidationError, match="duplicate ids"):
        make_plan(milestones=[PlanMilestone(id="m", title="Task")] * 2)


@pytest.mark.parametrize("bounds", [{}, {"start_at": STAMP}, {"end_at": "2026-10-13T10:00:00Z"}, {"start_at": STAMP, "end_at": "2026-10-13T10:00:00Z"}])
def test_reuses_partial_time_window_without_deadline_default(bounds):
    horizon = TimeWindow(**bounds)
    plan = make_plan(planning_horizon=horizon, milestones=[PlanMilestone(id="m", title="Unscheduled")])
    assert isinstance(plan.planning_horizon, TimeWindow)
    assert plan.planning_horizon == horizon
    assert plan.milestones[0].start_at is plan.milestones[0].due_at is None


def test_invalid_timing_and_outside_horizon_rejected():
    with pytest.raises(ValidationError):
        make_plan(planning_horizon={"start_at": STAMP, "end_at": "2026-10-11T10:00:00Z"})
    with pytest.raises(ValidationError):
        make_plan(planning_horizon={"start_at": "2026-10-12T10:00:00"})
    with pytest.raises(ValidationError, match="outside"):
        make_plan(planning_horizon=TimeWindow(start_at=STAMP), milestones=[
            PlanMilestone(id="m", title="Task", due_at="2026-10-11T10:00:00Z")
        ])


def test_nested_collections_and_snapshots_are_immutable_detached():
    item = source_item()
    need = PlanningNeed(id="n", kind="skill_improvement", reason_codes=item.reason_codes, source_item=item)
    needs, milestones = [need], [PlanMilestone(id="m", title="Task", source_need_id="n", dependency_ids=["prior"])]
    plan = make_plan(skill_gap_audit=audit(), planning_needs=needs, milestones=milestones)
    before = plan.model_dump_json()
    needs.clear()
    milestones.clear()
    assert plan.model_dump_json() == before
    for model, field, value in (
        (plan, "track_id", "changed"), (plan.planning_needs[0], "kind", "uncertainty_resolution"),
        (plan.milestones[0], "source_need_id", "changed"), (plan.skill_gap_audit, "coverage", "complete"),
        (plan.planning_needs[0].source_item, "status", "satisfied"),
    ):
        with pytest.raises(ValidationError):
            setattr(model, field, value)
    for collection in (plan.planning_needs, plan.milestones, need.reason_codes, plan.milestones[0].dependency_ids):
        with pytest.raises(AttributeError):
            collection.append("changed")
    with pytest.raises(TypeError):
        plan.model_copy(update={"planning_needs": []})


def test_contract_import_boundary_has_no_engine_or_runtime_dependencies():
    tree = ast.parse(inspect.getsource(plan_module))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports == {"datetime", "enum", "collections.abc", "typing", "pydantic",
                       "competition_copilot.domain.skill_gap", "competition_copilot.domain.temporal"}
    assert not any(isinstance(node, ast.Import) for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Attribute) and node.attr in ("model_construct", "__setattr__") for node in ast.walk(tree))
