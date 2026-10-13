"""Explicit typed inputs only; fixtures are not official historical changes."""

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
from competition_copilot.domain.plan import CompetitionPlan, PlanMilestone
from competition_copilot.domain.replanning import EventImpactAnalysis
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.student import StudentProfile

T1 = datetime(2030, 1, 1, tzinfo=timezone.utc)
T2 = T1 + timedelta(days=1)
T3 = T2 + timedelta(days=1)
TARGET = CompetitionTarget(competition_id="competition", edition_id="edition")
SOURCE = SourceMetadata(
    source_url="https://example.invalid/impact-fixture", source_type="manual",
    observed_at=T1, verification_status="verified",
)


def plan(**changes):
    return CompetitionPlan(**{
        "id": "plan", "student_id": "student", "competition_id": "competition",
        "edition_id": "edition", "track_id": "a", "created_at": T1, "updated_at": T1,
        "milestones": (PlanMilestone(id="m", title="Manual task"),), **changes,
    })


def event(*, field="registration_window.end_at", target=TARGET,
          before_state="known_value", after_state="known_value",
          before_tracks=("a",), after_tracks=("b",)):
    observation = "unknown" in (before_state, after_state)
    kind = "observation_state_changed" if observation else (
        "presence_changed" if "known_absent" in (before_state, after_state) else "value_changed"
    )
    if field == "track_membership":
        def membership(state, tracks):
            return ObservedTrackMembership(
                state=state, value=tracks if state == "known_value" else None,
                sources=() if state == "unknown" else (SOURCE,),
            )
        change = TrackMembershipChange(
            field=field, kind=kind,
            before=membership(before_state, before_tracks), after=membership(after_state, after_tracks),
        )
    else:
        def instant(state, time):
            return ObservedInstant(
                state=state, value=time if state == "known_value" else None,
                sources=() if state == "unknown" else (SOURCE,),
            )
        change = WindowEndpointChange(
            field=field, kind=kind, before=instant(before_state, T1), after=instant(after_state, T2),
        )
    diff = SnapshotDiff(
        before=SnapshotReference(snapshot_id="before", target=target, observed_at=T1),
        after=SnapshotReference(snapshot_id="after", target=target, observed_at=T2),
        changes=(change,),
    )
    return CompetitionEventEngine().interpret(diff, detected_at=T2)[0]


def analyze(source=None, current=None, student=None, **context):
    return CompetitionEventImpactAnalyzer().analyze(
        source or event(), student or StudentProfile(id="student"), current or plan(),
        evaluated_at=context.get("evaluated_at", T3),
    )


def assert_result(result, outcome, reason):
    assert result.outcome == outcome
    assert tuple(code.value for code in result.reason_codes) == (reason,)
    assert result.evidence[0].event_id == result.event.id
    assert result.evidence[0].plan_id == result.plan.plan_id
    assert set(result.evidence[0].source_change_fields) == set(result.event.source_change_fields)
    assert result.scope.milestone_ids == ()  # no guessed milestone dependency
    assert result.scope.whole_plan == (outcome == "affects_plan")
    assert result.scope.state == ("unresolved" if outcome == "undetermined" else "known")
    if outcome == "no_plan_impact":
        target, planned = result.event.target, result.plan.target
        if reason == "target_mismatch":
            assert (target.competition_id != planned.competition_id
                    or target.edition_id != planned.edition_id
                    or (target.track_id is not None and planned.track_id is not None
                        and target.track_id != planned.track_id))
        else:
            membership = result.event.source_changes[0]
            assert membership.before.state == membership.after.state == "known_value"
            assert planned.track_id in membership.before.value
            assert planned.track_id in membership.after.value
    elif outcome == "affects_plan":
        membership = result.event.source_changes[0]
        before, after = membership.before.value or (), membership.after.value or ()
        assert (result.plan.target.track_id in before) != (result.plan.target.track_id in after)
    else:
        assert reason in ("observation_only_event", "plan_dependency_not_represented")
    assert EventImpactAnalysis.model_validate_json(result.model_dump_json()) == result
    assert EventImpactAnalysis.model_validate(result.model_dump(mode="json")) == result


@pytest.mark.parametrize("target", [
    CompetitionTarget(competition_id="other", edition_id="edition"),
    CompetitionTarget(competition_id="competition", edition_id="other"),
    CompetitionTarget(competition_id="competition", edition_id="edition", track_id="b"),
])
@pytest.mark.parametrize("observation", [False, True])
def test_target_mismatch_is_negative_evidence_before_factual_or_observation_logic(target, observation):
    assert_result(analyze(event(target=target, after_state="unknown" if observation else "known_value")),
                  "no_plan_impact", "target_mismatch")


@pytest.mark.parametrize("field", [
    "registration_window.start_at", "registration_window.end_at",
    "competition_window.start_at", "competition_window.end_at",
])
def test_window_changes_missing_dependency_are_undetermined_even_with_supplied_dates(field):
    dated = plan(milestones=(PlanMilestone(
        id="m", title="报名 deadline competition track", description="registration end",
        start_at=T1, due_at=T2, estimated_hours=10,
    ),))
    assert_result(analyze(event(field=field), dated), "undetermined", "plan_dependency_not_represented")


