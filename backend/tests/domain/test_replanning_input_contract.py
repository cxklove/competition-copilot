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
from competition_copilot.domain.replanning import (
    AffectedPlanScope,
    EventImpactAnalysis,
    PlanDiff,
    PlanMilestonesChange,
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


def test_keep_empty_no_revision_and_structural_instruction_rejected():
    source = decision(outcome="negative")
    result = batch(source=source, status="no_revision_required")
    assert not result.has_unresolved_remainder and result.instructions == ()
    with pytest.raises(ValidationError):
        batch(source=source, status="no_revision_required", instructions=(instruction(source=source),))


def test_uncertain_and_missing_replan_inputs_are_explicitly_unresolved():
    source = decision(outcome="uncertain")
    assert batch(source=source).status == "unresolved"
    with pytest.raises(ValidationError):
        batch(source=source, status="executable", instructions=(instruction(source=source),))
    assert batch().status == "unresolved"
    with pytest.raises(ValidationError):
        batch(status="executable")


def test_minimal_explicit_approved_update_is_executable_and_before_is_unchanged():
    current, source = plan(), decision()
    before = current.model_dump_json()
    update = instruction(current, source)
    result = batch(current, source, instructions=(update,), status="executable")
    assert result.instructions[0].after.id == "m1"
    assert result.instructions[0].after.due_at == AFTER_DUE
    assert result.before.model_dump_json() == before == current.model_dump_json()
    assert not result.has_unresolved_remainder
    assert result.instructions[0].authority.approval_ref == "test-approval-1"


def test_frozen_plan_diff_can_audit_explicit_update_fixture_without_revision_service():
    current, source = plan(), decision()
    update = instruction(current, source)
    batch(current, source, instructions=(update,), status="executable")
    # Explicit before/after fixture only: no application/diff computation engine.
    supplied_milestones = (update.after, current.milestones[1])
    after = CompetitionPlan(**{
        **current.model_dump(), "id": revised_plan_identity(current, supplied_milestones),
        "version": 2, "updated_at": T4, "milestones": supplied_milestones,
    })
    audit = PlanDiff(before=current, after=after, decision=source, evaluated_at=T4,
                    changes=(PlanMilestonesChange(before=current.milestones, after=supplied_milestones),))
    assert audit.after.milestones[0].due_at == AFTER_DUE
    assert audit.after.milestones[1] == current.milestones[1]


def test_scope_limits_partial_remainder_and_missing_instruction_coverage():
    source = decision(mids=("m1",))
    with pytest.raises(ValidationError):
        batch(source=source, instructions=(instruction(source=source, mid="m2"),), status="executable")
    partial = decision(partial=True)
    assert batch(source=partial, instructions=(instruction(source=partial),), status="partially_executable").has_unresolved_remainder
    with pytest.raises(ValidationError):
        batch(source=partial, instructions=(instruction(source=partial),), status="executable")
    broader = decision(mids=("m1", "m2"))
    assert batch(source=broader, instructions=(instruction(source=broader),), status="partially_executable").has_unresolved_remainder


def test_whole_plan_scope_does_not_authorize_or_claim_automatic_complete_revision():
    source = decision(whole=True, mids=())
    assert batch(source=source).instructions == ()
    updates = tuple(instruction(source=source, mid=mid) for mid in ("m1", "m2"))
    assert batch(source=source, instructions=updates, status="partially_executable").has_unresolved_remainder
    with pytest.raises(ValidationError):
        batch(source=source, instructions=updates, status="executable")


@pytest.mark.parametrize("override", [{"version": 2}, {"id": "different"}, {"updated_at": T2}])
def test_expected_plan_version_identity_content_preconditions_reject(override):
    current, source = plan(), decision()
    update = instruction(current, source, expected_plan=PlanReference.from_plan(plan(**override)))
    with pytest.raises(ValidationError):
        batch(current, source, instructions=(update,), status="executable")


def test_expected_before_content_and_exact_decision_preconditions_reject():
    source = decision()
    wrong = PlanMilestone(id="m1", title="Wrong old task", due_at=DUE)
    update = instruction(source=source, expected_before=wrong,
                         after=PlanMilestone(**{**wrong.model_dump(), "due_at": AFTER_DUE}))
    with pytest.raises(ValidationError):
        batch(source=source, instructions=(update,), status="executable")
    other = decision(mids=("m1", "m2"))
    with pytest.raises(ValidationError):
        batch(source=other, instructions=(instruction(source=source),), status="partially_executable")


def test_duplicate_and_conflicting_same_target_updates_reject_atomic_batch():
    first = instruction()
    other = instruction(after=PlanMilestone(**{**first.after.model_dump(), "due_at": AFTER_DUE + timedelta(days=1)}))
    for updates in ((first, first), (first, other), (other, first)):
        with pytest.raises(ValidationError):
            batch(instructions=updates, status="executable")
    with pytest.raises(ValidationError):
        instruction(operation="remove_milestone")


@pytest.mark.parametrize("field,value", [
    ("id", "different"), ("title", "New prose"), ("description", "New prose"),
    ("start_at", T2), ("estimated_hours", 10), ("dependency_ids", ("m2",)),
    ("status", "blocked"), ("source_need_id", "new-need"),
])
def test_only_due_at_update_is_authorized_no_implicit_other_field_permission(field, value):
    old = plan().milestones[0]
    with pytest.raises(ValidationError):
        instruction(after=PlanMilestone(**{**old.model_dump(), "due_at": AFTER_DUE, field: value}))


def test_no_op_new_need_target_audit_horizon_or_free_form_command_reject():
    with pytest.raises(ValidationError):
        instruction(after=plan().milestones[0])
    for extra in ("planning_needs", "target", "skill_gap_audit", "planning_horizon"):
        with pytest.raises(ValidationError):
            batch(**{extra: "replacement"})
    with pytest.raises(ValidationError):
        instruction(operation="do something")


def test_existing_horizon_and_dependency_reference_safety():
    current = plan(planning_horizon=TimeWindow(start_at=T1, end_at=DUE + timedelta(days=1)))
    source = decision(current)
    with pytest.raises(ValidationError):
        batch(current, source, instructions=(instruction(current, source),), status="executable")
    legacy = plan(milestones=(PlanMilestone(id="m1", title="Task", due_at=DUE, dependency_ids=("missing",)),))
    source = decision(legacy)
    with pytest.raises(ValidationError):
        batch(legacy, source, instructions=(instruction(legacy, source),), status="executable")


@pytest.mark.parametrize("missing", ["authority", "source_decision_fingerprint", "expected_plan", "expected_before", "after"])
def test_structural_instruction_requires_authority_and_machine_preconditions(missing):
    data = instruction().model_dump()
    del data[missing]
    with pytest.raises(ValidationError):
        UpdateMilestoneInstruction(**data)


def test_human_approval_reference_and_explicit_times_required():
    authority = instruction().authority.model_dump()
    for field in ("approval_ref", "approved_by_ref", "instruction_source_ref", "approved_at"):
        missing = dict(authority)
        del missing[field]
        with pytest.raises(ValidationError):
            RevisionAuthority(**missing)
    with pytest.raises(ValidationError):
        RevisionAuthority(**{**authority, "approved_at": T3.replace(tzinfo=None)})
    with pytest.raises(ValidationError):
        RevisionAuthority(**{**authority, "approval_ref": " "})
    with pytest.raises(ValidationError):
        instruction(authority={**authority, "kind": "deterministic_rule"})
    with pytest.raises(ValidationError):
        batch(supplied_at=T4.replace(tzinfo=None))
    missing = batch().model_dump()
    del missing["supplied_at"]
    with pytest.raises(ValidationError):
        ReplanningInput(**missing)


@pytest.mark.parametrize("approved", [T1, T2, T4 + timedelta(days=1)])
def test_approval_time_must_follow_decision_and_precede_supplied_batch(approved):
    with pytest.raises(ValidationError):
        update = instruction(authority={**instruction().authority.model_dump(), "approved_at": approved})
        batch(instructions=(update,), status="executable")


def test_canonical_order_identity_serialization_and_nested_immutability():
    current, source = plan(), decision(mids=("m1", "m2"))
    a, b = (instruction(current, source, mid=mid) for mid in ("m1", "m2"))
    first = batch(current, source, instructions=(a, b), status="executable")
    reverse = batch(current, source, instructions=(b, a), status="executable")
    assert first.id == reverse.id
    assert first.model_dump_json() == reverse.model_dump_json()
    assert a.id == instruction(current, source).id
    for obj in (first, first.instructions[0], first.instructions[0].authority, first.before, first.instructions[0].after):
        with pytest.raises(ValidationError):
            obj.extra = "mutation"
    with pytest.raises(TypeError):
        first.model_copy(update={})
    assert ReplanningInput.model_validate_json(first.model_dump_json()) == first
    assert ReplanningInput.model_validate(first.model_dump(mode="json")) == first


@pytest.mark.parametrize("mode", ["keep", "uncertain", "missing", "executable", "partial"])
def test_all_input_status_payloads_have_stable_machine_readable_json(mode):
    if mode == "keep":
        result = batch(source=decision(outcome="negative"), status="no_revision_required")
    elif mode == "uncertain":
        result = batch(source=decision(outcome="uncertain"))
    elif mode == "missing":
        result = batch()
    else:
        source = decision(partial=mode == "partial")
        result = batch(source=source, instructions=(instruction(source=source),),
                       status="partially_executable" if mode == "partial" else "executable")
    parsed = ReplanningInput.model_validate_json(result.model_dump_json())
    assert parsed == result and parsed.id == result.id


def test_existing_need_reference_is_preserved_without_need_replacement():
    need = PlanningNeed(id="existing-need", kind="uncertainty_resolution", reason_codes=("REQUIREMENT_DATA_MISSING",))
    audit = SkillGapPlanningAudit(
        target={"scope": "track", "competition_id": "competition", "edition_id": "edition", "track_id": "a"},
        coverage="missing", gap_status="undetermined", reason_codes=("REQUIREMENT_DATA_MISSING",),
    )
    current = plan(planning_needs=(need,), skill_gap_audit=audit, milestones=(
        PlanMilestone(id="m1", title="Existing need task", source_need_id=need.id, due_at=DUE),
    ))
    source = decision(current)
    update = instruction(current, source)
    result = batch(current, source, instructions=(update,), status="executable")
    assert result.instructions[0].after.source_need_id == need.id
    assert result.before.planning_needs == (need,)


def test_ids_bind_after_state_approval_context_and_resolution_status():
    source = decision()
    original = instruction(source=source)
    changed = instruction(source=source, after=PlanMilestone(**{
        **original.after.model_dump(), "due_at": AFTER_DUE + timedelta(days=1),
    }))
    changed_authority = instruction(source=source, authority={
        **original.authority.model_dump(), "approval_ref": "another-explicit-approval",
    })
    assert len({original.id, changed.id, changed_authority.id}) == 3
    executable = batch(source=source, instructions=(original,), status="executable")
    missing = batch(source=source)
    assert executable.id != missing.id
    assert original.id == instruction(source=source).id


def test_authority_and_after_instants_have_canonical_identity_without_auto_clock():
    original = instruction()
    equivalent = instruction(authority={
        **original.authority.model_dump(),
        "approved_at": original.authority.approved_at.astimezone(timezone(timedelta(hours=8))),
    }, after=PlanMilestone(**{
        **original.after.model_dump(),
        "due_at": original.after.due_at.astimezone(timezone(timedelta(hours=8))),
    }))
    assert original.id == equivalent.id
    assert batch(instructions=(original,), status="executable").id == batch(instructions=(equivalent,), status="executable").id
    with pytest.raises(ValidationError):
        instruction(after=PlanMilestone(**{
            **original.after.model_dump(), "due_at": AFTER_DUE.replace(tzinfo=None),
        }))
