"""Synthetic validated P9.3 comparison fixtures; no Repository or source IO."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.digital_twin import (
    CompetitionDynamicState,
    CompetitionSnapshot,
    CompetitionTarget,
    FactChangeKind,
    ObservedTimeWindow,
    ObservedTrackMembership,
    SnapshotDiff,
)
from competition_copilot.domain.snapshot_diff_engine import SnapshotDiffEngine
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.temporal import TimeWindow

SOURCE_TIME = datetime(2025, 1, 1, tzinfo=timezone.utc)
CAPTURE = datetime(2026, 5, 1, tzinfo=timezone.utc)
A = datetime(2026, 1, 10, tzinfo=timezone.utc)
B = datetime(2026, 1, 20, tzinfo=timezone.utc)
TARGET = CompetitionTarget(competition_id="test-competition", edition_id="test-edition")


def source(observed_at=SOURCE_TIME):
    return SourceMetadata(
        source_url="https://example.org/test-only-diff-source",
        source_type="official",
        observed_at=observed_at,
        verification_status="verified",
    )


def window(state="known_value", *, start=None, end=B, provenance=None):
    return ObservedTimeWindow(
        state=state,
        value=TimeWindow(start_at=start, end_at=end)
        if state == "known_value"
        else None,
        sources=(provenance or source(),) if state != "unknown" else (),
    )


def tracks(state="known_value", ids=("a", "b"), provenance=None):
    return ObservedTrackMembership(
        state=state,
        value=ids if state == "known_value" else None,
        sources=(provenance or source(),) if state != "unknown" else (),
    )


def snapshot(snapshot_id="before", observed_at=CAPTURE, target=TARGET, **facts):
    state = {
        "registration_window": window("unknown"),
        "competition_window": window("unknown"),
        "track_membership": tracks("unknown"),
        **facts,
    }
    return CompetitionSnapshot(
        snapshot_id=snapshot_id,
        target=target,
        observed_at=observed_at,
        dynamic_state=CompetitionDynamicState(**state),
    )


def compare(left, right):
    return SnapshotDiffEngine().compare(snapshot(**left), snapshot("after", **right))


@pytest.mark.parametrize(
    "field", ["registration_window", "competition_window", "track_membership"]
)
@pytest.mark.parametrize(
    "before_state,after_state,expected",
    [
        ("unknown", "unknown", None),
        ("unknown", "known_value", "observation_state_changed"),
        ("known_value", "unknown", "observation_state_changed"),
        ("known_value", "known_value", None),
        ("known_absent", "known_absent", None),
        ("known_absent", "known_value", "presence_changed"),
        ("known_value", "known_absent", "presence_changed"),
        ("unknown", "known_absent", "observation_state_changed"),
        ("known_absent", "unknown", "observation_state_changed"),
    ],
)
def test_whole_observation_matrix(field, before_state, after_state, expected):
    fact = tracks if field == "track_membership" else window
    result = compare({field: fact(before_state)}, {field: fact(after_state)})
    if expected is None:
        assert result.changes == ()
    else:
        assert len(result.changes) == 1
        change = result.changes[0]
        assert change.field == field
        assert change.kind.value == expected
        assert change.before.state.value == before_state
        assert change.after.state.value == after_state
        if "unknown" in (before_state, after_state):
            assert change.kind == FactChangeKind.OBSERVATION_STATE_CHANGED
            assert change.kind != FactChangeKind.PRESENCE_CHANGED
            assert change.kind != FactChangeKind.VALUE_CHANGED


@pytest.mark.parametrize("field", ["registration_window", "competition_window"])
@pytest.mark.parametrize("boundary", ["start_at", "end_at"])
@pytest.mark.parametrize(
    "before_value,after_value,expected",
    [
        (None, None, None),
        (None, A, "observation_state_changed"),
        (A, None, "observation_state_changed"),
        (A, A, None),
        (A, B, "value_changed"),
    ],
)
def test_window_endpoint_matrix(field, boundary, before_value, after_value, expected):
    left_values = {"start": None, "end": None}
    right_values = dict(left_values)
    argument = "start" if boundary == "start_at" else "end"
    left_values[argument] = before_value
    right_values[argument] = after_value
    result = compare({field: window(**left_values)}, {field: window(**right_values)})
    if expected is None:
        assert result.changes == ()
    else:
        assert len(result.changes) == 1
        change = result.changes[0]
        assert change.field == f"{field}.{boundary}"
        assert change.kind.value == expected
        assert change.before.value == before_value
        assert change.after.value == after_value
        assert change.before.sources == change.after.sources == (source(),)


@pytest.mark.parametrize(
    "before_ids,after_ids,added,removed",
    [
        (("a", "b"), ("a", "b", "c"), {"c"}, set()),
        (("a", "b", "c"), ("a", "c"), set(), {"b"}),
        ((), ("a",), {"a"}, set()),
        (("a",), (), set(), {"a"}),
        (("a", "b"), ("b", "c"), {"c"}, {"a"}),
    ],
)
def test_known_track_set_changes_preserve_added_and_removed_ids(
    before_ids, after_ids, added, removed
):
    result = compare(
        {"track_membership": tracks(ids=before_ids)},
        {"track_membership": tracks(ids=after_ids)},
    )
    assert len(result.changes) == 1
    change = result.changes[0]
    assert (
        change.field == "track_membership"
        and change.kind == FactChangeKind.VALUE_CHANGED
    )
    assert set(change.after.value) - set(change.before.value) == added
    assert set(change.before.value) - set(change.after.value) == removed
    assert change.before.value == tuple(sorted(before_ids))
    assert change.after.value == tuple(sorted(after_ids))


def test_same_exact_snapshot_and_distinct_same_state_are_zero_changes():
    before = snapshot(registration_window=window(), track_membership=tracks())
    engine = SnapshotDiffEngine()
    reflexive = engine.compare(before, before)
    assert reflexive.before == reflexive.after
    assert reflexive.changes == ()
    after = snapshot(
        "after",
        CAPTURE + timedelta(days=1),
        registration_window=window(),
        track_membership=tracks(),
    )
    result = engine.compare(before, after)
    assert result.changes == ()
    assert result.before.snapshot_id == "before" and result.after.snapshot_id == "after"
    assert result.before.observed_at < result.after.observed_at
    assert SnapshotDiff.model_validate_json(reflexive.model_dump_json()) == reflexive


@pytest.mark.parametrize(
    "target",
    [
        CompetitionTarget(competition_id="other", edition_id="test-edition"),
        CompetitionTarget(competition_id="test-competition", edition_id="other"),
        CompetitionTarget(
            competition_id="test-competition",
            edition_id="test-edition",
            track_id="other",
        ),
    ],
)
def test_target_mismatch_rejected(target):
    with pytest.raises(ValidationError):
        SnapshotDiffEngine().compare(snapshot(), snapshot("after", target=target))


def test_reverse_time_rejected_and_equal_time_allowed():
    with pytest.raises(ValidationError):
        SnapshotDiffEngine().compare(
            snapshot(observed_at=CAPTURE + timedelta(days=1)), snapshot("after")
        )
    assert SnapshotDiffEngine().compare(snapshot(), snapshot("after")).changes == ()


def test_same_id_conflicting_time_or_content_rejected():
    before = snapshot()
    with pytest.raises(ValidationError):
        SnapshotDiffEngine().compare(
            before, snapshot(observed_at=CAPTURE + timedelta(days=1))
        )
    with pytest.raises(ValueError, match="different snapshot content"):
        SnapshotDiffEngine().compare(before, snapshot(registration_window=window()))


def test_provenance_only_changes_are_ignored_as_fact_changes():
    other_source = source(SOURCE_TIME + timedelta(days=1))
    result = compare(
        {"registration_window": window(), "track_membership": tracks()},
        {
            "registration_window": window(provenance=other_source),
            "track_membership": tracks(provenance=other_source),
        },
    )
    assert result.changes == ()


def test_fixed_change_order_determinism_audit_and_input_immutability():
    before = snapshot(
        registration_window=window(start=A, end=B),
        competition_window=window(end=B),
        track_membership=tracks(),
    )
    after = snapshot(
        "after",
        registration_window=window(
            start=A + timedelta(days=1), end=B + timedelta(days=1)
        ),
        competition_window=window(end=B + timedelta(days=2)),
        track_membership=tracks(ids=("c", "b")),
    )
    before_json, after_json = before.model_dump_json(), after.model_dump_json()
    engine = SnapshotDiffEngine()
    first, second = engine.compare(before, after), engine.compare(before, after)
    assert first == second and first.model_dump_json() == second.model_dump_json()
    assert [change.field for change in first.changes] == [
        "registration_window.start_at",
        "registration_window.end_at",
        "competition_window.end_at",
        "track_membership",
    ]
    assert (
        first.changes[0].before.sources
        == before.dynamic_state.registration_window.sources
    )
    assert (
        first.changes[0].after.sources
        == after.dynamic_state.registration_window.sources
    )
    assert (
        before.model_dump_json() == before_json
        and after.model_dump_json() == after_json
    )
    assert SnapshotDiff.model_validate_json(first.model_dump_json()) == first
    assert first.model_dump(mode="json")["changes"][0]["kind"] == "value_changed"
    with pytest.raises(ValidationError):
        first.changes[0].kind = FactChangeKind.PRESENCE_CHANGED
    with pytest.raises(AttributeError):
        first.changes.append(first.changes[0])


@pytest.mark.parametrize(
    "right",
    [
        {},
        {"registration_window": window()},
        {"registration_window": window(end=A)},
        {"track_membership": tracks()},
    ],
)
def test_serialization_for_zero_observation_endpoint_and_tracks(right):
    result = compare({"registration_window": window()}, right)
    assert SnapshotDiff.model_validate_json(result.model_dump_json()) == result
    assert result.model_dump(mode="json")["changes"] == [
        change.model_dump(mode="json") for change in result.changes
    ]
