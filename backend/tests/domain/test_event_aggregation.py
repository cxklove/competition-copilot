"""Supplied batch aggregation/dedup; fixtures are structured, not official history."""

import itertools
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
from competition_copilot.domain.event import (
    CompetitionEvent,
    competition_event_identity,
)
from competition_copilot.domain.event_aggregation import CompetitionEventAggregator
from competition_copilot.domain.event_engine import CompetitionEventEngine
from competition_copilot.domain.source_metadata import SourceMetadata

T1 = datetime(2030, 1, 1, tzinfo=timezone.utc)
T2 = T1 + timedelta(days=1)
TARGET = CompetitionTarget(competition_id="competition", edition_id="edition")
SOURCE = SourceMetadata(
    source_url="https://example.invalid/aggregation-fixture",
    source_type="manual",
    observed_at=T1,
    verification_status="verified",
)


def endpoint(field, observation=False):
    return WindowEndpointChange(
        field=field,
        kind="observation_state_changed" if observation else "value_changed",
        before=ObservedInstant(state="known_value", value=T1, sources=(SOURCE,)),
        after=ObservedInstant(state="unknown")
        if observation
        else ObservedInstant(
            state="known_value",
            value=T2,
            sources=(SOURCE,),
        ),
    )


def membership(observation=False):
    return TrackMembershipChange(
        field="track_membership",
        kind="observation_state_changed" if observation else "value_changed",
        before=ObservedTrackMembership(
            state="known_value", value=("a", "b"), sources=(SOURCE,)
        ),
        after=ObservedTrackMembership(state="unknown")
        if observation
        else ObservedTrackMembership(
            state="known_value",
            value=("a", "c"),
            sources=(SOURCE,),
        ),
    )


def primitives(*changes, target=TARGET, after_id="after"):
    diff = SnapshotDiff(
        before=SnapshotReference(snapshot_id="before", target=target, observed_at=T1),
        after=SnapshotReference(snapshot_id=after_id, target=target, observed_at=T2),
        changes=changes,
    )
    return CompetitionEventEngine().interpret(diff, detected_at=T2)


def normalize(events):
    return CompetitionEventAggregator().normalize(events)


def json_sequence(events):
    return tuple(event.model_dump_json() for event in events)


def reconstruct(event, **changes):
    return CompetitionEvent(**{**event.model_dump(), **changes})


def assert_serialization(events):
    for event in events:
        assert CompetitionEvent.model_validate_json(event.model_dump_json()) == event
        assert CompetitionEvent.model_validate(event.model_dump(mode="json")) == event


def test_empty_and_single_event_preserve_identity_target_time_lineage():
    assert normalize(()) == ()
    events = primitives(endpoint("registration_window.end_at"))
    assert normalize(events) == events
    assert_serialization(normalize(events))


@pytest.mark.parametrize("family", ["registration_window", "competition_window"])
def test_window_start_end_aggregate_with_all_changes_and_new_id(family):
    events = primitives(endpoint(family + ".start_at"), endpoint(family + ".end_at"))
    canonical = normalize(events)
    assert len(events) == 2 and len(canonical) == 1
    event = canonical[0]
    assert event.event_type == events[0].event_type
    assert event.source_change_fields == (family + ".start_at", family + ".end_at")
    assert event.source_changes == events[0].source_changes + events[1].source_changes
    assert event.source_diff == events[0].source_diff
    assert event.observed_at == T2 and event.target == TARGET
    assert event.id not in (events[0].id, events[1].id)
    assert normalize((events[0],))[0].id != event.id
    assert_serialization(canonical)


def test_track_add_and_remove_retained_in_one_frozen_membership_record():
    # P9 permits one membership record per Diff, containing the entire before/
    # after set. Do not fabricate two same-field changes or expand P10.2 mapping.
    events = primitives(membership())
    canonical = normalize(events + events)
    assert len(canonical) == 1 and len(canonical[0].source_changes) == 1
    change = canonical[0].source_changes[0]
    assert change.before.value == ("a", "b") and change.after.value == ("a", "c")
    assert canonical[0].event_type.value == "track_membership_changed"
    assert_serialization(canonical)


def test_observation_same_family_aggregates_but_other_families_stay_separate():
    events = primitives(
        endpoint("registration_window.start_at", True),
        endpoint("registration_window.end_at", True),
        membership(True),
    )
    canonical = normalize(events)
    assert len(canonical) == 2
    assert all(
        event.event_type.value == "observation_coverage_changed" for event in canonical
    )
    assert canonical[0].source_change_fields == (
        "registration_window.start_at",
        "registration_window.end_at",
    )
    assert canonical[1].source_change_fields == ("track_membership",)
    assert_serialization(canonical)


def test_fact_and_observation_same_family_never_merge():
    events = primitives(
        endpoint("registration_window.start_at"),
        endpoint("registration_window.end_at", True),
    )
    canonical = normalize(events)
    assert len(canonical) == 2
    assert [event.event_type.value for event in canonical] == [
        "registration_window_changed",
        "observation_coverage_changed",
    ]


def test_different_source_diff_cycles_do_not_merge():
    change = endpoint("registration_window.end_at")
    events = primitives(change, after_id="after-one") + primitives(
        change, after_id="after-two"
    )
    assert len(normalize(events)) == 2


def test_same_references_but_different_full_diff_lineage_do_not_merge():
    start = primitives(endpoint("registration_window.start_at"))[0]
    end = primitives(endpoint("registration_window.end_at"))[0]
    assert start.source_diff.before == end.source_diff.before
    assert start.source_diff.after == end.source_diff.after
    assert start.source_diff != end.source_diff
    assert len(normalize((start, end))) == 2


