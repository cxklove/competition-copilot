"""Supplied event Contract only; no Diff classification/aggregation engine."""

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
from competition_copilot.domain.event import (
    CompetitionEvent,
    CompetitionEventCategory,
    CompetitionEventType,
    competition_event_identity,
)
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.temporal import TimeWindow

T1 = datetime(2030, 1, 1, tzinfo=timezone.utc)
T2 = T1 + timedelta(days=1)
TARGET = CompetitionTarget(competition_id="competition", edition_id="edition")
SOURCE = SourceMetadata(
    source_url="https://example.invalid/p10-contract-fixture",
    source_type="manual",
    observed_at=T1,
    verification_status="verified",
)


def endpoint(field="registration_window.end_at", unknown=False):
    return WindowEndpointChange(
        field=field,
        kind="observation_state_changed" if unknown else "value_changed",
        before=ObservedInstant(state="known_value", value=T1, sources=(SOURCE,)),
        after=(
            ObservedInstant(state="unknown")
            if unknown
            else ObservedInstant(state="known_value", value=T2, sources=(SOURCE,))
        ),
    )


def diff(*changes, target=TARGET):
    return SnapshotDiff(
        before=SnapshotReference(snapshot_id="before", target=target, observed_at=T1),
        after=SnapshotReference(snapshot_id="after", target=target, observed_at=T2),
        changes=changes,
    )


def payload(event_type="registration_window_changed", source_diff=None, fields=None):
    source_diff = diff(endpoint()) if source_diff is None else source_diff
    fields = (
        tuple(change.field for change in source_diff.changes)
        if fields is None
        else fields
    )
    return dict(
        id=competition_event_identity(event_type, source_diff, fields),
        competition_id=source_diff.after.target.competition_id,
        edition_id=source_diff.after.target.edition_id,
        track_id=source_diff.after.target.track_id,
        event_type=event_type,
        observed_at=T2,
        source=SOURCE,
        source_diff=source_diff,
        source_change_fields=fields,
    )


@pytest.mark.parametrize(
    "kind,change,category",
    [
        ("registration_window_changed", endpoint(), "fact_change"),
        (
            "competition_window_changed",
            endpoint("competition_window.end_at"),
            "fact_change",
        ),
        (
            "track_membership_changed",
            TrackMembershipChange(
                field="track_membership",
                kind="value_changed",
                before=ObservedTrackMembership(
                    state="known_value", value=("a",), sources=(SOURCE,)
                ),
                after=ObservedTrackMembership(
                    state="known_value", value=("a", "b"), sources=(SOURCE,)
                ),
            ),
            "fact_change",
        ),
        ("observation_coverage_changed", endpoint(unknown=True), "observation_change"),
    ],
)
def test_supported_typed_events_and_stable_json(kind, change, category):
    event = CompetitionEvent(**payload(kind, diff(change)))
    assert event.target == TARGET
    assert event.category == CompetitionEventCategory(category)
    assert event.source_changes == (change,)
    assert event.source == SOURCE and event.source_diff.before.snapshot_id == "before"
    assert event.occurred_at is None and event.description is None
    assert CompetitionEvent.model_validate_json(event.model_dump_json()) == event
    assert CompetitionEvent.model_validate(event.model_dump(mode="json")) == event
    assert (
        event.model_dump_json()
        == CompetitionEvent(**payload(kind, diff(change))).model_dump_json()
    )


def test_multiple_changes_canonical_selection_order_and_identity():
    start, end = endpoint("registration_window.start_at"), endpoint()
    one = CompetitionEvent(**payload(source_diff=diff(end, start)))
    two = CompetitionEvent(**payload(source_diff=diff(start, end)))
    assert one.source_change_fields == (start.field, end.field)
    assert one.source_changes == (start, end)
    assert one.id == two.id and one.model_dump_json() == two.model_dump_json()
    # One event may select only part of a Diff, without copying/merging values.
    subset = CompetitionEvent(
        **payload(source_diff=diff(start, end), fields=(end.field,))
    )
    assert subset.source_changes == (end,) and subset.id != one.id


def test_fact_presence_transition_is_supported_without_business_effective_time():
    change = TimeWindowChange(
        field="registration_window",
        kind="presence_changed",
        before=ObservedTimeWindow(
            state="known_value", value=TimeWindow(end_at=T1), sources=(SOURCE,)
        ),
        after=ObservedTimeWindow(state="known_absent", sources=(SOURCE,)),
    )
    event = CompetitionEvent(**payload(source_diff=diff(change)))
    assert event.category == CompetitionEventCategory.FACT_CHANGE
    assert event.source_changes[0].after.state.value == "known_absent"


@pytest.mark.parametrize(
    "before,after",
    [
        ("unknown", "known_value"),
        ("known_value", "unknown"),
        ("unknown", "known_absent"),
        ("known_absent", "unknown"),
    ],
)
def test_whole_field_coverage_states_remain_observation_events(before, after):
    def fact(state):
        return ObservedTimeWindow(
            state=state,
            value=TimeWindow(end_at=T1) if state == "known_value" else None,
            sources=() if state == "unknown" else (SOURCE,),
        )

    change = TimeWindowChange(
        field="competition_window",
        kind="observation_state_changed",
        before=fact(before),
        after=fact(after),
    )
    event = CompetitionEvent(**payload("observation_coverage_changed", diff(change)))
    assert event.category == CompetitionEventCategory.OBSERVATION_CHANGE


