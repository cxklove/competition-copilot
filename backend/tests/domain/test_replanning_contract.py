"""P11.1 supplied result validation only; no impact/revision engine fixtures."""

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
from competition_copilot.domain.plan import CompetitionPlan, PlanMilestone
from competition_copilot.domain.replanning import (
    AffectedPlanScope,
    EventImpactAnalysis,
    PlanDiff,
    PlanMilestonesChange,
    PlanReference,
    ReplanningDecision,
    ReplanningEvidence,
    revised_plan_identity,
)
from competition_copilot.domain.source_metadata import SourceMetadata

T1 = datetime(2030, 1, 1, tzinfo=timezone.utc)
T2 = T1 + timedelta(days=1)
T3 = T2 + timedelta(days=1)
SOURCE = SourceMetadata(
    source_url="https://example.invalid/p11-contract-fixture", source_type="manual",
    observed_at=T1, verification_status="verified",
)


def plan(**overrides):
    return CompetitionPlan(**{
        "id": "plan", "student_id": "student", "competition_id": "competition",
        "edition_id": "edition", "track_id": "a", "created_at": T1, "updated_at": T1,
        "milestones": (PlanMilestone(id="m1", title="Manual milestone"),), **overrides,
    })


def event(
    *, field="registration_window.end_at", observation=False, target=None,
    after_id="after", before_tracks=("a",), after_tracks=("b",),
):
    target = target or CompetitionTarget(competition_id="competition", edition_id="edition")
    if field == "track_membership":
        change = TrackMembershipChange(
            field=field, kind="observation_state_changed" if observation else "value_changed",
            before=ObservedTrackMembership(state="known_value", value=before_tracks, sources=(SOURCE,)),
            after=ObservedTrackMembership(state="unknown") if observation else
            ObservedTrackMembership(state="known_value", value=after_tracks, sources=(SOURCE,)),
        )
    else:
        change = WindowEndpointChange(
            field=field, kind="observation_state_changed" if observation else "value_changed",
            before=ObservedInstant(state="known_value", value=T1, sources=(SOURCE,)),
            after=ObservedInstant(state="unknown") if observation else
            ObservedInstant(state="known_value", value=T2, sources=(SOURCE,)),
        )
    diff = SnapshotDiff(
        before=SnapshotReference(snapshot_id="before", target=target, observed_at=T1),
        after=SnapshotReference(snapshot_id=after_id, target=target, observed_at=T2),
        changes=(change,),
    )
    return CompetitionEventEngine().interpret(diff, detected_at=T2)[0]


def impact(outcome="undetermined", *, source=None, current=None, **overrides):
    # Old no-impact fixtures used same-target windows without a dependency,
    # encoding the unsafe Contract. Use a proven preserved-track basis instead.
    source = source or (event(field="track_membership", after_tracks=("a", "b"))
                        if outcome == "no_plan_impact" else event())
    current = current or plan()
    reasons = {
        "undetermined": ("plan_dependency_not_represented",),
        "no_plan_impact": ("unrelated_track_change",),
        "affects_plan": ("target_track_removed",),
    }
    return EventImpactAnalysis(**{
        "event": source, "plan": PlanReference.from_plan(current), "student_id": current.student_id,
        "evaluated_at": T2, "outcome": outcome,
        "scope": AffectedPlanScope(
            plan_id=current.id, state="unresolved" if outcome == "undetermined" else "known",
            whole_plan=outcome == "affects_plan",
        ),
        "reason_codes": reasons[outcome],
        "evidence": (ReplanningEvidence(
            event_id=source.id, plan_id=current.id, source_change_fields=source.source_change_fields,
        ),), **overrides,
    })


