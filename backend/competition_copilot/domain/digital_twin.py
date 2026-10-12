"""Typed observation and directed comparison contracts; no capture/diff engine."""

from collections.abc import Mapping
from enum import Enum
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    VerificationStatus,
)
from competition_copilot.domain.temporal import TimeWindow

StableId = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)
]


class _TwinContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always"
    )

    @model_validator(mode="before")
    @classmethod
    def detach_input(cls, value: Any) -> Any:
        return value.model_dump() if isinstance(value, BaseModel) else value

    def model_copy(
        self, *, update: Mapping[str, Any] | None = None, deep: bool = False
    ) -> Self:
        if update is not None:
            raise TypeError("Construct a new validated digital twin contract instead")
        return super().model_copy(deep=deep)


class CompetitionTarget(_TwinContract):
    """Generic machine identity, not a planning or requirement target.

    Repository existence and parent relationships are validated by P9.2, since
    this contract contains IDs rather than Competition/Edition/Track objects.
    """

    competition_id: StableId
    edition_id: StableId
    track_id: StableId | None = None


class ObservationState(str, Enum):
    KNOWN_VALUE = "known_value"
    KNOWN_ABSENT = "known_absent"
    UNKNOWN = "unknown"


class _ObservedFact(_TwinContract):
    """Known facts require verified provenance; silence/null is UNKNOWN.

    KNOWN_ABSENT means an explicitly sourced absence, not an unobserved value.
    UNKNOWN may retain sources describing an incomplete observation attempt.
    Each field carries its own sources; there is no assumed common source.
    """

    state: ObservationState
    sources: tuple[SourceMetadata, ...] = ()

    @field_validator("sources", mode="before")
    @classmethod
    def detach_sources(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            return tuple(
                source.model_dump() if isinstance(source, BaseModel) else source
                for source in value
            )
        return value

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if (self.state == ObservationState.KNOWN_VALUE) != (self.value is not None):
            raise ValueError("Only KNOWN_VALUE must carry a value")
        if self.state != ObservationState.UNKNOWN and (
            not self.sources
            or any(
                s.verification_status != VerificationStatus.VERIFIED
                for s in self.sources
            )
        ):
            raise ValueError("Known facts require verified source metadata")
        return self


class ObservedTimeWindow(_ObservedFact):
    """A known window may have partial (or unknown) endpoints per TimeWindow.

    Whole-field UNKNOWN says the window itself was not reliably observed.
    Missing endpoints do not assert that those endpoints are absent.
    """

    value: TimeWindow | None = None

    @field_validator("value", mode="before")
    @classmethod
    def detach_window(cls, value: Any) -> Any:
        return value.model_dump() if isinstance(value, BaseModel) else value


class ObservedInstant(_ObservedFact):
    """One window endpoint; an omitted endpoint in a partial window is UNKNOWN."""

    value: AwareDatetime | None = None


class ObservedTrackMembership(_ObservedFact):
    """Complete edition track ID set, including a known empty set.

    An incomplete/unobserved set is UNKNOWN, not KNOWN_VALUE(()).
    KNOWN_ABSENT asserts absence of the membership fact itself, not zero tracks.
    """

    value: tuple[StableId, ...] | None = None

    @field_validator("value")
    @classmethod
    def canonical_membership(
        cls, value: tuple[str, ...] | None
    ) -> tuple[str, ...] | None:
        if value is None:
            return None
        if len(set(value)) != len(value):
            raise ValueError("Duplicate track IDs")
        return tuple(sorted(value))


class CompetitionDynamicState(_TwinContract):
    """Observed edition windows and edition-wide membership, even for track targets."""

    registration_window: ObservedTimeWindow
    competition_window: ObservedTimeWindow
    track_membership: ObservedTrackMembership


class CompetitionSnapshot(_TwinContract):
    """One explicit observation; identity is supplied, never random or clock based.

    P9.2 will generate IDs from canonical machine data including observation time.
    Different observations can have equal dynamic values and different IDs.
    Source observation times describe provenance; observed_at describes capture.
    """

    snapshot_id: StableId
    target: CompetitionTarget
    observed_at: AwareDatetime
    dynamic_state: CompetitionDynamicState

    @model_validator(mode="after")
    def source_observation_order(self) -> Self:
        for fact in (
            self.dynamic_state.registration_window,
            self.dynamic_state.competition_window,
            self.dynamic_state.track_membership,
        ):
            if any(source.observed_at > self.observed_at for source in fact.sources):
                raise ValueError(
                    "Source observation cannot be later than snapshot observation"
                )
        return self


class SnapshotReference(_TwinContract):
    """Small audit reference, not a duplicate complete snapshot."""

    snapshot_id: StableId
    target: CompetitionTarget
    observed_at: AwareDatetime


class FactChangeKind(str, Enum):
    VALUE_CHANGED = "value_changed"
    PRESENCE_CHANGED = "presence_changed"
    OBSERVATION_STATE_CHANGED = "observation_state_changed"


class _FactChange(_TwinContract):
    """Validate supplied low-level change classification; do not compute a diff."""

    kind: FactChangeKind

    @model_validator(mode="after")
    def validate_kind(self) -> Self:
        before, after = self.before, self.after
        if self.kind == FactChangeKind.VALUE_CHANGED:
            if (
                before.state != ObservationState.KNOWN_VALUE
                or after.state != ObservationState.KNOWN_VALUE
                or before.value == after.value
            ):
                raise ValueError("VALUE_CHANGED requires different known values")
        elif self.kind == FactChangeKind.PRESENCE_CHANGED:
            if {before.state, after.state} != {
                ObservationState.KNOWN_VALUE,
                ObservationState.KNOWN_ABSENT,
            }:
                raise ValueError("PRESENCE_CHANGED requires known value/known absence")
        elif before.state == after.state or ObservationState.UNKNOWN not in (
            before.state,
            after.state,
        ):
            raise ValueError(
                "Observation change requires a transition involving UNKNOWN"
            )
        return self


class TimeWindowChange(_FactChange):
    """Whole-window observation or presence change, never an endpoint change."""

    field: Literal["registration_window", "competition_window"]
    before: ObservedTimeWindow
    after: ObservedTimeWindow

    @model_validator(mode="after")
    def exclude_endpoint_value_change(self) -> Self:
        if self.kind == FactChangeKind.VALUE_CHANGED:
            raise ValueError("Use WindowEndpointChange for known endpoint changes")
        return self


class WindowEndpointChange(_FactChange):
    """Typed start/end change; unknown endpoint -> known is observation change."""

    field: Literal[
        "registration_window.start_at",
        "registration_window.end_at",
        "competition_window.start_at",
        "competition_window.end_at",
    ]
    before: ObservedInstant
    after: ObservedInstant


class TrackMembershipChange(_FactChange):
    """Known set-to-set changes expose IDs safely; UNKNOWN never asserts removal.

    Added/removed member computation belongs to P9.3, not this contract.
    """

    field: Literal["track_membership"]
    before: ObservedTrackMembership
    after: ObservedTrackMembership


SnapshotChange = Annotated[
    TimeWindowChange | WindowEndpointChange | TrackMembershipChange,
    Field(discriminator="field"),
]


class SnapshotDiff(_TwinContract):
    """Directed low-level changes only. Not an Event or impact assessment.

    Changes are supplied, not inferred. P9.3 verifies them against the referenced
    snapshots. Empty changes are legal for observations of unchanged state.
    """

    before: SnapshotReference
    after: SnapshotReference
    changes: tuple[SnapshotChange, ...] = ()

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        if self.before.target != self.after.target:
            raise ValueError("Snapshot diff requires the same target")
        if self.before.snapshot_id == self.after.snapshot_id:
            raise ValueError("Diff requires distinct observation snapshot references")
        if self.before.observed_at > self.after.observed_at:
            raise ValueError("Before observation must not follow after observation")
        fields = tuple(change.field for change in self.changes)
        if len(set(fields)) != len(fields):
            raise ValueError("Duplicate changed fields")
        if any(
            window in fields and any(field.startswith(f"{window}.") for field in fields)
            for window in ("registration_window", "competition_window")
        ):
            raise ValueError("Whole-window and endpoint changes cannot overlap")
        return self
