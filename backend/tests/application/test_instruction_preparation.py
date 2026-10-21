"""Synthetic generic targets through real P10/P11, no event/decision mocks."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.application.instruction_preparation import (
    POLICY_ID,
    InstructionPreparationResult,
    PlanRevisionProposal,
    TargetTrackRemovedCancellationPolicy,
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
from competition_copilot.domain.plan import CompetitionPlan, PlanMilestone
from competition_copilot.domain.replanning import (
    EventImpactAnalysis,
    PlanReference,
    ReplanningDecision,
)
from competition_copilot.domain.replanning_decision_service import (
    ReplanningDecisionService,
)
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.student import StudentProfile

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)
PREPARED = NOW + timedelta(minutes=4)
POLICY = TargetTrackRemovedCancellationPolicy()


def scenario(*, status="draft", kind="removed", plan_track="track-a", event_target=None):
    plan = CompetitionPlan(id="synthetic-plan", student_id="synthetic-student",
        competition_id="synthetic-competition", edition_id="synthetic-edition", track_id=plan_track,
        status=status, created_at=NOW, updated_at=NOW,
        milestones=(PlanMilestone(id="milestone-a", title="Explicit existing milestone"),))
    target = CompetitionTarget(**(event_target or {"competition_id": plan.competition_id,
        "edition_id": plan.edition_id, "track_id": plan.track_id}))
    source = SourceMetadata(source_url="https://example.invalid/controlled-policy-test",
        source_type="manual", verification_status="verified", observed_at=NOW)
    if kind == "unknown":
        change = WindowEndpointChange(field="registration_window.end_at", kind="value_changed",
            before=ObservedInstant(state="known_value", value=NOW + timedelta(days=7), sources=(source,)),
            after=ObservedInstant(state="known_value", value=NOW + timedelta(days=8), sources=(source,)))
    else:
        old, new = ("track-a", "track-b"), ("track-b",)
        if kind == "added":
            old, new = new, old
        elif kind == "preserved":
            old, new = ("track-a",), ("track-a", "track-b")
        change = TrackMembershipChange(field="track_membership", kind="value_changed",
            before=ObservedTrackMembership(state="known_value", value=old, sources=(source,)),
            after=ObservedTrackMembership(state="known_value", value=new, sources=(source,)))
    diff = SnapshotDiff(
        before=SnapshotReference(snapshot_id="synthetic-before-" + kind, target=target, observed_at=NOW),
        after=SnapshotReference(snapshot_id="synthetic-after-" + kind, target=target, observed_at=NOW + timedelta(minutes=1)),
        changes=(change,))
    event = CompetitionEventEngine().interpret(diff, detected_at=NOW + timedelta(minutes=1))[0]
    impact = CompetitionEventImpactAnalyzer().analyze(event, StudentProfile(id=plan.student_id), plan,
        evaluated_at=NOW + timedelta(minutes=2))
    decision = ReplanningDecisionService().decide((impact,), plan, evaluated_at=NOW + timedelta(minutes=3))
    return plan, decision


@pytest.mark.parametrize("status", ["draft", "active"])
def test_exact_removal_prepares_only_typed_operation_with_full_audit(status):
    plan, decision = scenario(status=status)
    before = plan.model_dump_json(), decision.model_dump_json()
    result = POLICY.prepare(plan, decision, prepared_at=PREPARED)
    assert result.status == "PREPARED" and result.policy_id == POLICY_ID
    proposal = result.proposal
    assert proposal.operation.before_value == status and proposal.operation.after_value == "cancelled"
    assert proposal.operation.expected_plan == PlanReference.from_plan(plan)
    assert proposal.before == plan and proposal.decision == decision
    assert {r.kind for r in proposal.evidence_refs} == {"EVENT", "IMPACT", "DECISION", "SCOPE", "PLAN"}
    assert any(r.ref_id == decision.impacts[0].event.id for r in proposal.evidence_refs)
    assert POLICY_ID in proposal.message
    for forbidden in ("human_approved", "approved_by_ref", "HUMAN_APPROVED", "authority", "executed_at"):
        assert forbidden not in proposal.model_dump_json()
    assert InstructionPreparationResult.model_validate_json(result.model_dump_json()) == result
    assert POLICY.prepare(plan, decision, prepared_at=PREPARED).model_dump_json() == result.model_dump_json()
    assert (plan.model_dump_json(), decision.model_dump_json()) == before
    with pytest.raises(ValidationError, match="frozen"):
        proposal.operation.after_value = "active"
    with pytest.raises(TypeError):
        proposal.model_copy(update={"prepared_at": NOW})


@pytest.mark.parametrize("kind", ["added", "preserved", "unknown"])
def test_other_reason_keep_or_unknown_decision_has_no_supported_policy(kind):
    plan, decision = scenario(kind=kind)
    result = POLICY.prepare(plan, decision, prepared_at=PREPARED)
    assert result.status == "UNSUPPORTED" and result.proposal is None
    assert result.reason_codes == ("NO_SUPPORTED_INSTRUCTION_POLICY",)


@pytest.mark.parametrize("status", ["cancelled", "completed", "superseded"])
def test_terminal_plan_status_unsupported(status):
    plan, decision = scenario(status=status)
    assert POLICY.prepare(plan, decision, prepared_at=PREPARED).status == "UNSUPPORTED"


def test_null_track_and_edition_event_not_promoted_to_exact_track_match():
    for plan, decision in (scenario(plan_track=None), scenario(event_target={
        "competition_id": "synthetic-competition", "edition_id": "synthetic-edition", "track_id": None})):
        assert POLICY.prepare(plan, decision, prepared_at=PREPARED).status == "UNSUPPORTED"


@pytest.mark.parametrize("field,value", [("competition_id", "other-competition"),
                                        ("edition_id", "other-edition"), ("track_id", "other-track")])
def test_disjoint_event_target_unsupported(field, value):
    target = {"competition_id": "synthetic-competition", "edition_id": "synthetic-edition", "track_id": "track-a"}
    target[field] = value
    plan, decision = scenario(event_target=target)
    assert POLICY.prepare(plan, decision, prepared_at=PREPARED).status == "UNSUPPORTED"


def test_foreign_student_plan_or_plan_content_cannot_reuse_decision():
    plan, decision = scenario()
    for change in ({"student_id": "other-student"}, {"version": 2}, {"id": "other-plan"}):
        other = CompetitionPlan(**{**plan.model_dump(), **change})
        assert POLICY.prepare(other, decision, prepared_at=PREPARED).status == "UNSUPPORTED"


def test_milestone_scope_and_mixed_unknown_remainder_are_not_complete_cancellation():
    plan, decision = scenario()
    impact = decision.impacts[0]
    data = impact.model_dump()
    data["scope"].update(whole_plan=False, milestone_ids=("milestone-a",))
    data["evidence"][0]["milestone_ids"] = ("milestone-a",)
    scoped = EventImpactAnalysis.model_validate(data)
    narrow = ReplanningDecisionService().decide((scoped,), plan, evaluated_at=decision.evaluated_at)
    assert not narrow.scope.whole_plan and narrow.outcome == "replan"
    assert POLICY.prepare(plan, narrow, prepared_at=PREPARED).status == "UNSUPPORTED"
    _, unknown = scenario(kind="unknown")
    mixed = ReplanningDecisionService().decide((impact, unknown.impacts[0]), plan, evaluated_at=decision.evaluated_at)
    assert mixed.scope.state == "partially_resolved"
    assert POLICY.prepare(plan, mixed, prepared_at=PREPARED).status == "UNSUPPORTED"


def test_malformed_lineage_proposal_tampering_and_authority_fields_fail_closed():
    plan, decision = scenario()
    proposal = POLICY.prepare(plan, decision, prepared_at=PREPARED).proposal
    for changes in ({"approved_by_ref": "injected"}, {"authority": "human_approved"},
                    {"evidence_refs": ()}, {"reason_codes": ()}, {"prepared_at": NOW}):
        with pytest.raises(ValidationError):
            PlanRevisionProposal.model_validate({**proposal.model_dump(), **changes})
    forged_impact = EventImpactAnalysis.model_construct(**{**decision.impacts[0].__dict__, "evidence": ()})
    forged = ReplanningDecision.model_construct(**{**decision.__dict__, "impacts": (forged_impact,)})
    with pytest.raises(ValidationError):
        POLICY.prepare(plan, forged, prepared_at=PREPARED)


def test_preparation_needs_no_file_network_or_executor(monkeypatch):
    plan, decision = scenario()
    def forbid(*args, **kwargs):
        pytest.fail("Preparation must be pure")
    monkeypatch.setattr("builtins.open", forbid)
    monkeypatch.setattr("socket.socket.connect", forbid)
    monkeypatch.setattr("competition_copilot.domain.plan_revision_service.PlanRevisionService.revise", forbid)
    assert POLICY.prepare(plan, decision, prepared_at=PREPARED).status == "PREPARED"