def decision(outcome="undetermined", *, impacts=None, **overrides):
    impacts = impacts or (impact(),)
    reasons = {
        "undetermined": ("revision_not_representable",),
        "keep_current_plan": ("no_plan_impact",),
        "replan": ("structural_revision_supported",),
    }
    return ReplanningDecision(**{
        "impacts": impacts, "evaluated_at": T3, "outcome": outcome,
        "scope": AffectedPlanScope(
            plan_id=impacts[0].plan.plan_id,
            state="unresolved" if outcome == "undetermined" else "known",
            whole_plan=outcome == "replan",
        ),
        "reason_codes": reasons[outcome], **overrides,
    })


def replan_context():
    old = plan()
    supplied = impact("affects_plan", source=event(field="track_membership"), current=old)
    return old, decision("replan", impacts=(supplied,))


def revised(old, milestones, **overrides):
    return CompetitionPlan(**{
        **old.model_dump(), "id": revised_plan_identity(old, milestones),
        "version": old.version + 1, "updated_at": T3, "milestones": milestones, **overrides,
    })


@pytest.mark.parametrize("outcome", ["undetermined", "no_plan_impact", "affects_plan"])
def test_all_impact_outcomes_and_structured_evidence(outcome):
    result = impact(outcome, source=event(field="track_membership") if outcome == "affects_plan" else None)
    assert result.outcome.value == outcome
    assert result.evidence[0].event_id == result.event.id
    assert result.plan.student_id == "student"
    assert EventImpactAnalysis.model_validate_json(result.model_dump_json()) == result


def test_missing_dependency_is_unknown_not_known_empty_or_no_impact():
    uncertain = impact()
    known = impact("no_plan_impact")
    assert uncertain.scope.state != known.scope.state
    for outcome in ("no_plan_impact", "affects_plan"):
        with pytest.raises(ValidationError):
            impact(outcome, reason_codes=("plan_dependency_not_represented",))
    with pytest.raises(ValidationError):
        impact("affects_plan", reason_codes=("plan_dependency_matched",))


@pytest.mark.parametrize("target", [
    CompetitionTarget(competition_id="other", edition_id="edition"),
    CompetitionTarget(competition_id="competition", edition_id="other"),
    CompetitionTarget(competition_id="competition", edition_id="edition", track_id="b"),
])
def test_disjoint_target_allows_only_no_impact_with_matching_reason(target):
    source = event(target=target)
    assert impact("no_plan_impact", source=source, reason_codes=("target_mismatch",)).scope.state == "known"
    with pytest.raises(ValidationError):
        impact(source=source)
    with pytest.raises(ValidationError):
        impact("affects_plan", source=source, reason_codes=("target_mismatch",))


def test_edition_track_context_does_not_prove_dependency_or_impact():
    assert impact().outcome == "undetermined"  # edition Event / track Plan
    assert impact(source=event(target=CompetitionTarget(
        competition_id="competition", edition_id="edition", track_id="a",
    )), current=plan(track_id=None)).outcome == "undetermined"
    with pytest.raises(ValidationError):
        impact("no_plan_impact", reason_codes=("target_mismatch",))


def test_observation_event_uncertainty_never_forces_replan():
    observed = impact(source=event(observation=True), reason_codes=("observation_only_event",))
    assert decision(impacts=(observed,)).outcome == "undetermined"
    with pytest.raises(ValidationError):
        impact("affects_plan", source=event(field="track_membership", observation=True))
    with pytest.raises(ValidationError):
        decision("replan", impacts=(observed,))


def test_fact_track_dependency_claim_is_validated_not_invented():
    assert impact("affects_plan", source=event(field="track_membership")).scope.whole_plan
    with pytest.raises(ValidationError):
        impact("affects_plan", source=event(field="track_membership"), current=plan(track_id="c"))
    with pytest.raises(ValidationError):
        impact("affects_plan", source=event(field="track_membership"), current=plan(track_id=None))


@pytest.mark.parametrize("outcome", ["undetermined", "keep_current_plan", "replan"])
def test_three_replanning_decisions(outcome):
    item = impact(
        "no_plan_impact" if outcome == "keep_current_plan" else "affects_plan" if outcome == "replan" else "undetermined",
        source=event(field="track_membership") if outcome == "replan" else None,
    )
    result = decision(outcome, impacts=(item,))
    assert result.outcome.value == outcome
    assert ReplanningDecision.model_validate_json(result.model_dump_json()) == result


