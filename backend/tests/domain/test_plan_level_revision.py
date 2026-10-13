"""Controlled target-removal scenarios and explicitly approved cancellation.

These are test scenarios, never official historical events or automatic policy.
"""

import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from competition_copilot.domain.baseline_plan_builder import (
    BaselineCompetitionPlanBuilder,
)
from competition_copilot.domain.digital_twin import (
    CompetitionTarget,
    ObservedTrackMembership,
    SnapshotDiff,
    SnapshotReference,
    TrackMembershipChange,
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
    PlanDiff,
    PlanReference,
    PlanStatusChange,
    revised_plan_identity,
)
from competition_copilot.domain.replanning_decision_service import (
    ReplanningDecisionService,
)
from competition_copilot.domain.replanning_input import (
    AuthorizedScopeResolution,
    ReplanningInput,
    RevisionAuthority,
    UpdateMilestoneInstruction,
    UpdatePlanStatusInstruction,
    replanning_decision_fingerprint,
)
from competition_copilot.domain.skill_gap import SkillRequirementTarget
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.student import StudentProfile
from competition_copilot.domain.temporal import TimeWindow
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)

T0 = datetime(2026, 10, 13, tzinfo=timezone.utc)
T1, T2, T3 = (T0 + timedelta(days=n) for n in (1, 2, 3))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Controlled cancellation tests must stay offline")
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(socket.socket, "connect", fail)


def scenario(status="active", event_kind="removed"):
    repo = JsonSeedCompetitionRepository(Path(__file__).resolve().parents[3] / "data" / "seed")
    edition = next(item for item in repo.list_editions() if repo.list_tracks(item.id))
    competition = repo.get_competition(edition.competition_id)
    track = repo.list_tracks(edition.id)[0]
    student = StudentProfile(id="test-only-plan-level-student")
    target = SkillRequirementTarget(scope="track", competition_id=competition.id,
                                    edition_id=edition.id, track_id=track.id)
    need = PlanningNeed(id="test-only-explicit-existing-need", kind="uncertainty_resolution",
                        reason_codes=("REQUIREMENT_DATA_MISSING",))
    audit = SkillGapPlanningAudit(target=target, coverage="missing", gap_status="undetermined",
                                 reason_codes=need.reason_codes)
    initial = BaselineCompetitionPlanBuilder().build(
        target=target, planning_needs=(need,), source_audit=audit,
        student_id=student.id, created_at=T0, planning_horizon=TimeWindow(start_at=T0, end_at=T3),
    )
    before = CompetitionPlan(**{**initial.model_dump(), "status": status})
    source = SourceMetadata(source_url="https://example.invalid/test-only-controlled-cancellation",
                            source_type="manual", observed_at=T0, verification_status="verified")
    if event_kind == "added":
        old, new = ("test-only-other-track",), (track.id, "test-only-other-track")
    elif event_kind == "negative":
        old, new = (track.id,), (track.id, "test-only-other-track")
    else:
        old, new = (track.id,), ("test-only-other-track",)
    event_target = CompetitionTarget(competition_id=competition.id, edition_id=edition.id)
    diff = SnapshotDiff(
        before=SnapshotReference(snapshot_id="test-only-before", target=event_target, observed_at=T0),
        after=SnapshotReference(snapshot_id="test-only-after", target=event_target, observed_at=T1),
        changes=(TrackMembershipChange(field="track_membership", kind="value_changed",
            before=ObservedTrackMembership(state="known_value", value=old, sources=(source,)),
            after=ObservedTrackMembership(state="known_value", value=new, sources=(source,))),),
    )
    event = CompetitionEventEngine().interpret(diff, detected_at=T1)[0]
    impact = CompetitionEventImpactAnalyzer().analyze(event, student, before, evaluated_at=T1)
    decision = ReplanningDecisionService().decide((impact,), before, evaluated_at=T2)
    return before, impact, decision