def test_different_targets_do_not_merge():
    change = endpoint("registration_window.end_at")
    other = CompetitionTarget(
        competition_id="other", edition_id="other", track_id="track"
    )
    canonical = normalize(primitives(change) + primitives(change, target=other))
    assert len(canonical) == 2 and {event.target for event in canonical} == {
        TARGET,
        other,
    }


def test_exact_duplicates_and_overlapping_source_lineage_are_unique():
    events = primitives(
        endpoint("registration_window.start_at"), endpoint("registration_window.end_at")
    )
    assert normalize((events[0], events[0])) == (events[0],)
    aggregate = normalize(events)[0]
    # Different valid IDs selecting overlapping fields (primitive + canonical
    # input) cannot repeat the start lineage in the normalized output.
    assert aggregate.id != events[0].id
    assert normalize((aggregate, events[0], events[1], aggregate)) == (aggregate,)
    assert len(aggregate.source_changes) == 2


@pytest.mark.parametrize(
    "changes",
    [{"observed_at": T2 + timedelta(hours=1)}, {"description": "Different display"}],
)
def test_same_id_different_content_rejected(changes):
    event = primitives(endpoint("registration_window.end_at"))[0]
    conflict = reconstruct(event, **changes)
    assert conflict.id == event.id
    with pytest.raises(ValueError, match="Same Event ID"):
        normalize((event, conflict))


def test_same_id_conflicting_full_diff_content_rejected():
    start = endpoint("registration_window.start_at")
    first = primitives(start)[0]
    second = primitives(start, endpoint("registration_window.end_at"))[0]
    assert first.id == second.id and first.source_diff != second.source_diff
    with pytest.raises(ValueError, match="Same Event ID"):
        normalize((first, second))


def test_aggregation_cannot_create_conflicting_ids_across_distinct_full_diffs():
    start = endpoint("registration_window.start_at")
    end = endpoint("registration_window.end_at")
    group_one = primitives(start, end, endpoint("competition_window.start_at"))[:2]
    group_two = primitives(start, end, endpoint("competition_window.end_at"))[:2]
    aggregate_two = normalize(group_two)[0]
    # All input IDs differ, but P10.1 IDs include selected changes/references,
    # not unrelated Diff fields. Never output same ID with conflicting full lineage.
    assert len({event.id for event in group_one + (aggregate_two,)}) == 3
    with pytest.raises(ValueError, match="Canonical Event ID conflicts"):
        normalize(group_one + (aggregate_two,))


def test_same_group_different_detection_times_rejected_not_min_max():
    first, second = primitives(
        endpoint("registration_window.start_at"), endpoint("registration_window.end_at")
    )
    later = reconstruct(second, observed_at=T2 + timedelta(hours=1))
    assert first.id != later.id
    with pytest.raises(ValueError, match="conflicting detection time"):
        normalize((first, later))


def test_input_order_independence_canonical_order_and_no_cross_run_state():
    events = primitives(
        endpoint("registration_window.start_at"),
        endpoint("registration_window.end_at"),
        endpoint("competition_window.start_at"),
        membership(True),
    )
    aggregator = CompetitionEventAggregator()
    expected = aggregator.normalize(events)
    assert [event.source_change_fields[0] for event in expected] == [
        "registration_window.start_at",
        "competition_window.start_at",
        "track_membership",
    ]
    for permutation in itertools.permutations(events):
        actual = aggregator.normalize(permutation)
        assert json_sequence(actual) == json_sequence(expected)
        assert [event.id for event in actual] == [event.id for event in expected]
    assert aggregator.normalize(events) == expected  # No processed-history suppression.
    assert_serialization(expected)


def test_equal_aware_instants_normalize_without_conflict_or_order_drift():
    event = primitives(endpoint("registration_window.end_at"))[0]
    localized = reconstruct(
        event, observed_at=T2.astimezone(timezone(timedelta(hours=8)))
    )
    assert event == localized
    assert json_sequence(normalize((event, localized))) == json_sequence(
        normalize((localized, event))
    )
    assert normalize((localized,))[0].observed_at.utcoffset() == timedelta(0)


def test_inputs_immutable_outputs_frozen_and_lineage_sources_preserved():
    events = primitives(
        endpoint("registration_window.start_at"), endpoint("registration_window.end_at")
    )
    original = json_sequence(events)
    result = normalize(events)
    assert json_sequence(events) == original
    assert all(SOURCE in change.before.sources for change in result[0].source_changes)
    with pytest.raises(AttributeError):
        result.append(None)
    with pytest.raises(ValidationError):
        result[0].id = "changed"
    with pytest.raises(ValidationError):
        result[0].source_changes[0].kind = "presence_changed"
    assert_serialization(result)


def test_invalid_untyped_or_legacy_inputs_are_rejected():
    with pytest.raises(TypeError):
        normalize([])
    with pytest.raises(TypeError):
        normalize(({},))
    legacy = CompetitionEvent(
        id="legacy",
        competition_id="competition",
        edition_id="edition",
        event_type="deadline_changed",
        observed_at=T2,
        source=SOURCE,
    )
    with pytest.raises(ValueError, match="P10 Diff-backed"):
        normalize((legacy,))


def test_multi_family_input_event_is_rejected_without_remapping_or_splitting():
    events = primitives(endpoint("registration_window.end_at", True), membership(True))
    reference = events[0]
    fields = ("registration_window.end_at", "track_membership")
    combined = reconstruct(
        reference,
        source_change_fields=fields,
        id=competition_event_identity(
            reference.event_type, reference.source_diff, fields
        ),
    )
    with pytest.raises(ValueError, match="one canonical field family"):
        normalize((combined,))
