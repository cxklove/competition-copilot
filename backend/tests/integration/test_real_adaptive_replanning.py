"""Offline real-component integration, with TEST-ONLY controlled Events/approval.

Repository target identities are real reviewed Seed data. Membership/window changes
and human approvals below are synthetic scenarios, not official historical claims.
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
    PlanRevisionService,
)
from competition_copilot.domain.replanning import PlanReference, revised_plan_identity
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

ROOT = Path(__file__).resolve().parents[3]
SEED = ROOT / "data" / "seed"
T0 = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
OBSERVED, EVALUATED, DECIDED, APPROVED, EXECUTED = (
    T0 + timedelta(hours=n) for n in range(1, 6)
)


@pytest.fixture(autouse=True)
def offline_read_only_data(monkeypatch):
    def reject_network(*args, **kwargs):
        pytest.fail("P11.5 integration must remain offline")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(socket.socket, "connect", reject_network)
    monkeypatch.setattr(socket, "getaddrinfo", reject_network)
    original_open = Path.open

    def read_only(path, mode="r", *args, **kwargs):
        if path.resolve().is_relative_to(ROOT / "data"):
            assert mode in ("r", "rb"), "Integration must never persist data"
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", read_only)
    files = tuple(SEED.glob("*.json"))
    original = {path: path.read_bytes() for path in files}
    yield
    assert {path: path.read_bytes() for path in files} == original


@pytest.fixture
def real_context():
    repository = JsonSeedCompetitionRepository(SEED)
    competition = repository.get_competition("huawei-ict")
    edition = repository.get_edition("huawei-ict-2026")
    track = repository.get_track("huawei-ict-2026-innovation")
    tracks = tuple(item.id for item in repository.list_tracks(edition.id))
    assert edition.competition_id == competition.id and track.edition_id == edition.id
    assert track.id in tracks
    student = StudentProfile(id="test-only-p11-5-student")
    target = SkillRequirementTarget(scope="track", competition_id=competition.id,
                                    edition_id=edition.id, track_id=track.id)
    # Explicit pre-existing planning context fixture. No new P7 inference/rerun.
    need = PlanningNeed(id="test-only-existing-uncertainty-need", kind="uncertainty_resolution",
                        reason_codes=("REQUIREMENT_DATA_MISSING",))
    audit = SkillGapPlanningAudit(target=target, coverage="missing", gap_status="undetermined",
                                 reason_codes=need.reason_codes)
    baseline = BaselineCompetitionPlanBuilder().build(
        target=target, planning_needs=(need,), source_audit=audit, student_id=student.id,
        created_at=T0, planning_horizon=TimeWindow(start_at=T0, end_at=T0 + timedelta(days=30)),
    )
    # P8 status is supplied metadata. Prepare active context through normal constructor.
    before = CompetitionPlan(**{**baseline.model_dump(), "status": "active"})
    assert before.milestones and before.milestones == baseline.milestones
    return before, student, tracks


def controlled_event(context, mode):
    before, _, tracks = context
    target = CompetitionTarget(competition_id=before.competition_id, edition_id=before.edition_id)
    source = SourceMetadata(
        source_url="https://example.invalid/test-only-p11-5-controlled-scenario",
        source_type="manual", observed_at=OBSERVED, verification_status="verified",
    )
    if mode == "undetermined":
        change = WindowEndpointChange(field="registration_window.end_at", kind="value_changed",
            before=ObservedInstant(state="known_value", value=T0 + timedelta(days=7), sources=(source,)),
            after=ObservedInstant(state="known_value", value=T0 + timedelta(days=8), sources=(source,)))
    else:
        old = tracks if mode != "added" else tuple(t for t in tracks if t != before.track_id)
        new = (tuple(t for t in tracks if t != before.track_id) if mode == "replan"
               else tracks if mode == "added" else (*tracks, "test-only-unrelated-added-track"))
        change = TrackMembershipChange(field="track_membership", kind="value_changed",
            before=ObservedTrackMembership(state="known_value", value=old, sources=(source,)),
            after=ObservedTrackMembership(state="known_value", value=new, sources=(source,)))
    diff = SnapshotDiff(
        before=SnapshotReference(snapshot_id=f"test-only-{mode}-before", target=target, observed_at=T0),
        after=SnapshotReference(snapshot_id=f"test-only-{mode}-after", target=target, observed_at=OBSERVED),
        changes=(change,),
    )
    events = CompetitionEventEngine().interpret(diff, detected_at=OBSERVED)
    assert len(events) == 1
    return events[0]


def impact_for(context, mode):
    before, student, _ = context
    event = controlled_event(context, mode)
    return CompetitionEventImpactAnalyzer().analyze(event, student, before, evaluated_at=EVALUATED)


def authorized_cancellation(before, decision):
    authority = RevisionAuthority(kind="human_approved", approval_ref="test-only-approved-plan-cancellation",
        approved_by_ref="test-only-human", instruction_source_ref="test-only-explicit-cancel-request",
        approved_at=APPROVED)
    fingerprint = replanning_decision_fingerprint(decision)
    instruction = UpdatePlanStatusInstruction(
        operation="update_plan_status", expected_plan=PlanReference.from_plan(before),
        expected_before_status=before.status, desired_after_status="cancelled",
        source_decision_fingerprint=fingerprint, original_scope=decision.scope, authority=authority,
    )
    resolution = AuthorizedScopeResolution(
        expected_plan=PlanReference.from_plan(before), source_decision_fingerprint=fingerprint,
        original_scope=decision.scope, status="complete", coverage="cancel_target_removed_plan",
        instruction_ids=(instruction.id,), authority=authority,
    )
    return ReplanningInput(before=before, decision=decision, supplied_at=APPROVED,
        status="executable", plan_status_instruction=instruction, scope_resolution=resolution)


def execute(context, mode, *, impacts=None):
    before, _, _ = context
    impacts = impacts if impacts is not None else (impact_for(context, mode),)
    decision = ReplanningDecisionService().decide(impacts, before, evaluated_at=DECIDED)
    if decision.outcome == "replan":
        source = authorized_cancellation(before, decision)
    else:
        source = ReplanningInput(before=before, decision=decision, supplied_at=APPROVED,
            status="no_revision_required" if decision.outcome == "keep_current_plan" else "unresolved")
    result = PlanRevisionService().revise(before, source, executed_at=EXECUTED)
    return decision, source, result


def assert_audit(context, decision, source, result):
    before, _, _ = context
    reference = PlanReference.from_plan(before)
    assert source.before == result.plan_diff.before == before
    assert source.decision == result.plan_diff.decision == decision
    assert result.replanning_input == source
    assert decision.scope.plan_id == before.id
    assert all(item.plan == reference for item in decision.impacts)
    for impact in decision.impacts:
        assert impact.event.source_diff is not None
        assert all(e.event_id == impact.event.id and e.plan_id == before.id for e in impact.evidence)
        assert all(e.source_change_fields == impact.event.source_change_fields for e in impact.evidence)
    assert result.plan_diff.trigger_event_ids == decision.trigger_event_ids
    if source.scope_resolution is not None:
        resolution, instruction = source.scope_resolution, source.plan_status_instruction
        assert resolution.original_scope == instruction.original_scope == decision.scope
        assert resolution.expected_plan == instruction.expected_plan == reference
        assert resolution.source_decision_fingerprint == instruction.source_decision_fingerprint == replanning_decision_fingerprint(decision)
        assert resolution.instruction_ids == (instruction.id,)
        assert resolution.authority == instruction.authority


def output_json(decision, source, result):
    models = [*(item.event for item in decision.impacts), *decision.impacts,
              decision, decision.scope, source, source.before, result.after, result.plan_diff, result]
    if source.scope_resolution:
        models.extend((source.scope_resolution, source.plan_status_instruction))
    for model in models:
        parsed = type(model).model_validate_json(model.model_dump_json())
        assert parsed == model and parsed.model_dump_json() == model.model_dump_json()
    return tuple(model.model_dump_json() for model in models)


def test_real_adaptive_replanning_keep_path(real_context):
    before = real_context[0]
    original = before.model_dump_json()
    decision, source, result = execute(real_context, "keep")
    impact = decision.impacts[0]
    assert impact.outcome == "no_plan_impact" and "unrelated_track_change" in impact.reason_codes
    assert impact.evidence and impact.event.source_changes[0].after.value
    assert before.track_id in impact.event.source_changes[0].after.value
    assert decision.outcome == "keep_current_plan"
    assert decision.scope.state == "known" and not decision.scope.whole_plan and decision.scope.milestone_ids == ()
    assert source.status == "no_revision_required" and source.instructions == ()
    assert result.after == before
    assert result.plan_diff.changes == () and result.plan_diff.status_change is None
    assert before.model_dump_json() == original
    assert_audit(real_context, decision, source, result)


def test_real_adaptive_replanning_undetermined_path(real_context):
    before = real_context[0]
    original = before.model_dump_json()
    decision, source, result = execute(real_context, "undetermined")
    impact = decision.impacts[0]
    assert impact.event.event_type == "registration_window_changed"
    assert impact.outcome == "undetermined"
    assert "plan_dependency_not_represented" in impact.reason_codes
    assert decision.outcome == "undetermined" and decision.scope.state == "unresolved"
    assert source.status == "unresolved" and source.has_unresolved_remainder
    assert result.after == before and result.plan_diff.changes == () and result.plan_diff.status_change is None
    assert result.plan_diff.decision.outcome != "keep_current_plan"
    assert before.model_dump_json() == original
    assert_audit(real_context, decision, source, result)


def test_real_adaptive_replanning_target_removed_cancels_plan(real_context):
    before = real_context[0]
    original = before.model_dump_json()
    decision, source, result = execute(real_context, "replan")
    impact = decision.impacts[0]
    assert impact.event.event_type == "track_membership_changed"
    assert before.track_id in impact.event.source_changes[0].before.value
    assert before.track_id not in impact.event.source_changes[0].after.value
    assert impact.outcome == "affects_plan" and "target_track_removed" in impact.reason_codes
    assert impact.scope.whole_plan and impact.scope.milestone_ids == ()
    assert decision.outcome == "replan" and decision.scope == impact.scope
    assert source.status == "executable" and source.scope_resolution.status == "complete"
    assert source.scope_resolution.coverage == "cancel_target_removed_plan"
    assert source.plan_status_instruction.authority.kind == "human_approved"
    assert source.plan_status_instruction.authority.approval_ref.startswith("test-only-")
    assert result.after.status == "cancelled" and before.status == "active"
    for field in CompetitionPlan.model_fields.keys() - {"id", "version", "updated_at", "status"}:
        assert getattr(before, field) == getattr(result.after, field)
    assert result.after.track_id == before.track_id
    assert result.after.milestones == before.milestones and result.after.milestones
    assert result.after.id == revised_plan_identity(before, before.milestones, after_status="cancelled")
    assert result.after.version == before.version + 1 and result.after.updated_at == EXECUTED
    assert result.plan_diff.changes == ()  # no fake milestone change
    assert result.plan_diff.status_change.before_status == "active"
    assert result.plan_diff.status_change.after_status == "cancelled"
    assert result.plan_diff.before == before and result.plan_diff.after == result.after
    assert before.model_dump_json() == original
    assert_audit(real_context, decision, source, result)


@pytest.mark.parametrize("mode", ["keep", "undetermined", "replan"])
def test_real_adaptive_replanning_is_deterministic_and_serializable(real_context, mode):
    before = real_context[0]
    original = before.model_dump_json(), real_context[1].model_dump_json()
    first = execute(real_context, mode)
    second = execute(real_context, mode)
    assert first == second
    assert output_json(*first) == output_json(*second)
    assert first[1].id == second[1].id and first[2].after.id == second[2].after.id
    if mode == "replan":
        assert first[1].scope_resolution.id == second[1].scope_resolution.id
    assert (before.model_dump_json(), real_context[1].model_dump_json()) == original


def test_target_removal_milestone_only_still_partial_and_nonexecutable(real_context):
    before = real_context[0]
    impact = impact_for(real_context, "replan")
    decision = ReplanningDecisionService().decide((impact,), before, evaluated_at=DECIDED)
    old = before.milestones[0]
    authority = authorized_cancellation(before, decision).plan_status_instruction.authority
    update = UpdateMilestoneInstruction(operation="update_milestone", expected_plan=PlanReference.from_plan(before),
        source_decision_fingerprint=replanning_decision_fingerprint(decision), expected_before=old,
        after=PlanMilestone(**{**old.model_dump(), "due_at": T0 + timedelta(days=7)}), authority=authority)
    source = ReplanningInput(before=before, decision=decision, supplied_at=APPROVED,
                             status="partially_executable", instructions=(update,))
    original = before.model_dump_json()
    assert source.has_unresolved_remainder and decision.scope.whole_plan
    with pytest.raises(ValueError, match="fully executable"):
        PlanRevisionService().revise(before, source, executed_at=EXECUTED)
    assert before.model_dump_json() == original


def test_target_added_cannot_claim_complete_cancellation(real_context):
    impact = impact_for(real_context, "added")
    decision = ReplanningDecisionService().decide((impact,), real_context[0], evaluated_at=DECIDED)
    assert impact.outcome == "affects_plan" and "plan_dependency_matched" in impact.reason_codes
    with pytest.raises(ValidationError, match="target removal"):
        authorized_cancellation(real_context[0], decision)


def test_missing_approval_evidence_cannot_execute(real_context):
    before = real_context[0]
    decision, source, _ = execute(real_context, "replan")
    data = source.model_dump()
    del data["plan_status_instruction"]["authority"]["approval_ref"]
    original = before.model_dump_json()
    with pytest.raises(ValidationError):
        invalid = ReplanningInput(**data)
        PlanRevisionService().revise(before, invalid, executed_at=EXECUTED)
    assert before.model_dump_json() == original and source.decision == decision


def test_multiple_impact_order_independence_retains_all_trigger_lineage(real_context):
    confirmed, irrelevant = impact_for(real_context, "replan"), impact_for(real_context, "keep")
    first = execute(real_context, "replan", impacts=(confirmed, irrelevant))
    reversed_input = execute(real_context, "replan", impacts=(irrelevant, confirmed))
    assert first == reversed_input and output_json(*first) == output_json(*reversed_input)
    assert first[1].id == reversed_input[1].id
    assert first[1].scope_resolution.id == reversed_input[1].scope_resolution.id
    assert first[0].trigger_event_ids == tuple(sorted((confirmed.event.id, irrelevant.event.id)))
    assert_audit(real_context, *first)
