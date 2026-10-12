"""P9.1 validated synthetic contracts; no builder, comparison engine or IO."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.digital_twin import (
    CompetitionDynamicState,
    CompetitionSnapshot,
    CompetitionTarget,
    FactChangeKind,
    ObservationState,
    ObservedInstant,
    ObservedTimeWindow,
    ObservedTrackMembership,
    SnapshotDiff,
    SnapshotReference,
    TimeWindowChange,
    TrackMembershipChange,
    WindowEndpointChange,
)
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.temporal import TimeWindow

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=1)


def source(**updates):
    return SourceMetadata.model_validate(
        {
            "source_url": "https://example.org/test-only-observation",
            "source_type": "official",
            "observed_at": NOW,
            "verification_status": "verified",
            **updates,
        }
    )


def window(state="known_value", value=None):
    return ObservedTimeWindow(
        state=state,
        value=(TimeWindow(end_at=LATER) if value is None else value)
        if state == "known_value"
        else None,
        sources=(source(),) if state != "unknown" else (),
    )


def tracks(state="known_value", value=()):
    return ObservedTrackMembership(
        state=state,
        value=value if state == "known_value" else None,
        sources=(source(),) if state != "unknown" else (),
    )


def instant(state="known_value", value=LATER):
    return ObservedInstant(
        state=state,
        value=value if state == "known_value" else None,
        sources=(source(),) if state != "unknown" else (),
    )


def target(track_id=None):
    return CompetitionTarget(
        competition_id="competition-a", edition_id="edition-a", track_id=track_id
    )


def snapshot(snapshot_id="snapshot-a", observed_at=NOW, track_id=None):
    return CompetitionSnapshot(
        snapshot_id=snapshot_id,
        target=target(track_id),
        observed_at=observed_at,
        dynamic_state=CompetitionDynamicState(
            registration_window=window(),
            competition_window=window("unknown"),
            track_membership=tracks(),
        ),
    )


def reference(snapshot_id="snapshot-a", observed_at=NOW, track_id=None):
    return SnapshotReference(
        snapshot_id=snapshot_id, target=target(track_id), observed_at=observed_at
    )


@pytest.mark.parametrize("track_id", [None, "track-a"])
def test_snapshot_target_and_observation_identity(track_id):
    first = snapshot(track_id=track_id)
    second = snapshot("snapshot-b", LATER, track_id)
    assert first.target == target(track_id)
    assert first.dynamic_state == second.dynamic_state
    assert first.snapshot_id != second.snapshot_id
    assert first.observed_at != second.observed_at
    assert first.model_dump(mode="json")["target"]["track_id"] == track_id


@pytest.mark.parametrize("field", ["competition_id", "edition_id", "track_id"])
@pytest.mark.parametrize("invalid", [" ", 123])
def test_invalid_target_identity(field, invalid):
    with pytest.raises(ValidationError):
        CompetitionTarget.model_validate({**target().model_dump(), field: invalid})


def test_snapshot_requires_explicit_aware_time_and_identity():
    payload = snapshot().model_dump()
    for field in ("snapshot_id", "observed_at"):
        with pytest.raises(ValidationError):
            CompetitionSnapshot.model_validate(
                {k: v for k, v in payload.items() if k != field}
            )
    with pytest.raises(ValidationError):
        CompetitionSnapshot.model_validate(
            {**payload, "observed_at": NOW.replace(tzinfo=None)}
        )
    with pytest.raises(ValidationError):
        snapshot(observed_at=NOW - timedelta(seconds=1))


@pytest.mark.parametrize(
    "model,value",
    [
        (ObservedInstant, LATER),
        (ObservedTimeWindow, TimeWindow(end_at=LATER)),
        (ObservedTrackMembership, ("track-a",)),
    ],
)
@pytest.mark.parametrize("state", list(ObservationState))
def test_observation_states(model, value, state):
    fact = model(
        state=state,
        value=value if state == ObservationState.KNOWN_VALUE else None,
        sources=(source(),) if state != ObservationState.UNKNOWN else (),
    )
    assert fact.state == state
    assert (fact.value is not None) == (state == ObservationState.KNOWN_VALUE)


@pytest.mark.parametrize(
    "model,value",
    [
        (ObservedInstant, LATER),
        (ObservedTimeWindow, TimeWindow(end_at=LATER)),
        (ObservedTrackMembership, ()),
    ],
)
@pytest.mark.parametrize("state", list(ObservationState))
def test_illegal_state_value_combinations(model, value, state):
    with pytest.raises(ValidationError):
        model(
            state=state,
            value=None if state == ObservationState.KNOWN_VALUE else value,
            sources=(source(),),
        )


def test_unknown_absent_and_known_empty_are_distinct():
    unknown, absent, empty = tracks("unknown"), tracks("known_absent"), tracks()
    assert len({fact.model_dump_json() for fact in (unknown, absent, empty)}) == 3
    assert unknown.value is None and absent.value is None and empty.value == ()


def test_known_windows_reuse_full_partial_and_empty_bounds():
    full = window(value=TimeWindow(start_at=NOW, end_at=LATER))
    partial = window()
    known_without_bounds = window(value=TimeWindow())
    unknown = window("unknown")
    assert full.value.start_at == NOW
    assert partial.value.start_at is None and partial.value.end_at == LATER
    assert known_without_bounds.value == TimeWindow()
    assert unknown.value is None
    assert (
        len(
            {
                f.model_dump_json()
                for f in (full, partial, known_without_bounds, unknown)
            }
        )
        == 4
    )
    for payload in (
        {"start_at": LATER, "end_at": NOW},
        {"end_at": NOW.replace(tzinfo=None)},
    ):
        with pytest.raises(ValidationError):
            ObservedTimeWindow(state="known_value", value=payload, sources=(source(),))


def test_track_ids_sorted_unique_and_immutable():
    fact = tracks(value=["track-b", "track-a"])
    assert fact.value == ("track-a", "track-b")
    assert fact == tracks(value=("track-a", "track-b"))
    with pytest.raises(ValidationError):
        tracks(value=("track-a", " track-a "))
    with pytest.raises(ValidationError):
        tracks(value=(" ",))


@pytest.mark.parametrize("state", ["known_value", "known_absent"])
@pytest.mark.parametrize(
    "sources",
    [
        (),
        (source(verification_status="pending"),),
        (source(verification_status="rejected"),),
    ],
)
def test_known_fact_requires_verified_provenance(state, sources):
    with pytest.raises(ValidationError):
        ObservedTimeWindow(
            state=state,
            value=TimeWindow() if state == "known_value" else None,
            sources=sources,
        )


def test_fact_level_sources_are_independent_and_preserved():
    other = source(
        source_url="https://example.org/another-source", source_type="university"
    )
    registration = window()
    competition = ObservedTimeWindow(
        state="known_value", value=TimeWindow(), sources=[other]
    )
    state = CompetitionDynamicState(
        registration_window=registration,
        competition_window=competition,
        track_membership=tracks(),
    )
    assert state.registration_window.sources == (source(),)
    assert state.competition_window.sources == (other,)
    assert state.registration_window.sources != state.competition_window.sources
    unknown = ObservedTimeWindow(
        state="unknown", sources=(source(verification_status="pending"),)
    )
    assert unknown.value is None


def test_snapshot_nested_immutability_and_serialization():
    item = snapshot()
    for model, field, value in (
        (item, "snapshot_id", "other"),
        (item.target, "track_id", "other"),
        (item.dynamic_state, "track_membership", tracks("unknown")),
        (item.dynamic_state.registration_window, "state", ObservationState.UNKNOWN),
        (item.dynamic_state.registration_window.value, "end_at", NOW),
        (item.dynamic_state.registration_window.sources[0], "source_type", "manual"),
    ):
        with pytest.raises(ValidationError):
            setattr(model, field, value)
    with pytest.raises(AttributeError):
        item.dynamic_state.track_membership.value.append("other")
    with pytest.raises(TypeError):
        item.model_copy(update={"snapshot_id": "other"})
    assert CompetitionSnapshot.model_validate_json(item.model_dump_json()) == item
    assert item.model_dump_json() == snapshot().model_dump_json()
    assert (
        item.model_dump(mode="json")["dynamic_state"]["competition_window"]["state"]
        == "unknown"
    )


def test_diff_references_direction_and_unchanged_state():
    diff = SnapshotDiff(before=reference(), after=reference("snapshot-b", LATER))
    assert (
        diff.before.snapshot_id == "snapshot-a"
        and diff.after.snapshot_id == "snapshot-b"
    )
    assert diff.changes == ()
    same_time = SnapshotDiff(before=reference(), after=reference("snapshot-b"))
    assert same_time.before.observed_at == same_time.after.observed_at
    with pytest.raises(ValidationError):
        SnapshotDiff(before=diff.after, after=diff.before)
    with pytest.raises(ValidationError):
        SnapshotDiff(before=reference(), after=reference())
    for mismatched in (
        target("track-a"),
        CompetitionTarget(competition_id="other", edition_id="edition-a"),
        CompetitionTarget(competition_id="competition-a", edition_id="other"),
    ):
        with pytest.raises(ValidationError):
            SnapshotDiff(
                before=reference(),
                after=SnapshotReference(
                    snapshot_id="snapshot-b", target=mismatched, observed_at=LATER
                ),
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
def test_unknown_transitions_are_observation_changes_only(before, after):
    change = TimeWindowChange(
        field="registration_window",
        kind="observation_state_changed",
        before=window(before),
        after=window(after),
    )
    assert change.kind == FactChangeKind.OBSERVATION_STATE_CHANGED
    for kind in ("value_changed", "presence_changed"):
        with pytest.raises(ValidationError):
            TimeWindowChange(
                field=change.field, kind=kind, before=change.before, after=change.after
            )


def test_known_value_and_presence_changes_are_typed():
    changed = WindowEndpointChange(
        field="competition_window.end_at",
        kind="value_changed",
        before=instant(),
        after=instant(value=LATER + timedelta(days=1)),
    )
    assert changed.before.value != changed.after.value
    presence = TimeWindowChange(
        field="registration_window",
        kind="presence_changed",
        before=window(),
        after=window("known_absent"),
    )
    assert presence.after.state == ObservationState.KNOWN_ABSENT
    with pytest.raises(ValidationError):
        WindowEndpointChange(
            field="competition_window.end_at",
            kind="value_changed",
            before=instant(),
            after=instant(),
        )
    with pytest.raises(ValidationError):
        WindowEndpointChange(
            field="competition_window.end_at",
            kind="observation_state_changed",
            before=changed.before,
            after=changed.after,
        )
    with pytest.raises(ValidationError):
        TimeWindowChange(
            field="competition_window",
            kind="value_changed",
            before=window(),
            after=window(value=TimeWindow(end_at=NOW)),
        )


def test_partial_window_endpoint_unknown_to_known_is_observation_change():
    before_window = window(value=TimeWindow(end_at=LATER))
    after_window = window(value=TimeWindow(start_at=NOW, end_at=LATER))
    assert before_window.state == after_window.state == ObservationState.KNOWN_VALUE
    assert before_window.value.start_at is None and after_window.value.start_at == NOW
    change = WindowEndpointChange(
        field="registration_window.start_at",
        kind="observation_state_changed",
        before=instant("unknown"),
        after=instant(value=NOW),
    )
    assert change.kind == FactChangeKind.OBSERVATION_STATE_CHANGED
    with pytest.raises(ValidationError):
        WindowEndpointChange(
            field=change.field,
            kind="value_changed",
            before=change.before,
            after=change.after,
        )
    with pytest.raises(ValidationError):
        ObservedInstant(
            state="known_value", value=NOW.replace(tzinfo=None), sources=(source(),)
        )
    diff = SnapshotDiff(
        before=reference(), after=reference("snapshot-b", LATER), changes=(change,)
    )
    assert SnapshotDiff.model_validate_json(diff.model_dump_json()) == diff


def test_track_membership_changes_require_known_sets():
    change = TrackMembershipChange(
        field="track_membership",
        kind="value_changed",
        before=tracks(value=("track-a",)),
        after=tracks(value=("track-b",)),
    )
    assert set(change.after.value) - set(change.before.value) == {"track-b"}
    assert set(change.before.value) - set(change.after.value) == {"track-a"}
    with pytest.raises(ValidationError):
        TrackMembershipChange(
            field="track_membership",
            kind="value_changed",
            before=tracks(value=("track-a",)),
            after=tracks("unknown"),
        )
    observation = TrackMembershipChange(
        field="track_membership",
        kind="observation_state_changed",
        before=tracks("unknown"),
        after=tracks(),
    )
    assert observation.kind == FactChangeKind.OBSERVATION_STATE_CHANGED


def test_diff_changes_immutable_typed_serializable_and_unique():
    change = TimeWindowChange(
        field="registration_window",
        kind="observation_state_changed",
        before=window("unknown"),
        after=window(),
    )
    incoming = [change]
    diff = SnapshotDiff(
        before=reference(), after=reference("snapshot-b", LATER), changes=incoming
    )
    incoming.clear()
    assert diff.changes == (change,)
    with pytest.raises(ValidationError):
        diff.changes[0].kind = FactChangeKind.VALUE_CHANGED
    with pytest.raises(AttributeError):
        diff.changes.append(change)
    with pytest.raises(ValidationError):
        SnapshotDiff(before=diff.before, after=diff.after, changes=(change, change))
    endpoint_change = WindowEndpointChange(
        field="registration_window.end_at",
        kind="observation_state_changed",
        before=instant("unknown"),
        after=instant(),
    )
    with pytest.raises(ValidationError):
        SnapshotDiff(
            before=diff.before, after=diff.after, changes=(change, endpoint_change)
        )
    assert SnapshotDiff.model_validate_json(diff.model_dump_json()) == diff
    assert (
        diff.model_dump(mode="json")["changes"][0]["kind"]
        == "observation_state_changed"
    )
    payload = diff.model_dump()
    for invalid in (
        {"field": "deadline_changed", "before": 1, "after": 2},
        {
            **change.model_dump(),
            "before": {"state": "known_value", "value": "free text"},
        },
    ):
        with pytest.raises(ValidationError):
            SnapshotDiff.model_validate({**payload, "changes": [invalid]})


def test_contract_has_no_event_impact_plan_or_untyped_payload():
    forbidden = {
        "event_type",
        "impact",
        "severity",
        "plan_id",
        "replan_reason",
        "description",
    }
    for model in (
        CompetitionSnapshot,
        CompetitionDynamicState,
        SnapshotDiff,
        TimeWindowChange,
        WindowEndpointChange,
        TrackMembershipChange,
    ):
        assert not forbidden.intersection(model.model_fields)
    with pytest.raises(ValidationError):
        SnapshotDiff.model_validate(
            {
                **SnapshotDiff(
                    before=reference(), after=reference("snapshot-b", LATER)
                ).model_dump(),
                "event_type": "deadline_changed",
            }
        )
