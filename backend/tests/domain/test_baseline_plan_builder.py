"""P8.3 synthetic structure tests; no decision mapping, data access or scheduling."""

import ast
import inspect
import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain import baseline_plan_builder
from competition_copilot.domain.baseline_plan_builder import (
    BaselineCompetitionPlanBuilder,
)
from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.plan import (
    CompetitionPlan,
    MilestoneStatus,
    PlanningNeed,
    PlanStatus,
    SkillGapPlanningAudit,
    SkillRequirementTarget,
)
from competition_copilot.domain.skill import SkillLevel
from competition_copilot.domain.skill_gap import (
    SkillFactRole,
    SkillGapItem,
    SkillGapReasonCode,
    SkillRequirement,
    requirement_presence_field,
    skill_fact_field,
    skill_fact_value,
)
from competition_copilot.domain.temporal import TimeWindow

STAMP = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)


def target(track_id=None, competition_id="c", edition_id="e"):
    return SkillRequirementTarget(
        competition_id=competition_id, edition_id=edition_id, track_id=track_id,
        scope="track" if track_id is not None else "edition",
    )


def need(kind="skill_improvement", need_id="n", skill_id="skill-a"):
    """Author a validated P8.1 input; no P7 Decision/Engine or P8.2 mapper runs."""
    if skill_id is None:
        return PlanningNeed(id=need_id, kind=kind, reason_codes=(
            SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE,
        ))
    improvement = kind == "skill_improvement"
    required = SkillLevel.INTERMEDIATE if improvement else None
    student = SkillLevel.BEGINNER if improvement else SkillLevel.ADVANCED
    source = {"source_url": "https://example.org/synthetic", "source_type": "manual",
              "observed_at": STAMP, "verification_status": "verified"}
    fact = SkillRequirement(
        skill_id=skill_id, requirement_type="required", required_level=required,
        presence_evidence=[Evidence(code="TEST_ONLY_PRESENCE", message="Synthetic presence.",
                                    field=requirement_presence_field(skill_id), value=True, source=source)],
        evidence=[] if required is None else [Evidence(
            code="TEST_ONLY_LEVEL", message="Synthetic threshold.", source=source,
            field=skill_fact_field(SkillFactRole.REQUIREMENT, skill_id), value=skill_fact_value(required),
        )],
    )
    item = SkillGapItem(
        requirement=fact, student_level=student, status="gap" if improvement else "unknown",
        reason_codes=(SkillGapReasonCode.SKILL_BELOW_REQUIREMENT if improvement
                      else SkillGapReasonCode.REQUIREMENT_PROFICIENCY_UNSPECIFIED,),
        student_evidence=[Evidence(
            code="TEST_ONLY_STUDENT", message="Synthetic supplied student fact.",
            field=skill_fact_field(SkillFactRole.STUDENT_SKILL, skill_id), value=skill_fact_value(student),
        )],
    )
    return PlanningNeed(id=need_id, kind=kind, source_item=item, reason_codes=item.reason_codes)


def audit(planning_target, needs):
    """Supplied synthetic audit fixture; Builder only passes it through."""
    reasons = tuple(dict.fromkeys(r for n in needs for r in n.reason_codes))
    coverage = "partial" if SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE in reasons else "complete"
    if not reasons:
        reasons = (SkillGapReasonCode.REQUIREMENT_SATISFIED,)
    status = "gap_identified" if SkillGapReasonCode.SKILL_BELOW_REQUIREMENT in reasons else (
        "no_gap" if reasons == (SkillGapReasonCode.REQUIREMENT_SATISFIED,) else "undetermined"
    )
    return SkillGapPlanningAudit(target=planning_target, coverage=coverage, gap_status=status, reason_codes=reasons)


def build(needs=(), planning_target=None, horizon=None, **updates):
    planning_target = planning_target or target()
    return BaselineCompetitionPlanBuilder().build(**{
        "target": planning_target, "planning_needs": needs,
        "student_id": "student-test", "created_at": STAMP,
        "source_audit": audit(planning_target, needs), "planning_horizon": horizon,
        **updates,
    })


