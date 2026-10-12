"""Deterministic per-change mapping only; no aggregation/dedup behavior."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.digital_twin import (
    CompetitionTarget,
    ObservedInstant,
    ObservedTimeWindow,
    ObservedTrackMembership,
    SnapshotDiff,
    SnapshotReference,
    TimeWindowChange,
    TrackMembershipChange,
    WindowEndpointChange,
)
from competition_copilot.domain.event import CompetitionEvent, CompetitionEventCategory
from competition_copilot.domain.event_engine import CompetitionEventEngine
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.temporal import TimeWindow

T1 = datetime(2030, 1, 1, tzinfo=timezone.utc)
T2 = T1 + timedelta(days=1)
TARGET = CompetitionTarget(competition_id="competition", edition_id="edition")
BEFORE_SOURCE = SourceMetadata(
    source_url="https://example.invalid/before",
    source_type="manual",
    observed_at=T1,
    verification_status="verified",
)
AFTER_SOURCE = SourceMetadata(
    source_url="https://example.invalid/after",
    source_type="manual",
    observed_at=T2,
    verification_status="verified",
)


def diff(*changes, target=TARGET):
    return SnapshotDiff(
        before=SnapshotReference(snapshot_id="before", target=target, observed_at=T1),
        after=SnapshotReference(snapshot_id="after", target=target, observed_at=T2),
        changes=changes,
    )


def instant(state, value, source):
    return ObservedInstant(
        state=state,
        value=value if state == "known_value" else None,
        sources=() if state == "unknown" else (source,),
    )


def endpoint(field, before="known_value", after="known_value"):
    kind = (
        "observation_state_changed"
        if "unknown" in (before, after)
        else ("value_changed" if before == after else "presence_changed")
    )
    return WindowEndpointChange(
        field=field,
        kind=kind,
        before=instant(before, T1, BEFORE_SOURCE),
        after=instant(after, T2, AFTER_SOURCE),
    )


def whole_change(field, before, after):
    kind = (
        "observation_state_changed"
        if "unknown" in (before, after)
        else "presence_changed"
    )
    if field == "track_membership":

        def fact(state, source):
            return ObservedTrackMembership(
                state=state,
                value=("a",) if state == "known_value" else None,
                sources=() if state == "unknown" else (source,),
            )

        return TrackMembershipChange(
            field=field,
            kind=kind,
            before=fact(before, BEFORE_SOURCE),
            after=fact(after, AFTER_SOURCE),
        )

    def fact(state, source):
        return ObservedTimeWindow(
            state=state,
            value=TimeWindow(end_at=T1) if state == "known_value" else None,
            sources=() if state == "unknown" else (source,),
        )

    return TimeWindowChange(
        field=field,
        kind=kind,
        before=fact(before, BEFORE_SOURCE),
        after=fact(after, AFTER_SOURCE),
    )


def interpret(source_diff, detected_at=T2):
    return CompetitionEventEngine().interpret(source_diff, detected_at=detected_at)


def sequence_json(events):
    return json.dumps(
        [event.model_dump(mode="json") for event in events], sort_keys=True
    )


def assert_lineage(events, source_diff):
    assert len(events) == len(source_diff.changes)
    for event in events:
        assert event.target == source_diff.after.target
        assert event.source_diff.before == source_diff.before
        assert event.source_diff.after == source_diff.after
        assert event.source_diff.changes == tuple(
            sorted(
                source_diff.changes,
                key=lambda item: (
                    "registration_window",
                    "registration_window.start_at",
                    "registration_window.end_at",
                    "competition_window",
                    "competition_window.start_at",
                    "competition_window.end_at",
                    "track_membership",
                ).index(item.field),
            )
        )
        assert len(event.source_changes) == 1
        assert event.source_change_fields == (event.source_changes[0].field,)
        assert event.source_changes[0] in source_diff.changes
        assert event.observed_at == T2 and event.occurred_at is None
        assert CompetitionEvent.model_validate_json(event.model_dump_json()) == event


def test_zero_diff_and_reflexive_diff_produce_empty_immutable_sequence():
    assert interpret(diff()) == ()
    reference = diff().before
    assert interpret(SnapshotDiff(before=reference, after=reference)) == ()
    assert sequence_json(interpret(diff())) == "[]"


@pytest.mark.parametrize(
    "field,event_type",
    [
        ("registration_window.start_at", "registration_window_changed"),
        ("registration_window.end_at", "registration_window_changed"),
        ("competition_window.start_at", "competition_window_changed"),
        ("competition_window.end_at", "competition_window_changed"),
    ],
)
def test_window_value_changes_map_to_factual_type(field, event_type):
    source_diff = diff(endpoint(field))
    events = interpret(source_diff)
    assert events[0].event_type.value == event_type
    assert events[0].category == CompetitionEventCategory.FACT_CHANGE
    assert events[0].source == AFTER_SOURCE
    assert_lineage(events, source_diff)


def test_two_registration_changes_are_two_events_not_aggregated():
    source_diff = diff(
        endpoint("registration_window.start_at"), endpoint("registration_window.end_at")
    )
    events = interpret(source_diff)
    assert len(events) == 2
    assert all(
        event.event_type.value == "registration_window_changed" for event in events
    )
    assert events[0].id != events[1].id
    assert events[0].source_change_fields != events[1].source_change_fields
    assert_lineage(events, source_diff)


@pytest.mark.parametrize("before,after", [(("a",), ("a", "b")), (("a", "b"), ("a",))])
def test_track_member_add_remove_remains_one_membership_event(before, after):
    change = TrackMembershipChange(
        field="track_membership",
        kind="value_changed",
        before=ObservedTrackMembership(
            state="known_value", value=before, sources=(BEFORE_SOURCE,)
        ),
        after=ObservedTrackMembership(
            state="known_value", value=after, sources=(AFTER_SOURCE,)
        ),
    )
    source_diff = diff(change)
    events = interpret(source_diff)
    assert len(events) == 1 and events[0].event_type.value == "track_membership_changed"
    assert events[0].source_changes == (change,)
    assert_lineage(events, source_diff)


@pytest.mark.parametrize(
    "field", ["registration_window", "competition_window", "track_membership"]
)
@pytest.mark.parametrize(
    "before,after",
    [
        ("unknown", "known_value"),
        ("known_value", "unknown"),
        ("unknown", "known_absent"),
        ("known_absent", "unknown"),
    ],
)
def test_whole_observation_transitions_never_become_factual_events(
    field, before, after
):
    source_diff = diff(whole_change(field, before, after))
    events = interpret(source_diff)
    assert len(events) == 1
    assert events[0].event_type.value == "observation_coverage_changed"
    assert events[0].category == CompetitionEventCategory.OBSERVATION_CHANGE
    assert events[0].source == (BEFORE_SOURCE if after == "unknown" else AFTER_SOURCE)
    assert_lineage(events, source_diff)


@pytest.mark.parametrize(
    "field", ["registration_window", "competition_window", "track_membership"]
)
@pytest.mark.parametrize(
    "before,after",
    [
        ("known_value", "known_absent"),
        ("known_absent", "known_value"),
    ],
)
def test_explicit_presence_transitions_are_factual(field, before, after):
    source_diff = diff(whole_change(field, before, after))
    events = interpret(source_diff)
    assert events[0].event_type.value == field + "_changed"
    assert events[0].category == CompetitionEventCategory.FACT_CHANGE
    assert_lineage(events, source_diff)


@pytest.mark.parametrize(
    "field", ["registration_window.start_at", "registration_window.end_at"]
)
@pytest.mark.parametrize(
    "before,after", [("unknown", "known_value"), ("known_value", "unknown")]
)
def test_partial_window_endpoint_knowledge_change_is_observation(field, before, after):
    events = interpret(diff(endpoint(field, before, after)))
    assert events[0].event_type.value == "observation_coverage_changed"


def test_canonical_order_identity_serialization_and_input_immutability():
    source_diff = diff(
        whole_change("track_membership", "known_value", "unknown"),
        endpoint("competition_window.end_at"),
        endpoint("registration_window.end_at"),
        endpoint("registration_window.start_at"),
    )
    original = source_diff.model_dump_json()
    engine = CompetitionEventEngine()
    first = engine.interpret(source_diff, detected_at=T2)
    second = engine.interpret(source_diff, detected_at=T2)
    assert [event.source_change_fields[0] for event in first] == [
        "registration_window.start_at",
        "registration_window.end_at",
        "competition_window.end_at",
        "track_membership",
    ]
    assert first == second
    assert [event.id for event in first] == [event.id for event in second]
    assert sequence_json(first) == sequence_json(second)
    assert [event.model_dump_json() for event in first] == [
        event.model_dump_json() for event in second
    ]
    assert source_diff.model_dump_json() == original
    assert_lineage(first, source_diff)
    with pytest.raises(AttributeError):
        first.append(None)
    with pytest.raises(ValidationError):
        first[0].id = "changed"
    with pytest.raises(ValidationError):
        first[0].source_changes[0].kind = "presence_changed"


@pytest.mark.parametrize("time", [T2.replace(tzinfo=None), T1])
def test_naive_or_pre_observation_detection_time_rejected_even_for_zero_diff(time):
    with pytest.raises(ValueError):
        interpret(diff(), time)


def test_explicit_aware_detection_context_without_business_occurred_time():
    source_diff = diff(endpoint("registration_window.end_at"))
    late = T2 + timedelta(hours=3)
    events = interpret(source_diff, late)
    assert events[0].observed_at == late and events[0].occurred_at is None
    assert events[0].id == interpret(source_diff)[0].id
    localized = late.astimezone(timezone(timedelta(hours=8)))
    assert interpret(source_diff, localized)[0].observed_at == late
    with pytest.raises(TypeError):
        CompetitionEventEngine().interpret(source_diff)


def test_wrong_input_and_unknown_fields_or_kinds_fail_validation():
    with pytest.raises(TypeError):
        interpret({})
    # Frozen P9 literals/enums cannot represent unknown field/kind; no bypass.
    values = endpoint("registration_window.end_at").model_dump()
    for updates in ({"field": "quota"}, {"kind": "generic_changed"}):
        with pytest.raises(ValidationError):
            WindowEndpointChange(**{**values, **updates})


def test_track_target_is_preserved():
    target = CompetitionTarget(
        competition_id="competition", edition_id="edition", track_id="track"
    )
    events = interpret(diff(endpoint("competition_window.end_at"), target=target))
    assert events[0].target == target