def instruction(before, decision, **overrides):
    return UpdatePlanStatusInstruction(**{
        "operation": "update_plan_status", "expected_plan": PlanReference.from_plan(before),
        "source_decision_fingerprint": replanning_decision_fingerprint(decision),
        "original_scope": decision.scope, "expected_before_status": before.status,
        "desired_after_status": "cancelled",
        "authority": RevisionAuthority(kind="human_approved", approval_ref="test-only-cancel-approval",
            approved_by_ref="test-only-human", instruction_source_ref="test-only-explicit-cancel-request", approved_at=T2),
        **overrides,
    })


def resolution(before, decision, inst, **overrides):
    return AuthorizedScopeResolution(**{
        "expected_plan": PlanReference.from_plan(before),
        "source_decision_fingerprint": replanning_decision_fingerprint(decision),
        "original_scope": decision.scope, "status": "complete",
        "coverage": "cancel_target_removed_plan", "instruction_ids": (inst.id,),
        "authority": inst.authority, **overrides,
    })


def approved(before, decision, inst=None, res=None, **overrides):
    inst = inst or instruction(before, decision)
    res = res or resolution(before, decision, inst)
    return ReplanningInput(**{
        "before": before, "decision": decision, "supplied_at": T3, "status": "executable",
        "plan_status_instruction": inst, "scope_resolution": res, **overrides,
    })


@pytest.mark.parametrize("status", ["draft", "active"])
def test_real_target_removal_cancellation_production_probe(status):
    before, impact, decision = scenario(status)
    original = before.model_dump_json(), impact.model_dump_json(), decision.model_dump_json()
    source = approved(before, decision)
    result = PlanRevisionService().revise(before, source, executed_at=T3)
    assert impact.outcome == "affects_plan" and "target_track_removed" in impact.reason_codes
    assert impact.scope.whole_plan and not impact.scope.milestone_ids
    assert decision.outcome == "replan" and decision.scope == impact.scope
    assert source.scope_resolution.status == "complete" and source.status == "executable"
    assert result.after.status == "cancelled"
    for field in CompetitionPlan.model_fields.keys() - {"id", "version", "updated_at", "status"}:
        assert getattr(before, field) == getattr(result.after, field)
    assert result.after.version == before.version + 1
    assert result.after.id == revised_plan_identity(before, before.milestones, after_status=result.after.status)
    assert result.plan_diff.changes == ()
    assert result.plan_diff.status_change == PlanStatusChange(before_status=status, after_status="cancelled")
    assert result.plan_diff.decision == decision
    assert result.plan_diff.decision.impacts == (impact,)
    assert result.plan_diff.trigger_event_ids == (impact.event.id,)
    assert result.replanning_input.scope_resolution.original_scope == impact.scope
    assert result.replanning_input.plan_status_instruction.authority == source.scope_resolution.authority
    repeated = PlanRevisionService().revise(before, approved(before, decision), executed_at=T3)
    assert repeated == result and repeated.model_dump_json() == result.model_dump_json()
    assert (before.model_dump_json(), impact.model_dump_json(), decision.model_dump_json()) == original
    assert PlanRevisionResult.model_validate_json(result.model_dump_json()) == result
    assert AuthorizedScopeResolution.model_validate_json(source.scope_resolution.model_dump_json()).id == source.scope_resolution.id
    for obj in (result, result.after, result.plan_diff, result.plan_diff.status_change, source.scope_resolution, source.plan_status_instruction):
        with pytest.raises(ValidationError):
            obj.extra = "mutation"


@pytest.mark.parametrize("status", ["completed", "superseded", "cancelled"])
def test_terminal_states_and_duplicate_cancellation_reject(status):
    before, _, decision = scenario(status)
    with pytest.raises(ValidationError):
        instruction(before, decision)


