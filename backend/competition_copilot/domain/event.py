from collections.abc import Mapping
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from json import dumps
from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    field_validator,
    model_serializer,
    model_validator,
)

from competition_copilot.domain.digital_twin import (
    CompetitionTarget,
    FactChangeKind,
    SnapshotChange,
    SnapshotDiff,
    StableId,
)
from competition_copilot.domain.source_metadata import SourceMetadata


class CompetitionEventType(str, Enum):
    # P1 types remain deserializable; P10 does not generate these legacy types.
    REGISTRATION_OPENED = "registration_opened"
    REGISTRATION_CLOSED = "registration_closed"
    DEADLINE_CHANGED = "deadline_changed"
    MATERIAL_UPDATED = "material_updated"
    RULE_UPDATED = "rule_updated"
    TRACK_UPDATED = "track_updated"
    RESULT_PUBLISHED = "result_published"
    OTHER = "other"
    REGISTRATION_WINDOW_CHANGED = "registration_window_changed"
    COMPETITION_WINDOW_CHANGED = "competition_window_changed"
    TRACK_MEMBERSHIP_CHANGED = "track_membership_changed"
    OBSERVATION_COVERAGE_CHANGED = "observation_coverage_changed"


class CompetitionEventCategory(str, Enum):
    FACT_CHANGE = "fact_change"
    OBSERVATION_CHANGE = "observation_change"


