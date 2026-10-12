"""One-shot source/Snapshot/Diff composition, independent of transport and storage."""

from competition_copilot.application.competition_snapshots import _snapshot_id
from competition_copilot.application.monitoring import CompetitionObservationSource
from competition_copilot.domain.digital_twin import CompetitionSnapshot
from competition_copilot.domain.monitoring import (
    MonitorCheckOutcome,
    MonitorCheckRequest,
    MonitorCheckResult,
    SourceObservationResult,
)
from competition_copilot.domain.snapshot_diff_engine import SnapshotDiffEngine


class OneShotCompetitionMonitor:
    """Observe once; failures create neither Snapshot nor Diff.

    P9.2's pure ID helper preserves the frozen canonical identity algorithm.
    Its Repository builder is not invoked for external observations. Contract
    errors propagate; expected external failures are supplied typed results.
    """

    def __init__(
        self,
        source: CompetitionObservationSource,
        diff_engine: SnapshotDiffEngine | None = None,
    ) -> None:
        self._source = source
        self._diff_engine = SnapshotDiffEngine() if diff_engine is None else diff_engine

    def check(self, request: MonitorCheckRequest) -> MonitorCheckResult:
        if not isinstance(request, MonitorCheckRequest):
            raise TypeError("check requires a MonitorCheckRequest")
        request = MonitorCheckRequest.model_validate(request)
        observed = self._source.observe(request)
        if not isinstance(observed, SourceObservationResult):
            raise TypeError("Observation source must return SourceObservationResult")
        observed = SourceObservationResult.model_validate(observed)
        if observed.outcome == MonitorCheckOutcome.CHECK_FAILED:
            return MonitorCheckResult(request=request, observation=observed)

        # Reject source contract violations before creating a Snapshot or comparing.
        if (
            observed.target != request.target
            or observed.observed_at != request.observed_at
        ):
            raise ValueError("Observation target/time must match check request")
        if (
            observed.source.source_url != request.source.source_url
            or observed.source.source_type != request.source.source_type
            or observed.source.verification_status != request.source.verification_status
        ):
            raise ValueError(
                "A check cannot rebind or upgrade source verification policy"
            )

        current = CompetitionSnapshot(
            snapshot_id=_snapshot_id(
                observed.target, observed.observed_at, observed.dynamic_state
            ),
            target=observed.target,
            observed_at=observed.observed_at,
            dynamic_state=observed.dynamic_state,
        )
        diff = (
            self._diff_engine.compare(request.previous_snapshot, current)
            if request.previous_snapshot is not None
            else None
        )
        return MonitorCheckResult(
            request=request, observation=observed, snapshot=current, diff=diff
        )