@pytest.mark.parametrize("field", ["registration_window.end_at", "competition_window.end_at", "track_membership"])
@pytest.mark.parametrize("before_state,after_state", [
    ("known_value", "unknown"), ("unknown", "known_value"),
    ("known_absent", "unknown"), ("unknown", "known_absent"),
])
def test_observation_knowledge_changes_never_reinterpreted_as_fact_changes(field, before_state, after_state):
    source = event(field=field, before_state=before_state, after_state=after_state)
    assert_result(analyze(source), "undetermined", "observation_only_event")


@pytest.mark.parametrize("before,after,outcome,reason", [
    (("a",), ("b",), "affects_plan", "target_track_removed"),
    (("a", "b"), ("b", "c"), "affects_plan", "target_track_removed"),
    (("a",), ("a", "b"), "no_plan_impact", "unrelated_track_change"),
    (("a", "b"), ("a",), "no_plan_impact", "unrelated_track_change"),
    (("b",), ("a", "b"), "affects_plan", "plan_dependency_matched"),
    (("b",), ("c",), "undetermined", "plan_dependency_not_represented"),
])
def test_factual_track_lineage_with_frozen_p11_1_added_target_semantics(before, after, outcome, reason):
    source = event(field="track_membership", before_tracks=before, after_tracks=after)
    assert_result(analyze(source), outcome, reason)


@pytest.mark.parametrize("before_state,after_state,reason", [
    ("known_value", "known_absent", "target_track_removed"),
    ("known_absent", "known_value", "plan_dependency_matched"),
])
def test_explicit_membership_presence_transition_reuses_factual_contract(before_state, after_state, reason):
    source = event(field="track_membership", before_state=before_state, after_state=after_state, after_tracks=("a",))
    assert_result(analyze(source), "affects_plan", reason)


def test_edition_plan_does_not_invent_specific_track_dependency():
    source = event(field="track_membership")
    assert_result(analyze(source, plan(track_id=None)), "undetermined", "plan_dependency_not_represented")
    source = event(field="track_membership", target=CompetitionTarget(
        competition_id="competition", edition_id="edition", track_id="a",
    ))
    assert_result(analyze(source, plan(track_id=None)), "undetermined", "plan_dependency_not_represented")


def test_student_identity_conflict_rejected_and_other_profile_fields_irrelevant():
    with pytest.raises(ValueError, match="Student identity"):
        analyze(student=StudentProfile(id="other"))
    minimal = analyze()
    rich = analyze(student=StudentProfile(
        id="student", interests=["registration", "track a"], goals=["deadline"],
        major="competition", school="test school", weekly_available_hours=20,
    ))
    assert minimal.model_dump_json() == rich.model_dump_json()
    assert "student_profile" not in rich.model_dump()


@pytest.mark.parametrize("time", [T1, T3.replace(tzinfo=None)])
def test_invalid_or_reverse_explicit_evaluation_time_rejected(time):
    with pytest.raises(ValidationError):
        analyze(evaluated_at=time)


def test_time_required_and_evaluation_cannot_precede_plan_context():
    with pytest.raises(TypeError):
        CompetitionEventImpactAnalyzer().analyze(event(), StudentProfile(id="student"), plan())
    with pytest.raises(ValidationError):
        analyze(current=plan(updated_at=T3 + timedelta(days=1)))


@pytest.mark.parametrize("source", [
    event(), event(after_state="unknown"),
    event(field="track_membership"), event(field="track_membership", after_tracks=("a", "b")),
])
def test_full_input_preservation_determinism_immutable_output_and_json(source):
    student, current = StudentProfile(id="student", interests=["test"]), plan()
    before = (source.model_dump_json(), student.model_dump_json(), current.model_dump_json())
    first = analyze(source, current, student)
    second = analyze(source, current, student)
    assert first.model_dump_json() == second.model_dump_json()
    assert first == second
    assert before == (source.model_dump_json(), student.model_dump_json(), current.model_dump_json())
    for obj in (first, first.scope, first.evidence[0], first.plan, first.event):
        with pytest.raises(ValidationError):
            obj.extra = "mutated"
    with pytest.raises(TypeError):
        first.model_copy(update={})
    assert EventImpactAnalysis.model_validate_json(first.model_dump_json()) == first


@pytest.mark.parametrize("index", [0, 1, 2])
def test_untyped_inputs_are_rejected(index):
    inputs = [event(), StudentProfile(id="student"), plan()]
    inputs[index] = inputs[index].model_dump()
    with pytest.raises(TypeError):
        CompetitionEventImpactAnalyzer().analyze(*inputs, evaluated_at=T3)


def test_legacy_event_without_p10_lineage_is_rejected():
    from competition_copilot.domain.event import CompetitionEvent

    legacy = CompetitionEvent(
        id="historical", competition_id="competition", edition_id="edition",
        event_type="other", observed_at=T2, source=SOURCE,
    )
    with pytest.raises(ValueError, match="Diff-backed"):
        analyze(legacy)


def test_mutable_student_context_is_revalidated_without_mutation():
    student = StudentProfile(id="student")
    student.weekly_available_hours = -1  # ordinary mutable P1 profile assignment
    with pytest.raises(ValidationError):
        analyze(student=student)
    assert student.weekly_available_hours == -1