@pytest.mark.parametrize(
    "updates",
    [
        {"competition_id": "other"},
        {"edition_id": "other"},
        {"track_id": "other"},
        {"competition_id": " "},
        {"edition_id": " "},
        {"source_diff": None},
        {"source_change_fields": ()},
        {
            "source_change_fields": (
                "registration_window.end_at",
                "registration_window.end_at",
            )
        },
        {"source_change_fields": ("competition_window.end_at",)},
        {"id": "random-id"},
        {"observed_at": T1},
        {"observed_at": T2.replace(tzinfo=None)},
        {"occurred_at": T2},
        {"category": "fact_change"},
    ],
)
def test_invalid_target_lineage_identity_and_time_rejected(updates):
    with pytest.raises(ValidationError):
        CompetitionEvent(**{**payload(), **updates})


def test_required_identity_and_detection_time_have_no_defaults():
    for field in ("id", "observed_at", "competition_id", "edition_id"):
        values = payload()
        del values[field]
        with pytest.raises(ValidationError):
            CompetitionEvent(**values)


@pytest.mark.parametrize(
    "kind,change",
    [
        ("registration_window_changed", endpoint(unknown=True)),
        ("observation_coverage_changed", endpoint()),
        ("competition_window_changed", endpoint()),
        ("track_membership_changed", endpoint()),
    ],
)
def test_event_type_cannot_misclassify_field_or_knowledge(kind, change):
    with pytest.raises(ValidationError):
        CompetitionEvent(**payload(kind, diff(change)))


def test_mixed_fact_and_coverage_cannot_be_one_supplied_event():
    changes = diff(endpoint(), endpoint("registration_window.start_at", unknown=True))
    with pytest.raises(ValidationError):
        CompetitionEvent(**payload(source_diff=changes))


def test_zero_diff_and_fabricated_provenance_are_rejected():
    with pytest.raises(ValueError):
        competition_event_identity("registration_window_changed", diff(), ())
    fabricated = SourceMetadata(
        source_url="https://example.invalid/not-in-lineage",
        source_type="manual",
        observed_at=T1,
        verification_status="verified",
    )
    with pytest.raises(ValidationError):
        CompetitionEvent(**{**payload(), "source": fabricated})


def test_no_impact_workflow_student_or_future_type_extension():
    for field in (
        "severity",
        "impact",
        "affected_plan_ids",
        "student_id",
        "status",
        "replan_required",
    ):
        with pytest.raises(ValidationError):
            CompetitionEvent(**{**payload(), field: "unsupported"})
    with pytest.raises(ValueError):
        CompetitionEventType("eligibility_rule_changed")


def test_identity_excludes_display_detection_time_and_normalizes_aware_instants():
    event = CompetitionEvent(**payload())
    later = CompetitionEvent(
        **{
            **payload(),
            "observed_at": T2 + timedelta(hours=1),
            "description": "Display only",
        }
    )
    assert event.id == later.id
    localized = event.source_diff.model_dump(mode="python")
    localized["after"]["observed_at"] = T2.astimezone(timezone(timedelta(hours=8)))
    assert (
        competition_event_identity(
            event.event_type, SnapshotDiff(**localized), event.source_change_fields
        )
        == event.id
    )
    assert (
        competition_event_identity(
            "observation_coverage_changed",
            diff(endpoint(unknown=True)),
            (endpoint().field,),
        )
        != event.id
    )


def test_frozen_event_nested_contracts_and_no_copy_update_bypass():
    event = CompetitionEvent(**payload())
    for model, field, value in (
        (event, "id", "other"),
        (event.target, "competition_id", "other"),
        (event.source_diff, "changes", ()),
        (event.source_changes[0], "kind", "presence_changed"),
        (event.source, "verification_status", "pending"),
    ):
        with pytest.raises(ValidationError):
            setattr(model, field, value)
    with pytest.raises(AttributeError):
        event.source_change_fields.append("other")
    with pytest.raises(TypeError):
        event.model_copy(update={"id": "other"})


def test_track_target_is_reused_without_repository_lookup():
    target = CompetitionTarget(
        competition_id="competition", edition_id="edition", track_id="track"
    )
    event = CompetitionEvent(**payload(source_diff=diff(endpoint(), target=target)))
    assert event.target == target


def test_event_identity_binds_directed_snapshot_references():
    original = diff(endpoint())
    changed = SnapshotDiff(
        before=original.before,
        after=SnapshotReference(snapshot_id="different-after", target=TARGET, observed_at=T2),
        changes=original.changes,
    )
    one = CompetitionEvent(**payload(source_diff=original))
    two = CompetitionEvent(**payload(source_diff=changed))
    assert one.id != two.id
    with pytest.raises(ValidationError, match="canonical P10 identity"):
        CompetitionEvent(**{**payload(source_diff=changed), "id": one.id})
