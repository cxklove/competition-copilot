"""Pure one-change/one-event interpretation of the frozen P9 Diff contract."""

from datetime import datetime

from pydantic import AwareDatetime, TypeAdapter

from competition_copilot.domain.digital_twin import FactChangeKind, SnapshotDiff
from competition_copilot.domain.event import (
    CompetitionEvent,
    CompetitionEventType,
    competition_event_identity,
)

_FIELD_ORDER = (
    "registration_window",
    "registration_window.start_at",
    "registration_window.end_at",
    "competition_window",
    "competition_window.start_at",
    "competition_window.end_at",
    "track_membership",
)
_FACT_TYPES = {
    "registration_window": CompetitionEventType.REGISTRATION_WINDOW_CHANGED,
    "registration_window.start_at": CompetitionEventType.REGISTRATION_WINDOW_CHANGED,
    "registration_window.end_at": CompetitionEventType.REGISTRATION_WINDOW_CHANGED,
    "competition_window": CompetitionEventType.COMPETITION_WINDOW_CHANGED,
    "competition_window.start_at": CompetitionEventType.COMPETITION_WINDOW_CHANGED,
    "competition_window.end_at": CompetitionEventType.COMPETITION_WINDOW_CHANGED,
    "track_membership": CompetitionEventType.TRACK_MEMBERSHIP_CHANGED,
}


class CompetitionEventEngine:
    """Map supplied changes independently; no aggregation or cross-call state.

    detected_at is explicit aware detection time, never business occurred_at.
    Event.source is the first after source, falling back to the first before
    source for observation loss. Full evidence remains in the embedded Diff.
    """

    def interpret(
        self, source_diff: SnapshotDiff, *, detected_at: datetime
    ) -> tuple[CompetitionEvent, ...]:
        if not isinstance(source_diff, SnapshotDiff):
            raise TypeError("interpret requires SnapshotDiff")
        source_diff = SnapshotDiff.model_validate(source_diff)
        if not isinstance(detected_at, datetime):
            raise TypeError("detected_at must be an aware datetime")
        detected_at = TypeAdapter(AwareDatetime).validate_python(detected_at)
        if detected_at < source_diff.after.observed_at:
            raise ValueError("Detection time cannot precede current observation")

        for change in source_diff.changes:
            if change.field not in _FACT_TYPES:
                raise ValueError("Unsupported canonical Diff field")
            if change.kind not in (
                FactChangeKind.VALUE_CHANGED,
                FactChangeKind.PRESENCE_CHANGED,
                FactChangeKind.OBSERVATION_STATE_CHANGED,
            ):
                raise ValueError("Unsupported Diff change kind")

        events = []
        target = source_diff.after.target
        for change in sorted(
            source_diff.changes, key=lambda item: _FIELD_ORDER.index(item.field)
        ):
            event_type = (
                CompetitionEventType.OBSERVATION_COVERAGE_CHANGED
                if change.kind == FactChangeKind.OBSERVATION_STATE_CHANGED
                else _FACT_TYPES[change.field]
            )
            sources = change.after.sources or change.before.sources
            if not sources:
                raise ValueError("Source change must carry auditable provenance")
            fields = (change.field,)
            events.append(
                CompetitionEvent(
                    id=competition_event_identity(event_type, source_diff, fields),
                    competition_id=target.competition_id,
                    edition_id=target.edition_id,
                    track_id=target.track_id,
                    event_type=event_type,
                    observed_at=detected_at,
                    source=sources[0],
                    source_diff=source_diff,
                    source_change_fields=fields,
                )
            )
        return tuple(events)
