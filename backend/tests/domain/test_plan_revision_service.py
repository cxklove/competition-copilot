"""Explicit approved test instructions, never Event-derived deadline rules."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.digital_twin import (
    CompetitionTarget,
    ObservedInstant,
    ObservedTrackMembership,
    SnapshotDiff,
    SnapshotReference,
    TrackMembershipChange,
    WindowEndpointChange,
)
from competition_copilot.domain.event_engine import CompetitionEventEngine
from competition_copilot.domain.event_impact_analyzer import (
    CompetitionEventImpactAnalyzer,
)
from competition_copilot.domain.plan import (
    CompetitionPlan,
    PlanMilestone,
    PlanningNeed,
    SkillGapPlanningAudit,
)
from competition_copilot.domain.plan_revision_service import (
    PlanRevisionResult,
    PlanRevisionService,
)
from competition_copilot.domain.replanning import (
    AffectedPlanScope,
    EventImpactAnalysis,
    PlanReference,
    ReplanningEvidence,
    revised_plan_identity,
)
from competition_copilot.domain.replanning_decision_service import (
    ReplanningDecisionService,
)
from competition_copilot.domain.replanning_input import (
    ReplanningInput,
    RevisionAuthority,
    UpdateMilestoneInstruction,
    replanning_decision_fingerprint,
)
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.student import StudentProfile
from competition_copilot.domain.temporal import TimeWindow

T1 = datetime(2026, 10, 13, tzinfo=timezone.utc)
T2, T3, T4 = (T1 + timedelta(days=days) for days in (1, 2, 3))
DUE, AFTER_DUE = T1 + timedelta(days=7), T1 + timedelta(days=12)
SOURCE = SourceMetadata(
    source_url="https://example.invalid/instruction-fixture", source_type="manual",
    observed_at=T1, verification_status="verified",
)


def plan(**changes):
    return CompetitionPlan(**{
        "id": "plan", "student_id": "student", "competition_id": "competition",
        "edition_id": "edition", "track_id": "a", "created_at": T1, "updated_at": T1,
        "milestones": tuple(PlanMilestone(id=mid, title="Explicit existing task", due_at=DUE) for mid in ("m1", "m2")),
        **changes,
    })


def decision(current=None, *, outcome="affected", mids=("m1",), whole=False, partial=False):
    current = current or plan()
    target = CompetitionTarget(competition_id="competition", edition_id="edition")
    if outcome == "uncertain":
        change = WindowEndpointChange(
            field="registration_window.end_at", kind="value_changed",
            before=ObservedInstant(state="known_value", value=T1, sources=(SOURCE,)),
            after=ObservedInstant(state="known_value", value=T2, sources=(SOURCE,)),
        )
    else:
        change = TrackMembershipChange(
            field="track_membership", kind="value_changed",
            before=ObservedTrackMembership(state="known_value", value=("a",), sources=(SOURCE,)),
            after=ObservedTrackMembership(state="known_value", value=("b",) if outcome == "affected" else ("a", "b"), sources=(SOURCE,)),
        )
    diff = SnapshotDiff(
        before=SnapshotReference(snapshot_id="before", target=target, observed_at=T1),
        after=SnapshotReference(snapshot_id="after", target=target, observed_at=T2), changes=(change,),
    )
    event = CompetitionEventEngine().interpret(diff, detected_at=T2)[0]
    impact = CompetitionEventImpactAnalyzer().analyze(event, StudentProfile(id=current.student_id), current, evaluated_at=T2)
    if outcome == "affected":
        # Supplied Contract scope refs, not a deadline dependency or automatic
        # Event-to-revision rule. Human-approved instruction supplies WHAT later.
        impact = EventImpactAnalysis(**{
            **impact.model_dump(),
            "scope": AffectedPlanScope(plan_id=current.id, state="partially_resolved" if partial else "known", milestone_ids=mids, whole_plan=whole),
            "evidence": (ReplanningEvidence(event_id=event.id, plan_id=current.id, milestone_ids=mids, source_change_fields=event.source_change_fields),),
        })
    return ReplanningDecisionService().decide((impact,), current, evaluated_at=T3)


def instruction(current=None, source=None, *, mid="m1", **changes):
    current = current or plan()
    source = source or decision(current)
    before = next(item for item in current.milestones if item.id == mid)
    return UpdateMilestoneInstruction(**{
        "operation": "update_milestone",
        "source_decision_fingerprint": replanning_decision_fingerprint(source),
        "expected_plan": PlanReference.from_plan(current), "expected_before": before,
        "after": PlanMilestone(**{**before.model_dump(), "due_at": AFTER_DUE}),
        "authority": RevisionAuthority(kind="human_approved", approval_ref="test-approval-1", approved_by_ref="test-reviewer", instruction_source_ref="explicit-test-request", approved_at=T3),
        **changes,
    })


def batch(current=None, source=None, *, instructions=(), status="unresolved", **changes):
    current = current or plan()
    source = source or decision(current)
    return ReplanningInput(**{
        "before": current, "decision": source, "supplied_at": T4,
        "status": status, "instructions": instructions, **changes,
    })



def approved(current=None, *, mids=("m1",)):
    current = current or plan()
    source = decision(current, mids=mids)
    return batch(current, source, instructions=tuple(
        instruction(current, source, mid=mid) for mid in mids
    ), status="executable")


@pytest.mark.parametrize("outcome,status", [
    ("negative", "no_revision_required"), ("uncertain", "unresolved"),
])
def test_safe_noop_retains_keep_or_uncertainty_and_all_metadata(outcome, status):
    current = plan()
    source = batch(current, decision(current, outcome=outcome), status=status)
    result = PlanRevisionService().revise(current, source, executed_at=T4)
    assert result.after == current
    assert result.plan_diff.changes == ()
    assert result.plan_diff.decision == source.decision
    assert result.replanning_input == source
    assert result.plan_diff.decision.outcome == (
        "keep_current_plan" if outcome == "negative" else "undetermined"
    )
    assert PlanRevisionResult.model_validate_json(result.model_dump_json()) == result


def test_real_update_identity_actual_collection_diff_and_complete_lineage():
    current, source = plan(), approved()
    result = PlanRevisionService().revise(current, source, executed_at=T4)
    after, diff = result.after, result.plan_diff
    assert after.milestones[0].due_at == AFTER_DUE
    assert after.milestones[1] == current.milestones[1]
    assert after.version == current.version + 1
    assert after.id == revised_plan_identity(current, after.milestones)
    assert after.created_at == current.created_at and after.updated_at == T4
    assert len(diff.changes) == 1
    assert diff.changes[0].before == current.milestones
    assert diff.changes[0].after == after.milestones
    assert diff.decision == source.decision
    assert diff.decision.impacts == source.decision.impacts
    assert diff.trigger_event_ids == source.decision.trigger_event_ids
    assert result.replanning_input.instructions[0].authority == source.instructions[0].authority
    for field in CompetitionPlan.model_fields.keys() - {"id", "version", "updated_at", "milestones"}:
        assert getattr(after, field) == getattr(current, field)
    assert PlanRevisionResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("kind", ["missing", "partial", "whole"])
def test_noncomplete_replan_rejects_without_applying_known_subset(kind):
    current = plan()
    source = decision(current, partial=kind == "partial", whole=kind == "whole",
                      mids=() if kind == "whole" else ("m1",))
    payload = batch(current, source) if kind == "missing" else batch(
        current, source, instructions=(instruction(current, source),), status="partially_executable",
    )
    original = current.model_dump_json(), payload.model_dump_json()
    with pytest.raises(ValueError, match="fully executable"):
        PlanRevisionService().revise(current, payload, executed_at=T4)
    assert (current.model_dump_json(), payload.model_dump_json()) == original


@pytest.mark.parametrize("changes", [
    {"version": 2}, {"id": "other-plan"},
    {"milestones": (PlanMilestone(id="m1", title="Stale content", due_at=DUE),)},
])
def test_stale_current_plan_rejects(changes):
    source = approved()
    with pytest.raises(ValueError, match="exact current Plan"):
        PlanRevisionService().revise(plan(**changes), source, executed_at=T4)


@pytest.mark.parametrize("bad", ["keep", "uncertain", "scope", "before", "conflict", "authority", "need", "self"])
def test_service_boundary_revalidates_normal_untrusted_payloads_before_execution(bad):
    current = plan()
    source = approved().model_dump()
    if bad in ("keep", "uncertain"):
        other = decision(outcome="negative" if bad == "keep" else "uncertain")
        source["decision"] = other.model_dump()
    elif bad == "scope":
        source["instructions"] = (instruction(mid="m2").model_dump(),)
    elif bad == "before":
        source["instructions"][0]["expected_before"]["title"] = "Wrong before"
    elif bad == "conflict":
        source["instructions"] = source["instructions"] * 2
    elif bad == "authority":
        del source["instructions"][0]["authority"]["approval_ref"]
    elif bad == "need":
        source["instructions"][0]["after"]["source_need_id"] = "unknown"
    else:
        source["instructions"][0]["after"]["dependency_ids"] = ("m1",)
    original = current.model_dump_json()
    with pytest.raises(ValidationError):
        payload = ReplanningInput(**source)
        PlanRevisionService().revise(current, payload, executed_at=T4)
    assert current.model_dump_json() == original


def test_final_dependency_inventory_includes_unaffected_milestones():
    current = plan(milestones=(
        PlanMilestone(id="m1", title="Authorized task", due_at=DUE),
        PlanMilestone(id="m2", title="Legacy dangling dependency", dependency_ids=("missing",)),
    ))
    source = approved(current)
    original = current.model_dump_json()
    with pytest.raises(ValueError, match="dependency"):
        PlanRevisionService().revise(current, source, executed_at=T4)
    assert current.model_dump_json() == original


def test_preserves_existing_need_audit_horizon_and_nonlexical_milestone_order():
    need = PlanningNeed(id="existing-need", kind="uncertainty_resolution",
                        reason_codes=("REQUIREMENT_DATA_MISSING",))
    audit = SkillGapPlanningAudit(
        target={"scope": "track", "competition_id": "competition", "edition_id": "edition", "track_id": "a"},
        coverage="missing", gap_status="undetermined", reason_codes=("REQUIREMENT_DATA_MISSING",),
    )
    current = plan(planning_needs=(need,), skill_gap_audit=audit,
                   planning_horizon=TimeWindow(start_at=T1, end_at=AFTER_DUE),
                   milestones=(PlanMilestone(id="m3", title="Preserve first"),
                               PlanMilestone(id="m1", title="Need task", due_at=DUE, source_need_id=need.id),
                               PlanMilestone(id="m2", title="Preserve last", dependency_ids=("m1",))))
    result = PlanRevisionService().revise(current, approved(current), executed_at=T4)
    assert tuple(item.id for item in result.after.milestones) == ("m3", "m1", "m2")
    assert result.after.milestones[0] == current.milestones[0]
    assert result.after.milestones[2] == current.milestones[2]
    assert result.after.planning_needs == current.planning_needs
    assert result.after.skill_gap_audit == current.skill_gap_audit
    assert result.after.planning_horizon == current.planning_horizon


def test_multiple_updates_order_independence_determinism_and_immutability():
    current = plan()
    source = approved(current, mids=("m1", "m2"))
    reverse = ReplanningInput(**{**source.model_dump(), "instructions": source.instructions[::-1]})
    before = current.model_dump_json(), source.model_dump_json()
    service = PlanRevisionService()
    first = service.revise(current, source, executed_at=T4)
    second = service.revise(current, reverse, executed_at=T4)
    assert first == second and first.model_dump_json() == second.model_dump_json()
    assert first.after.id == second.after.id
    assert all(item.due_at == AFTER_DUE for item in first.after.milestones)
    assert len(first.plan_diff.changes) == 1  # frozen whole-collection granularity
    assert (current.model_dump_json(), source.model_dump_json()) == before
    for obj in (first, first.after, first.plan_diff, first.plan_diff.changes[0], first.after.milestones[0]):
        with pytest.raises(ValidationError):
            obj.extra = "mutation"
    with pytest.raises(TypeError):
        first.model_copy(update={})


@pytest.mark.parametrize("instant", [T4.replace(tzinfo=None), T4 - timedelta(seconds=1)])
def test_execution_time_is_explicit_aware_and_not_before_supply(instant):
    with pytest.raises(ValueError):
        PlanRevisionService().revise(plan(), approved(), executed_at=instant)


def test_missing_execution_time_and_noop_instruction_reject():
    with pytest.raises(TypeError):
        PlanRevisionService().revise(plan(), approved())
    with pytest.raises(ValidationError):
        instruction(after=plan().milestones[0])


def test_receipt_cannot_claim_execution_of_another_approved_after_state():
    source = approved()
    result = PlanRevisionService().revise(plan(), source, executed_at=T4)
    alternate = instruction(after=PlanMilestone(**{
        **source.instructions[0].after.model_dump(), "due_at": AFTER_DUE + timedelta(days=1),
    }))
    other = batch(instructions=(alternate,), status="executable")
    with pytest.raises(ValidationError, match="approved updates"):
        PlanRevisionResult(replanning_input=other, plan_diff=result.plan_diff)