def test_impact_does_not_imply_replan_and_undetermined_can_keep_exact_old_plan():
    old, approved = replan_context()
    uncertain = decision(impacts=approved.impacts)
    assert uncertain.impacts[0].outcome == "affects_plan"
    diff = PlanDiff(before=old, after=old, decision=uncertain, evaluated_at=T3)
    assert diff.changes == ()


def test_keep_and_empty_diff_reuse_exact_plan_and_lineage():
    old = plan()
    keep = decision("keep_current_plan", impacts=(impact("no_plan_impact", current=old),))
    result = PlanDiff(before=old, after=old, decision=keep, evaluated_at=T3)
    assert result.before_plan_id == result.after_plan_id == old.id
    assert result.trigger_event_ids == keep.trigger_event_ids
    assert result.changes == ()
    assert PlanDiff.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValidationError):
        PlanDiff(before=old, after=plan(id="different"), decision=keep, evaluated_at=T3)


def test_changed_plan_diff_only_records_supplied_existing_milestone_fields():
    old, approved = replan_context()
    milestones = (PlanMilestone(id="m1", title="Explicit supplied revision", due_at=T3),)
    new = revised(old, milestones)
    change = PlanMilestonesChange(before=old.milestones, after=new.milestones)
    result = PlanDiff(before=old, after=new, decision=approved, evaluated_at=T3, changes=(change,))
    assert result.before.id != result.after.id
    assert result.after.version == 2
    assert result.changes[0].after[0].due_at == T3
    assert old.milestones[0].due_at is None
    assert PlanDiff.model_validate_json(result.model_dump_json()) == result


def test_multiple_trigger_events_order_unique_and_full_context_binding():
    first = impact()
    second = impact(source=event(field="competition_window.end_at"))
    a = decision(impacts=(first, second))
    b = decision(impacts=(second, first))
    assert a.model_dump_json() == b.model_dump_json()
    assert a.trigger_event_ids == tuple(sorted((first.event.id, second.event.id)))
    old = plan()
    assert PlanDiff(before=old, after=old, decision=a, evaluated_at=T3).trigger_event_ids == a.trigger_event_ids
    with pytest.raises(ValidationError):
        decision(impacts=(first, first))
    with pytest.raises(ValidationError):
        decision(impacts=(first, impact(current=plan(id="other"))))


@pytest.mark.parametrize("change", [
    {"student_id": "other"},
    {"scope": {"plan_id": "other", "state": "unresolved"}},
    {"evaluated_at": T1},
    {"reason_codes": ()},
    {"evidence": ()},
    {"evidence": ({"event_id": "fake", "plan_id": "plan"},)},
    {"evidence": ({"event_id": "placeholder", "plan_id": "plan", "milestone_ids": ("fake",)},)},
])
def test_invalid_impact_references_and_reason_evidence_rejected(change):
    with pytest.raises(ValidationError):
        impact(**change)


@pytest.mark.parametrize("constructor", [impact, decision])
def test_explicit_aware_time_and_required_time(constructor):
    with pytest.raises(ValidationError):
        constructor(evaluated_at=datetime(2030, 1, 3))
    valid = constructor()
    missing = valid.model_dump()
    del missing["evaluated_at"]
    with pytest.raises(ValidationError):
        type(valid)(**missing)


@pytest.mark.parametrize("overrides", [
    {"id": "random-id"}, {"version": 3}, {"updated_at": T1 - timedelta(days=1)},
    {"status": "active"}, {"student_id": "other"}, {"track_id": "b"},
])
def test_plan_diff_rejects_invalid_identity_metadata_or_scope(overrides):
    old, approved = replan_context()
    milestones = (PlanMilestone(id="m1", title="changed"),)
    with pytest.raises(ValidationError):
        new = revised(old, milestones, **overrides)
        PlanDiff(
            before=old, after=new, decision=approved, evaluated_at=T3,
            changes=(PlanMilestonesChange(before=old.milestones, after=milestones),),
        )