def test_added_impact_cannot_use_cancellation_complete_policy():
    before, impact, decision = scenario(event_kind="added")
    assert impact.outcome == "affects_plan"
    assert "plan_dependency_matched" in impact.reason_codes
    with pytest.raises(ValidationError, match="target removal"):
        approved(before, decision)


@pytest.mark.parametrize("bad", ["before_status", "version", "decision", "scope", "authority", "instruction_ref", "missing_resolution"])
def test_resolution_instruction_preconditions_and_authority_cannot_be_bypassed(bad):
    before, _, decision = scenario()
    inst = instruction(before, decision)
    res = resolution(before, decision, inst)
    if bad == "before_status":
        inst = instruction(before, decision, expected_before_status="draft")
        res = resolution(before, decision, inst)
    elif bad == "version":
        different = CompetitionPlan(**{**before.model_dump(), "version": before.version + 1})
        res = resolution(before, decision, inst, expected_plan=PlanReference.from_plan(different))
    elif bad == "decision":
        res = resolution(before, decision, inst, source_decision_fingerprint="0" * 64)
    elif bad == "scope":
        res = resolution(before, decision, inst, original_scope=AffectedPlanScope(
            plan_id=before.id, state="partially_resolved", whole_plan=True))
    elif bad == "authority":
        res = resolution(before, decision, inst, authority=RevisionAuthority(**{
            **inst.authority.model_dump(), "approval_ref": "different-approval"}))
    elif bad == "instruction_ref":
        res = resolution(before, decision, inst, instruction_ids=("different-instruction",))
    with pytest.raises(ValidationError):
        approved(before, decision, inst, res, **({"scope_resolution": None} if bad == "missing_resolution" else {}))


def test_noop_or_arbitrary_status_transition_and_missing_authority_reject():
    before, _, decision = scenario()
    for desired in ("active", "completed", "superseded", "draft"):
        with pytest.raises(ValidationError):
            instruction(before, decision, desired_after_status=desired)
    data = instruction(before, decision).model_dump()
    del data["authority"]
    with pytest.raises(ValidationError):
        UpdatePlanStatusInstruction(**data)
    data = resolution(before, decision, instruction(before, decision)).model_dump()
    del data["authority"]["approval_ref"]
    with pytest.raises(ValidationError):
        AuthorizedScopeResolution(**data)


def test_milestone_only_partial_still_rejects_execution_and_fake_complete():
    before, _, decision = scenario()
    cancel = instruction(before, decision)
    old = before.milestones[0]
    update = UpdateMilestoneInstruction(operation="update_milestone", expected_plan=PlanReference.from_plan(before),
        source_decision_fingerprint=replanning_decision_fingerprint(decision), expected_before=old,
        after=PlanMilestone(**{**old.model_dump(), "due_at": T3}), authority=cancel.authority)
    partial = resolution(before, decision, update, status="partial", coverage="partial_milestone_revision",
                         executable_milestone_ids=(old.id,))
    source = ReplanningInput(before=before, decision=decision, supplied_at=T3,
                             status="partially_executable", instructions=(update,), scope_resolution=partial)
    with pytest.raises(ValueError, match="fully executable"):
        PlanRevisionService().revise(before, source, executed_at=T3)
    fake = resolution(before, decision, update)
    with pytest.raises(ValidationError, match="fake COMPLETE"):
        ReplanningInput(before=before, decision=decision, supplied_at=T3,
                        status="executable", instructions=(update,), scope_resolution=fake)
    with pytest.raises(ValidationError):
        approved(before, decision, instructions=(update,))


def test_diff_declarations_match_actual_status_and_unchanged_milestones():
    before, _, decision = scenario()
    result = PlanRevisionService().revise(before, approved(before, decision), executed_at=T3)
    data = result.plan_diff.model_dump()
    data["status_change"] = None
    with pytest.raises(ValidationError):
        PlanDiff(**data)
    with pytest.raises(ValidationError):
        PlanStatusChange(before_status="active", after_status="active")
    other = PlanStatusChange(before_status="draft", after_status="cancelled")
    with pytest.raises(ValidationError):
        PlanDiff(**{**result.plan_diff.model_dump(), "status_change": other})