P10_EVENT_TYPES = frozenset(
    (
        CompetitionEventType.REGISTRATION_WINDOW_CHANGED,
        CompetitionEventType.COMPETITION_WINDOW_CHANGED,
        CompetitionEventType.TRACK_MEMBERSHIP_CHANGED,
        CompetitionEventType.OBSERVATION_COVERAGE_CHANGED,
    )
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


def _selected_changes(
    diff: SnapshotDiff, fields: tuple[str, ...]
) -> tuple[SnapshotChange, ...]:
    if not fields or len(set(fields)) != len(fields):
        raise ValueError("Source change fields must be nonempty and unique")
    by_field = {change.field: change for change in diff.changes}
    if any(field not in by_field for field in fields):
        raise ValueError("Source change fields must exist in the supplied Diff")
    return tuple(by_field[field] for field in _FIELDS if field in fields)


def _canonical(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    # Pydantic URL primitives serialize as machine URLs, never display text.
    return (
        value if isinstance(value, (str, int, float, bool, type(None))) else str(value)
    )


def competition_event_identity(
    event_type: CompetitionEventType,
    source_diff: SnapshotDiff,
    source_change_fields: tuple[str, ...],
) -> str:
    """Contract identity only; does not classify, aggregate or create events.

    P9 has no diff_id/change_id. Directed references + selected typed changes
    provide deterministic lineage. Detection/display text is excluded.
    """
    event_type = CompetitionEventType(event_type)
    if event_type not in P10_EVENT_TYPES:
        raise ValueError("Deterministic P10 identity requires a P10 event type")
    diff = SnapshotDiff.model_validate(source_diff)
    selected = _selected_changes(diff, source_change_fields)
    payload = {
        "event_type": event_type,
        "before": diff.before.model_dump(),
        "after": diff.after.model_dump(),
        "changes": tuple(change.model_dump() for change in selected),
    }
    encoded = dumps(
        _canonical(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return f"competition-event-v1:{sha256(encoded.encode('utf-8')).hexdigest()}"


class CompetitionEvent(BaseModel):
    """P1 recorded events and P10 Diff-backed business/coverage interpretations.

    P10 observed_at is explicit detection time, not business effective time.
    occurred_at is retained only for legacy records. Description is display-only.
    No impact, student, notification or workflow semantics.
    """

    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always"
    )

    id: str
    competition_id: str
    edition_id: str
    event_type: CompetitionEventType
    occurred_at: datetime | None = None
    observed_at: datetime
    source: SourceMetadata
    description: str | None = None
    track_id: StableId | None = None
    source_diff: SnapshotDiff | None = None
    source_change_fields: tuple[StableId, ...] = ()

    @property
    def target(self) -> CompetitionTarget:
        return CompetitionTarget(
            competition_id=self.competition_id,
            edition_id=self.edition_id,
            track_id=self.track_id,
        )

    @property
    def category(self) -> CompetitionEventCategory | None:
        if self.event_type not in P10_EVENT_TYPES:
            return None  # Do not reinterpret historical P1 categories.
        return (
            CompetitionEventCategory.OBSERVATION_CHANGE
            if self.event_type == CompetitionEventType.OBSERVATION_COVERAGE_CHANGED
            else CompetitionEventCategory.FACT_CHANGE
        )

    @property
    def source_changes(self) -> tuple[SnapshotChange, ...]:
        return (
            ()
            if self.source_diff is None
            else _selected_changes(self.source_diff, self.source_change_fields)
        )

    @model_validator(mode="before")
    @classmethod
    def detach_event(cls, value: Any) -> Any:
        return value.model_dump() if isinstance(value, BaseModel) else value

    @field_validator("source_change_fields")
    @classmethod
    def canonical_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(
            field not in _FIELDS for field in value
        ):
            raise ValueError("Source change fields must be unique canonical paths")
        return tuple(field for field in _FIELDS if field in value)

    @field_validator("source_diff", mode="before")
    @classmethod
    def canonical_diff(cls, value: Any) -> SnapshotDiff | None:
        if value is None:
            return None
        diff = SnapshotDiff.model_validate(value)
        return SnapshotDiff(
            before=diff.before,
            after=diff.after,
            changes=tuple(
                sorted(diff.changes, key=lambda change: _FIELDS.index(change.field))
            ),
        )

    @model_validator(mode="after")
    def validate_lineage(self) -> Self:
        if self.event_type not in P10_EVENT_TYPES:
            if self.source_diff is not None or self.source_change_fields:
                raise ValueError("Legacy event types cannot claim P10 Diff lineage")
            return self
        if self.source_diff is None:
            raise ValueError("P10 event requires source Diff lineage")
        if self.target != self.source_diff.after.target:
            raise ValueError("Event target must match source Diff target")
        if self.observed_at < self.source_diff.after.observed_at:
            raise ValueError("Detection time cannot precede current observation")
        if self.occurred_at is not None:
            raise ValueError("P10 Diff does not establish a business occurred_at")
        selected = self.source_changes
        expected_prefix = {
            CompetitionEventType.REGISTRATION_WINDOW_CHANGED: "registration_window",
            CompetitionEventType.COMPETITION_WINDOW_CHANGED: "competition_window",
            CompetitionEventType.TRACK_MEMBERSHIP_CHANGED: "track_membership",
        }.get(self.event_type)
        for change in selected:
            observation = change.kind == FactChangeKind.OBSERVATION_STATE_CHANGED
            if observation != (
                self.category == CompetitionEventCategory.OBSERVATION_CHANGE
            ):
                raise ValueError("Event type and source change category conflict")
            if expected_prefix is not None and (
                change.field != expected_prefix
                and not change.field.startswith(expected_prefix + ".")
            ):
                raise ValueError("Event type and source field conflict")
            for fact in (change.before, change.after):
                if any(
                    source.observed_at > self.source_diff.after.observed_at
                    for source in fact.sources
                ):
                    raise ValueError(
                        "Lineage provenance cannot follow current observation"
                    )
        if not any(
            self.source == source
            for change in selected
            for fact in (change.before, change.after)
            for source in fact.sources
        ):
            raise ValueError(
                "Event source must be reused from selected change provenance"
            )
        if self.id != competition_event_identity(
            self.event_type, self.source_diff, self.source_change_fields
        ):
            raise ValueError("Event ID must match canonical P10 identity")
        return self

    @model_serializer(mode="wrap")
    def preserve_legacy_shape(self, handler):
        payload = handler(self)
        if self.event_type not in P10_EVENT_TYPES:
            for field in ("source_diff", "source_change_fields"):
                payload.pop(field, None)
            if self.track_id is None:
                payload.pop("track_id", None)
        return payload

    def model_copy(
        self, *, update: Mapping[str, Any] | None = None, deep: bool = False
    ) -> Self:
        if update is not None:
            raise TypeError("Construct a new validated event instead")
        return super().model_copy(deep=deep)

    @field_validator("id", "competition_id", "edition_id", "description")
    @classmethod
    def strip_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("occurred_at", "observed_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("datetime must be timezone-aware")
        return value
