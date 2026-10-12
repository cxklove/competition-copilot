"""Immutable one-shot monitoring contracts; no observation or orchestration runtime."""

from collections.abc import Mapping
from enum import Enum
from typing import Annotated, Any, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StringConstraints,
    field_validator,
    model_validator,
)

from competition_copilot.domain.digital_twin import (
    CompetitionDynamicState,
    CompetitionSnapshot,
    CompetitionTarget,
    SnapshotDiff,
    SnapshotReference,
)
from competition_copilot.domain.source_metadata import SourceMetadata


class _MonitorContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always"
    )

    @model_validator(mode="before")
    @classmethod
    def detach_input(cls, value: Any) -> Any:
        return value.model_dump() if isinstance(value, BaseModel) else value

    @field_validator("source", mode="before", check_fields=False)
    @classmethod
    def detach_source(cls, value: Any) -> Any:
        return value.model_dump() if isinstance(value, BaseModel) else value

    def model_copy(
        self, *, update: Mapping[str, Any] | None = None, deep: bool = False
    ) -> Self:
        if update is not None:
            raise TypeError("Construct a new validated monitor contract instead")
        return super().model_copy(deep=deep)


class MonitorCheckOutcome(str, Enum):
    CHECK_SUCCEEDED = "check_succeeded"
    CHECK_FAILED = "check_failed"


class SourceCheckErrorCode(str, Enum):
    SOURCE_UNAVAILABLE = "source_unavailable"
    FETCH_FAILED = "fetch_failed"
    PARSE_FAILED = "parse_failed"
    INVALID_OBSERVATION = "invalid_observation"


class SourceCheckError(_MonitorContract):
    """Expected external-source failure; not a Competition fact or impact."""

    code: SourceCheckErrorCode
    message: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)
    ]


class MonitorCheckRequest(_MonitorContract):
    """Explicit observation time and source policy for one check.

    source describes the configured source and existing verification status;
    a check is not an approval/verification action. No start/end or schedule policy.
    previous_snapshot=None supports an initial observation without a Diff.
    """

    target: CompetitionTarget
    observed_at: AwareDatetime
    source: SourceMetadata
    previous_snapshot: CompetitionSnapshot | None = None

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        if self.source.observed_at > self.observed_at:
            raise ValueError("Configured source observation cannot follow check time")
        if self.previous_snapshot is not None:
            if self.previous_snapshot.target != self.target:
                raise ValueError("Baseline target must match request target")
            if self.previous_snapshot.observed_at > self.observed_at:
                raise ValueError("Baseline observation cannot follow check time")
        return self


class SourceObservationResult(_MonitorContract):
    """One source check, distinct from the certainty of individual facts.

    Success requires typed state (which may be wholly UNKNOWN); failure forbids
    state and requires an error. No Snapshot is fabricated on source failure.
    This single-source result binds fact provenance to its declared source.
    KNOWN_ABSENT is an explicit sourced assertion, never inferred from missing data.
    """

    target: CompetitionTarget
    observed_at: AwareDatetime
    source: SourceMetadata
    outcome: MonitorCheckOutcome
    dynamic_state: CompetitionDynamicState | None = None
    error: SourceCheckError | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.source.observed_at > self.observed_at:
            raise ValueError("Source observation cannot follow check time")
        if self.outcome == MonitorCheckOutcome.CHECK_FAILED:
            if self.error is None or self.dynamic_state is not None:
                raise ValueError("Failed check requires an error and no observed state")
            return self
        if self.error is not None or self.dynamic_state is None:
            raise ValueError("Successful check requires typed state and no error")
        for fact in (
            self.dynamic_state.registration_window,
            self.dynamic_state.competition_window,
            self.dynamic_state.track_membership,
        ):
            for provenance in fact.sources:
                if (
                    provenance.source_url != self.source.source_url
                    or provenance.source_type != self.source.source_type
                    or provenance.verification_status != self.source.verification_status
                ):
                    raise ValueError(
                        "Fact provenance must match the declared source policy"
                    )
                if provenance.observed_at > self.observed_at:
                    raise ValueError("Fact source observation cannot follow check time")
        return self


class MonitorCheckResult(_MonitorContract):
    """Supplied one-shot result; validates binding, does not build or compare snapshots.

    Outcome/error/target/time are available through observation/request without
    duplicate status fields. Success with zero changes is a successful check.
    Expected source failure carries neither a new Snapshot nor a Diff.
    """

    request: MonitorCheckRequest
    observation: SourceObservationResult
    snapshot: CompetitionSnapshot | None = None
    diff: SnapshotDiff | None = None

    @property
    def outcome(self) -> MonitorCheckOutcome:
        return self.observation.outcome

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        request, observation = self.request, self.observation
        if (
            observation.target != request.target
            or observation.observed_at != request.observed_at
        ):
            raise ValueError("Observation target/time must match check request")
        if (
            observation.source.source_url != request.source.source_url
            or observation.source.source_type != request.source.source_type
            or observation.source.verification_status
            != request.source.verification_status
        ):
            raise ValueError(
                "A check cannot rebind or upgrade source verification policy"
            )
        if observation.outcome == MonitorCheckOutcome.CHECK_FAILED:
            if self.snapshot is not None or self.diff is not None:
                raise ValueError("Failed check cannot carry a Snapshot or Diff")
            return self
        if self.snapshot is None:
            raise ValueError("Successful monitor result requires a Snapshot")
        if (
            self.snapshot.target != observation.target
            or self.snapshot.observed_at != observation.observed_at
            or self.snapshot.dynamic_state != observation.dynamic_state
        ):
            raise ValueError(
                "Snapshot must preserve the successful structured observation"
            )
        baseline = request.previous_snapshot
        if baseline is None:
            if self.diff is not None:
                raise ValueError("An initial check has no baseline Diff")
        else:
            if (
                baseline.snapshot_id == self.snapshot.snapshot_id
                and baseline != self.snapshot
            ):
                raise ValueError(
                    "Same snapshot ID cannot identify different snapshot content"
                )
            if self.diff is None:
                raise ValueError("Successful check with a baseline requires a Diff")
            expected_before = SnapshotReference(
                snapshot_id=baseline.snapshot_id,
                target=baseline.target,
                observed_at=baseline.observed_at,
            )
            expected_after = SnapshotReference(
                snapshot_id=self.snapshot.snapshot_id,
                target=self.snapshot.target,
                observed_at=self.snapshot.observed_at,
            )
            if self.diff.before != expected_before or self.diff.after != expected_after:
                raise ValueError(
                    "Diff references must match baseline and current Snapshot"
                )
        return self
