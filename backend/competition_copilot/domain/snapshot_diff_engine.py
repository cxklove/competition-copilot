"""Pure comparison of validated observations; low-level changes only."""

from datetime import datetime

from competition_copilot.domain.digital_twin import (
    CompetitionSnapshot,
    FactChangeKind,
    ObservationState,
    ObservedInstant,
    ObservedTimeWindow,
    SnapshotChange,
    SnapshotDiff,
    SnapshotReference,
    TimeWindowChange,
    TrackMembershipChange,
    WindowEndpointChange,
)


def _state_transition(
    before: ObservationState, after: ObservationState
) -> FactChangeKind | None:
    if before == after:
        return None
    if ObservationState.UNKNOWN in (before, after):
        return FactChangeKind.OBSERVATION_STATE_CHANGED
    return FactChangeKind.PRESENCE_CHANGED


def _endpoint(value: datetime | None, window: ObservedTimeWindow) -> ObservedInstant:
    if value is None:
        return ObservedInstant(state=ObservationState.UNKNOWN, sources=window.sources)
    return ObservedInstant(
        state=ObservationState.KNOWN_VALUE, value=value, sources=window.sources
    )


class SnapshotDiffEngine:
    """Compare fields in fixed window/start/end/membership order.

    Provenance-only changes are ignored. Known track sets use the frozen
    TrackMembershipChange before/after representation, not per-member records.
    """

    def compare(
        self, before: CompetitionSnapshot, after: CompetitionSnapshot
    ) -> SnapshotDiff:
        if not isinstance(before, CompetitionSnapshot) or not isinstance(
            after, CompetitionSnapshot
        ):
            raise TypeError("compare requires CompetitionSnapshot inputs")
        before = CompetitionSnapshot.model_validate(before)
        after = CompetitionSnapshot.model_validate(after)
        before_ref = SnapshotReference(
            snapshot_id=before.snapshot_id,
            target=before.target,
            observed_at=before.observed_at,
        )
        after_ref = SnapshotReference(
            snapshot_id=after.snapshot_id,
            target=after.target,
            observed_at=after.observed_at,
        )
        # Apply target, chronology and same-ID metadata integrity before comparing.
        empty = SnapshotDiff(before=before_ref, after=after_ref)
        if before.snapshot_id == after.snapshot_id:
            if before != after:
                raise ValueError(
                    "Same snapshot ID cannot identify different snapshot content"
                )
            return empty

        changes: list[SnapshotChange] = []
        for field in ("registration_window", "competition_window"):
            left = getattr(before.dynamic_state, field)
            right = getattr(after.dynamic_state, field)
            kind = _state_transition(left.state, right.state)
            if kind is not None:
                changes.append(
                    TimeWindowChange(field=field, kind=kind, before=left, after=right)
                )
            elif left.state == ObservationState.KNOWN_VALUE:
                for boundary in ("start_at", "end_at"):
                    old_value = getattr(left.value, boundary)
                    new_value = getattr(right.value, boundary)
                    if old_value == new_value:
                        continue
                    old = _endpoint(old_value, left)
                    new = _endpoint(new_value, right)
                    kind = _state_transition(old.state, new.state)
                    changes.append(
                        WindowEndpointChange(
                            field=f"{field}.{boundary}",
                            kind=kind or FactChangeKind.VALUE_CHANGED,
                            before=old,
                            after=new,
                        )
                    )

        left = before.dynamic_state.track_membership
        right = after.dynamic_state.track_membership
        kind = _state_transition(left.state, right.state)
        if kind is None and left.state == ObservationState.KNOWN_VALUE:
            if left.value != right.value:
                kind = FactChangeKind.VALUE_CHANGED
        if kind is not None:
            changes.append(
                TrackMembershipChange(
                    field="track_membership", kind=kind, before=left, after=right
                )
            )
        return SnapshotDiff(before=before_ref, after=after_ref, changes=tuple(changes))
