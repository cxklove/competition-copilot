"""Stateless batch normalization of supplied P10 Events; no remapping or storage."""

from datetime import datetime, timezone
from typing import Any

from competition_copilot.domain.event import (
    P10_EVENT_TYPES,
    CompetitionEvent,
    CompetitionEventCategory,
    competition_event_identity,
)

_FIELDS = (
    "registration_window",
    "registration_window.start_at",
    "registration_window.end_at",
    "competition_window",
    "competition_window.start_at",
    "competition_window.end_at",
    "track_membership",
)
_FAMILIES = ("registration_window", "competition_window", "track_membership")
_FIELD_FAMILY = {
    "registration_window": "registration_window",
    "registration_window.start_at": "registration_window",
    "registration_window.end_at": "registration_window",
    "competition_window": "competition_window",
    "competition_window.start_at": "competition_window",
    "competition_window.end_at": "competition_window",
    "track_membership": "track_membership",
}


def _utc(value: Any) -> Any:
    """Normalize representations of already validated aware instants, not facts."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, dict):
        return {key: _utc(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_utc(item) for item in value)
    return value


def _scope(event: CompetitionEvent) -> str:
    family = _FIELD_FAMILY[event.source_change_fields[0]]
    if any(_FIELD_FAMILY[field] != family for field in event.source_change_fields):
        raise ValueError("Each input Event must have one canonical field family")
    return family


def _key(event: CompetitionEvent, family: str) -> tuple[str, ...]:
    target = event.target
    return (
        target.competition_id,
        target.edition_id,
        target.track_id or "",
        event.source_diff.model_dump_json(),
        event.event_type.value,
        family,
    )


def _output_order(event: CompetitionEvent) -> tuple:
    diff, target = event.source_diff, event.target
    return (
        target.competition_id,
        target.edition_id,
        target.track_id or "",
        diff.before.observed_at,
        diff.after.observed_at,
        diff.before.snapshot_id,
        diff.after.snapshot_id,
        diff.model_dump_json(),
        _FAMILIES.index(_scope(event)),
        0 if event.category == CompetitionEventCategory.FACT_CHANGE else 1,
        event.event_type.value,
    )


class CompetitionEventAggregator:
    """Group by target/full Diff/type/field family, dedup only this supplied batch.

    Accepts primitive Events and already canonical single-family P10 Events.
    Same-ID content conflicts and incompatible group detection times are rejected.
    Required detection time is preserved, never chosen by earliest/latest policy.
    """

    def normalize(
        self, events: tuple[CompetitionEvent, ...]
    ) -> tuple[CompetitionEvent, ...]:
        if not isinstance(events, tuple):
            raise TypeError("normalize requires an immutable Event tuple")
        seen: dict[str, CompetitionEvent] = {}
        groups: dict[tuple[str, ...], list[CompetitionEvent]] = {}
        for event in events:
            if not isinstance(event, CompetitionEvent):
                raise TypeError("normalize requires validated CompetitionEvent objects")
            event = CompetitionEvent.model_validate(event)
            if event.event_type not in P10_EVENT_TYPES or event.source_diff is None:
                raise ValueError("Aggregation requires P10 Diff-backed Events")
            event = CompetitionEvent.model_validate(_utc(event.model_dump()))
            if event.id in seen:
                if event != seen[event.id]:
                    raise ValueError("Same Event ID cannot identify different content")
                continue
            seen[event.id] = event
            family = _scope(event)
            groups.setdefault(_key(event, family), []).append(event)

        result = []
        for group in groups.values():
            reference = group[0]
            if any(
                event.observed_at != reference.observed_at
                or event.occurred_at != reference.occurred_at
                for event in group
            ):
                raise ValueError("Aggregation group has conflicting detection time")
            # Stable lineage chooses the representative display/source metadata;
            # full typed evidence from every selected field remains in the Diff.
            representative = min(
                group,
                key=lambda event: tuple(
                    _FIELDS.index(field) for field in event.source_change_fields
                ),
            )
            selected = {
                field for event in group for field in event.source_change_fields
            }
            fields = tuple(field for field in _FIELDS if field in selected)
            result.append(
                CompetitionEvent(
                    id=competition_event_identity(
                        representative.event_type, representative.source_diff, fields
                    ),
                    competition_id=representative.competition_id,
                    edition_id=representative.edition_id,
                    track_id=representative.track_id,
                    event_type=representative.event_type,
                    observed_at=representative.observed_at,
                    source=representative.source,
                    description=representative.description,
                    source_diff=representative.source_diff,
                    source_change_fields=fields,
                )
            )
        canonical_ids: dict[str, CompetitionEvent] = {}
        for event in result:
            if event.id in canonical_ids and event != canonical_ids[event.id]:
                raise ValueError("Canonical Event ID conflicts across aggregation groups")
            canonical_ids[event.id] = event
        return tuple(sorted(canonical_ids.values(), key=_output_order))