def test_no_fake_changes_empty_diff_or_wrong_before_context():
    old, approved = replan_context()
    milestones = (PlanMilestone(id="m1", title="changed"),)
    new = revised(old, milestones)
    with pytest.raises(ValidationError):
        PlanMilestonesChange(before=old.milestones, after=old.milestones)
    with pytest.raises(ValidationError):
        PlanDiff(before=old, after=new, decision=approved, evaluated_at=T3)
    with pytest.raises(ValidationError):
        PlanDiff(before=old, after=old, decision=approved, evaluated_at=T3)
    with pytest.raises(ValidationError):
        PlanDiff(before=plan(id="other"), after=plan(id="other"), decision=decision(), evaluated_at=T3)


def test_frozen_nested_models_and_no_student_profile_payload():
    supplied = impact()
    objects = (supplied, supplied.plan, supplied.scope, supplied.evidence[0], decision())
    for obj in objects:
        with pytest.raises(ValidationError):
            obj.extra = "mutation"
        with pytest.raises(TypeError):
            obj.model_copy(update={})
        assert type(obj).model_validate_json(obj.model_dump_json()) == obj
    assert "student_profile" not in supplied.model_dump()
    assert not {"severity", "impact_score", "notification"} & EventImpactAnalysis.model_fields.keys()
    with pytest.raises(ValidationError):
        PlanMilestonesChange(before=(), after=(PlanMilestone(id="m", title="test", priority="high"),))


def test_identity_repeat_stable_and_different_revision_distinct():
    old = plan()
    a = (PlanMilestone(id="m1", title="first"),)
    b = (PlanMilestone(id="m1", title="second"),)
    assert revised_plan_identity(old, a) == revised_plan_identity(old, a)
    assert revised_plan_identity(old, a) != revised_plan_identity(old, b)
    assert PlanReference.from_plan(old) == PlanReference.from_plan(old)


def test_canonical_scope_evidence_and_no_unknown_scope_claims():
    ref = PlanReference.from_plan(plan(milestones=(
        PlanMilestone(id="z", title="z"), PlanMilestone(id="a", title="a"),
    )))
    assert ref.milestone_ids == ("a", "z")
    with pytest.raises(ValidationError):
        AffectedPlanScope(plan_id="plan", state="unresolved", milestone_ids=("m1",))
    with pytest.raises(ValidationError):
        AffectedPlanScope(plan_id="plan", state="known", milestone_ids=("m1", "m1"))
    with pytest.raises(ValidationError):
        PlanReference(**{**ref.model_dump(), "content_digest": "fake"})


@pytest.mark.parametrize("bad_evidence", [
    {"milestone_ids": ("missing",)},
    {"source_change_fields": ("unsupported_field",)},
    {"plan_id": "wrong"},
])
def test_evidence_reference_validation_with_correct_event_identity(bad_evidence):
    source = event()
    evidence = ReplanningEvidence(**{
        "event_id": source.id, "plan_id": "plan", **bad_evidence,
    })
    with pytest.raises(ValidationError):
        impact(source=source, evidence=(evidence,))


def test_reason_role_duplicates_and_scope_consistency():
    with pytest.raises(ValidationError):
        impact(reason_codes=("revision_not_representable",))
    with pytest.raises(ValidationError):
        impact(reason_codes=("plan_dependency_not_represented",) * 2)
    with pytest.raises(ValidationError):
        decision(reason_codes=("observation_only_event",))
    item = impact()
    with pytest.raises(ValidationError):
        impact(evidence=item.evidence * 2)
    with pytest.raises(ValidationError):
        impact(scope=AffectedPlanScope(plan_id="plan", state="known"))
    with pytest.raises(ValidationError):
        impact("no_plan_impact", scope=AffectedPlanScope(plan_id="plan", state="known", whole_plan=True))