@pytest.mark.parametrize("kind, skill_id, title", [
    ("skill_improvement", "skill-a", "Address confirmed skill improvement need: skill-a"),
    ("uncertainty_resolution", "skill-a", "Resolve planning uncertainty for skill: skill-a"),
    ("uncertainty_resolution", None, "Resolve competition requirement uncertainty"),
])
def test_one_need_one_unscheduled_milestone(kind, skill_id, title):
    supplied = need(kind, skill_id=skill_id)
    plan = build((supplied,))
    assert plan.planning_needs == (supplied,)
    assert len(plan.milestones) == 1
    milestone = plan.milestones[0]
    assert milestone.source_need_id == supplied.id
    assert milestone.title == title
    assert milestone.description is None
    assert milestone.start_at is milestone.due_at is milestone.estimated_hours is None
    assert milestone.dependency_ids == ()
    assert milestone.status is MilestoneStatus.PENDING
    assert plan.status is PlanStatus.DRAFT
    assert plan.version == 1
    assert plan.created_at == plan.updated_at == STAMP


def test_mixed_needs_preserved_in_supplied_order():
    needs = (
        need("uncertainty_resolution", "z", "skill-z"),
        need("skill_improvement", "b", "skill-b"),
        need("uncertainty_resolution", "set", None),
    )
    plan = build(needs)
    assert plan.planning_needs == needs
    assert [m.source_need_id for m in plan.milestones] == [n.id for n in needs]
    assert len(plan.milestones) == len(needs)
    assert plan.planning_needs[-1].source_item is None
    assert len({m.id for m in plan.milestones}) == len(needs)


@pytest.mark.parametrize("track_id", [None, "track-a"])
def test_edition_track_and_empty_plan_are_valid(track_id):
    supplied_target = target(track_id)
    plan = build(planning_target=supplied_target)
    assert (plan.competition_id, plan.edition_id, plan.track_id) == (
        supplied_target.competition_id, supplied_target.edition_id, supplied_target.track_id
    )
    assert plan.planning_needs == plan.milestones == ()
    assert plan.planning_horizon is None
    assert plan.skill_gap_audit.target == supplied_target


def test_empty_plan_without_audit_is_supported_by_existing_contract():
    plan = build(source_audit=None)
    assert plan.milestones == ()
    assert plan.skill_gap_audit is None


@pytest.mark.parametrize("bounds", [None, {}, {"start_at": STAMP},
    {"end_at": "2026-11-01T12:00:00Z"}, {"start_at": STAMP, "end_at": "2026-11-01T12:00:00Z"},
])
def test_horizon_pass_through_does_not_schedule_milestones(bounds):
    horizon = TimeWindow(**bounds) if bounds is not None else None
    plan = build((need(),), horizon=horizon)
    assert plan.planning_horizon == horizon
    assert plan.milestones[0].start_at is plan.milestones[0].due_at is None
    assert plan.milestones[0].estimated_hours is None


def test_repeat_build_is_identical_and_read_only():
    planning_target = target("t")
    needs = (need(), need("uncertainty_resolution", "set", None))
    horizon = TimeWindow(start_at=STAMP)
    source_audit = audit(planning_target, needs)
    inputs = (planning_target, *needs, source_audit, horizon)
    before = tuple(x.model_dump_json() for x in inputs)
    first = build(needs, planning_target, horizon, source_audit=source_audit)
    second = build(needs, planning_target, horizon, source_audit=source_audit)
    assert first.model_dump_json() == second.model_dump_json()
    assert first.id == second.id
    assert [m.id for m in first.milestones] == [m.id for m in second.milestones]
    assert tuple(x.model_dump_json() for x in inputs) == before
    assert first.skill_gap_audit == source_audit
    assert first.planning_needs == needs
    payload = first.model_dump(mode="json")
    assert payload == json.loads(first.model_dump_json())
    assert CompetitionPlan.model_validate_json(first.model_dump_json()) == first
    with pytest.raises(ValidationError):
        first.status = PlanStatus.ACTIVE
    with pytest.raises(ValidationError):
        first.milestones[0].title = "changed"
    with pytest.raises(AttributeError):
        first.milestones.append(first.milestones[0])
    with pytest.raises(AttributeError):
        first.planning_needs.append(needs[0])


def test_material_input_changes_produce_distinct_plan_identity():
    original = need()
    first = build((original,))
    changed_student = build((original,), student_id="other")
    changed_horizon = build((original,), horizon=TimeWindow(start_at=STAMP))
    changed_collection = build((original, need("skill_improvement", "other", "skill-b")))
    data = original.model_dump()
    data["source_item"]["student_level"] = "beginner"
    data["source_item"]["requirement"]["required_level"] = "advanced"
    data["source_item"]["requirement"]["evidence"][0]["value"] = "advanced"
    changed_fact = build((PlanningNeed.model_validate(data),))
    assert len({p.id for p in (first, changed_student, changed_horizon, changed_collection, changed_fact)}) == 5