def test_unresolved_resolution_and_time_are_explicit_and_serializable():
    before, _, decision = scenario()
    inst = instruction(before, decision)
    unresolved = resolution(before, decision, inst, status="unresolved", coverage="unresolved", instruction_ids=())
    source = ReplanningInput(before=before, decision=decision, supplied_at=T3,
                             status="unresolved", scope_resolution=unresolved)
    assert ReplanningInput.model_validate_json(source.model_dump_json()) == source
    with pytest.raises(ValueError):
        PlanRevisionService().revise(before, source, executed_at=T3)
    with pytest.raises(ValidationError):
        resolution(before, decision, inst, authority={**inst.authority.model_dump(), "approved_at": T2.replace(tzinfo=None)})


def test_keep_and_uncertainty_do_not_authorize_cancellation():
    before, _, keep = scenario(event_kind="negative")
    _, _, confirmed = scenario()
    inst = instruction(before, confirmed)
    res = resolution(before, confirmed, inst)
    with pytest.raises(ValidationError):
        approved(before, keep, inst, res)
    # Existing production window fixture gives a normal UNDETERMINED decision.
    from competition_copilot.domain.digital_twin import (
        ObservedInstant,
        WindowEndpointChange,
    )
    source = SourceMetadata(source_url="https://example.invalid/test-only-window", source_type="manual",
                            observed_at=T0, verification_status="verified")
    target = CompetitionTarget(competition_id=before.competition_id, edition_id=before.edition_id)
    diff = SnapshotDiff(before=SnapshotReference(snapshot_id="test-window-before", target=target, observed_at=T0),
        after=SnapshotReference(snapshot_id="test-window-after", target=target, observed_at=T1),
        changes=(WindowEndpointChange(field="registration_window.end_at", kind="value_changed",
            before=ObservedInstant(state="known_value", value=T1, sources=(source,)),
            after=ObservedInstant(state="known_value", value=T2, sources=(source,))),))
    event = CompetitionEventEngine().interpret(diff, detected_at=T1)[0]
    impact = CompetitionEventImpactAnalyzer().analyze(event, StudentProfile(id=before.student_id), before, evaluated_at=T1)
    uncertain = ReplanningDecisionService().decide((impact,), before, evaluated_at=T2)
    with pytest.raises(ValidationError):
        approved(before, uncertain, inst, res)
    confirmed_impact = confirmed.impacts[0]
    mixed = ReplanningDecisionService().decide((impact, confirmed_impact), before, evaluated_at=T2)
    assert mixed.outcome == "replan" and mixed.scope.has_unresolved_remainder
    with pytest.raises(ValidationError, match="unresolved impact"):
        approved(before, mixed)


def test_resolution_partial_and_unresolved_roundtrip_canonical_refs():
    before, _, decision = scenario()
    inst = instruction(before, decision)
    partial = resolution(before, decision, inst, status="partial", coverage="partial_milestone_revision",
                         executable_milestone_ids=tuple(item.id for item in before.milestones))
    assert AuthorizedScopeResolution.model_validate_json(partial.model_dump_json()) == partial
    assert partial.has_unresolved_remainder
    with pytest.raises(ValidationError):
        resolution(before, decision, inst, instruction_ids=(inst.id, inst.id))
    with pytest.raises(TypeError):
        partial.model_copy(update={})


def test_existing_revision_identity_is_unchanged_without_status_transition():
    before, _, _ = scenario()
    assert revised_plan_identity(before, before.milestones) == revised_plan_identity(
        before, before.milestones, after_status=before.status)
    assert revised_plan_identity(before, before.milestones) != revised_plan_identity(
        before, before.milestones, after_status="cancelled")