def test_plan_diff_aware_time_nested_immutability_and_context_time():
    old = plan()
    keep = decision("keep_current_plan", impacts=(impact("no_plan_impact"),))
    valid = PlanDiff(before=old, after=old, decision=keep, evaluated_at=T3)
    for obj in (valid, valid.before, valid.after.milestones[0], valid.decision, valid.decision.impacts[0].event):
        with pytest.raises(ValidationError):
            obj.id = "mutated"
    with pytest.raises(ValidationError):
        PlanDiff(before=old, after=old, decision=keep, evaluated_at=T3.replace(tzinfo=None))
    missing = valid.model_dump()
    del missing["evaluated_at"]
    with pytest.raises(ValidationError):
        PlanDiff(**missing)
    with pytest.raises(ValidationError):
        impact(current=plan(updated_at=T3))


def test_supplied_changes_must_match_both_plans_and_time():
    old, approved = replan_context()
    milestones = (PlanMilestone(id="m1", title="changed"),)
    new = revised(old, milestones)
    with pytest.raises(ValidationError):
        PlanDiff(
            before=old, after=new, decision=approved, evaluated_at=T3,
            changes=(PlanMilestonesChange(before=(), after=milestones),),
        )
    with pytest.raises(ValidationError):
        PlanDiff(
            before=old, after=revised(old, milestones, updated_at=T2),
            decision=approved, evaluated_at=T3,
            changes=(PlanMilestonesChange(before=old.milestones, after=milestones),),
        )


@pytest.mark.parametrize("field", ["registration_window.end_at", "competition_window.end_at"])
def test_safety_window_without_dependency_cannot_claim_no_impact(field):
    source = event(field=field)
    with pytest.raises(ValidationError):
        impact("no_plan_impact", source=source, reason_codes=("no_relevant_plan_element",))
    assert impact(source=source, reason_codes=("plan_dependency_not_represented",)).outcome == "undetermined"


@pytest.mark.parametrize("before_tracks", [("a",), ("a", "b")])
@pytest.mark.parametrize("reasons", [
    ("target_track_removed", "no_relevant_plan_element"),
    ("no_relevant_plan_element",),
    ("plan_dependency_matched",),
    ("unrelated_track_change",),
])
def test_safety_removed_target_cannot_be_overridden_by_reason(before_tracks, reasons):
    source = event(field="track_membership", before_tracks=before_tracks, after_tracks=("b",))
    with pytest.raises(ValidationError):
        impact("no_plan_impact", source=source, reason_codes=reasons)
    assert impact("affects_plan", source=source, reason_codes=("target_track_removed",)).outcome == "affects_plan"
    with pytest.raises(ValidationError):
        impact("affects_plan", source=source, reason_codes=("target_track_removed", "no_relevant_plan_element"))


@pytest.mark.parametrize("before_tracks,after_tracks", [
    (("a",), ("a", "b")),
    (("a", "b"), ("a",)),
])
def test_safety_preserved_target_supports_no_impact_keep_and_empty_diff(before_tracks, after_tracks):
    source = event(field="track_membership", before_tracks=before_tracks, after_tracks=after_tracks)
    proven = impact("no_plan_impact", source=source, reason_codes=("unrelated_track_change",))
    assert proven.scope.state == "known" and proven.scope.milestone_ids == ()
    keep = decision("keep_current_plan", impacts=(proven,))
    diff = PlanDiff(before=plan(), after=plan(), decision=keep, evaluated_at=T3)
    assert diff.changes == ()
    assert PlanDiff.model_validate_json(diff.model_dump_json()) == diff
    # The label is allowed only when the same typed negative basis proves it.
    assert impact("no_plan_impact", source=source, reason_codes=("no_relevant_plan_element",)).outcome == "no_plan_impact"
    with pytest.raises(ValidationError):
        impact("affects_plan", source=source, reason_codes=("plan_dependency_matched",))
    with pytest.raises(ValidationError):
        impact(source=source)  # proven no-impact cannot masquerade as uncertainty