def test_evidence_display_text_does_not_define_identity_or_behavior():
    supplied = need()
    data = supplied.model_dump()
    data["source_item"]["requirement"]["presence_evidence"][0]["message"] = "Changed annotation, same canonical fact."
    changed = PlanningNeed.model_validate(data)
    first, second = build((supplied,)), build((changed,))
    assert first.id == second.id
    assert first.milestones == second.milestones
    assert second.planning_needs == (changed,)


def test_distinct_need_ids_for_same_skill_are_not_merged():
    first, second = need(need_id="first"), need(need_id="second")
    plan = build((first, second))
    assert len(plan.milestones) == 2
    assert [m.source_need_id for m in plan.milestones] == ["first", "second"]


def test_reordering_needs_preserves_new_order_and_changes_identity():
    first, second = need(need_id="a"), need("uncertainty_resolution", "b", "skill-b")
    ordered, reversed_plan = build((first, second)), build((second, first))
    assert ordered.id != reversed_plan.id
    assert [m.source_need_id for m in reversed_plan.milestones] == ["b", "a"]


@pytest.mark.parametrize("mismatched_target", [target(competition_id="other"), target(edition_id="other"), target("other")])
def test_target_and_source_audit_mismatch_rejected(mismatched_target):
    needs = (need(),)
    with pytest.raises(ValidationError, match="target"):
        build(needs, planning_target=mismatched_target, source_audit=audit(target(), needs))


def test_p8_2_need_target_cannot_be_rebound_even_with_other_matching_audit():
    canonical_id = "planning-need:" + json.dumps([
        "c", "e", None, "skill", "skill-a", "skill_improvement"
    ], separators=(",", ":"))
    supplied = need(need_id=canonical_id)
    assert build((supplied,)).milestones[0].source_need_id == canonical_id
    other_target = target(competition_id="other")
    with pytest.raises(ValueError, match="need target"):
        build((supplied,), planning_target=other_target, source_audit=audit(other_target, (supplied,)))


@pytest.mark.parametrize("bad_id", ["planning-need:invalid", "planning-need:[]"])
def test_malformed_canonical_need_identity_is_rejected(bad_id):
    with pytest.raises(ValueError):
        build((need(need_id=bad_id),))


def test_duplicate_need_ids_and_missing_audit_fail_atomically():
    supplied = need()
    with pytest.raises(ValidationError, match="duplicate ids"):
        build((supplied, supplied))
    with pytest.raises(ValidationError, match="supplied P7 audit"):
        build((supplied,), source_audit=None)


@pytest.mark.parametrize("changes", [
    {"planning_needs": []}, {"planning_needs": ({},)}, {"target": {}},
    {"source_audit": {}}, {"planning_horizon": {}},
    {"created_at": datetime(2026, 10, 12)}, {"student_id": " "},
])
def test_invalid_builder_input_rejected(changes):
    with pytest.raises((TypeError, ValueError)):
        build(**changes)


def test_unknown_need_type_is_rejected_without_generic_fallback():
    with pytest.raises(ValidationError):
        PlanningNeed.model_validate({**need().model_dump(), "kind": "unsupported"})
    tree = ast.parse(inspect.getsource(baseline_plan_builder))
    # Last branch in the kind mapping fails; no generic title/action fallback.
    kind_branches = [n for n in ast.walk(tree) if isinstance(n, ast.If)
                     and isinstance(n.test, ast.Compare)
                     and any(isinstance(x, ast.Attribute) and x.attr == "kind" for x in ast.walk(n.test))]
    assert kind_branches
    assert any(isinstance(n, ast.Raise) for branch in kind_branches for n in ast.walk(branch))


def test_builder_imports_only_p8_contracts_and_deterministic_standard_library():
    tree = ast.parse(inspect.getsource(baseline_plan_builder))
    assert {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} == {
        "datetime", "hashlib", "typing", "competition_copilot.domain.plan", "competition_copilot.domain.temporal",
    }
    assert {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} == {"json"}
    assert not any(isinstance(n, ast.Attribute) and n.attr in (
        "model_construct", "__setattr__", "uuid4", "now", "student_level", "required_level", "status", "reason_codes",
    ) for n in ast.walk(tree))
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "hash" for n in ast.walk(tree))