@pytest.mark.parametrize("field", ["registration_window.end_at", "track_membership"])
def test_safety_observation_loss_is_uncertainty_not_negative_or_track_removal(field):
    source = event(field=field, observation=True)
    for reasons in (("observation_only_event",), ("no_relevant_plan_element",), ("target_track_removed",)):
        with pytest.raises(ValidationError):
            impact("no_plan_impact", source=source, reason_codes=reasons)
    uncertain = impact(source=source, reason_codes=("observation_only_event",))
    assert uncertain.outcome == "undetermined"
    with pytest.raises(ValidationError):
        impact("affects_plan", source=source, reason_codes=("target_track_removed",))


@pytest.mark.parametrize("basis,outcome,accepted", [
    ("positive", "affects_plan", True),
    ("positive", "no_plan_impact", False),
    ("positive", "undetermined", False),
    ("negative", "no_plan_impact", True),
    ("negative", "affects_plan", False),
    ("negative", "undetermined", False),
    ("uncertain", "undetermined", True),
    ("uncertain", "no_plan_impact", False),
    ("uncertain", "affects_plan", False),
])
def test_safety_outcome_reason_typed_evidence_compatibility_matrix(basis, outcome, accepted):
    source, reason = {
        "positive": (event(field="track_membership"), "target_track_removed"),
        "negative": (event(field="track_membership", after_tracks=("a", "b")), "unrelated_track_change"),
        "uncertain": (event(), "plan_dependency_not_represented"),
    }[basis]
    if accepted:
        supplied = impact(outcome, source=source, reason_codes=(reason,))
        assert EventImpactAnalysis.model_validate_json(supplied.model_dump_json()) == supplied
    else:
        with pytest.raises(ValidationError):
            impact(outcome, source=source, reason_codes=(reason,))


def test_safety_known_empty_scope_and_reference_only_evidence_are_not_negative_basis():
    source = event()
    with pytest.raises(ValidationError):
        impact("no_plan_impact", source=source, reason_codes=("no_relevant_plan_element",))
    preserved = event(field="track_membership", after_tracks=("a", "b"))
    references_only = (ReplanningEvidence(event_id=preserved.id, plan_id="plan"),)
    with pytest.raises(ValidationError):
        impact("no_plan_impact", source=preserved, evidence=references_only)
    with pytest.raises(ValidationError):
        impact("no_plan_impact", source=preserved, reason_codes=("plan_dependency_not_represented",))


@pytest.mark.parametrize("observation", [False, True])
def test_safety_target_mismatch_still_has_valid_structured_negative_basis(observation):
    source = event(target=CompetitionTarget(competition_id="other", edition_id="edition"), observation=observation)
    proven = impact("no_plan_impact", source=source, reason_codes=("target_mismatch",))
    assert decision("keep_current_plan", impacts=(proven,)).outcome == "keep_current_plan"
    with pytest.raises(ValidationError):
        impact(source=source)


def test_safety_added_target_is_positive_and_removed_reason_cannot_claim_it():
    source = event(field="track_membership", before_tracks=("b",), after_tracks=("a", "b"))
    assert impact("affects_plan", source=source, reason_codes=("plan_dependency_matched",)).outcome == "affects_plan"
    with pytest.raises(ValidationError):
        impact("affects_plan", source=source, reason_codes=("target_track_removed",))
    with pytest.raises(ValidationError):
        impact("no_plan_impact", source=source, reason_codes=("no_relevant_plan_element",))


def test_safety_uncertainty_reason_cannot_override_negative_or_observation_category():
    with pytest.raises(ValidationError):
        impact(reason_codes=("observation_only_event",))  # factual window Event
    with pytest.raises(ValidationError):
        impact("no_plan_impact", reason_codes=("unrelated_track_change", "plan_dependency_not_represented"))
