"""Repository-backed baseline observations of verified edition state."""

from datetime import datetime, timezone
from hashlib import sha256
from json import dumps

from pydantic import AwareDatetime, TypeAdapter

from competition_copilot.domain.competition import CompetitionTrack
from competition_copilot.domain.digital_twin import (
    CompetitionDynamicState,
    CompetitionSnapshot,
    CompetitionTarget,
    ObservationState,
    ObservedTimeWindow,
    ObservedTrackMembership,
)
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    VerificationStatus,
)
from competition_copilot.domain.temporal import TimeWindow
from competition_copilot.repositories.competition import CompetitionRepository


class SnapshotTargetMismatchError(ValueError):
    """A returned edition does not belong to the requested competition."""


class SnapshotTargetUnsupportedError(ValueError):
    """This baseline builder observes edition state only."""


class SnapshotProvenanceError(ValueError):
    """A known Repository fact lacks verified source metadata."""


def _verified_source(source: SourceMetadata | None, field: str) -> SourceMetadata:
    if source is None or source.verification_status != VerificationStatus.VERIFIED:
        raise SnapshotProvenanceError(f"Verified source required for {field}")
    return SourceMetadata.model_validate(source.model_dump())


def _window_observation(
    value: TimeWindow | None, source: SourceMetadata | None, field: str
) -> ObservedTimeWindow:
    if value is None:
        return ObservedTimeWindow(state=ObservationState.UNKNOWN)
    return ObservedTimeWindow(
        state=ObservationState.KNOWN_VALUE,
        value=value,
        sources=(_verified_source(source, field),),
    )


def _track_observation(
    tracks: list[CompetitionTrack], edition_source: SourceMetadata | None
) -> ObservedTrackMembership:
    sources = [_verified_source(edition_source, "track_membership")]
    for track in sorted(tracks, key=lambda item: item.id):
        sources.append(_verified_source(track.source, f"track:{track.id}"))
    # An edition source anchors the complete Repository child query, including [].
    # Track sources support each nonempty membership fact; no source is invented.
    unique_sources = {source.model_dump_json(): source for source in sources}
    return ObservedTrackMembership(
        state=ObservationState.KNOWN_VALUE,
        value=tuple(track.id for track in tracks),
        sources=tuple(unique_sources[key] for key in sorted(unique_sources)),
    )


def _snapshot_id(
    target: CompetitionTarget,
    observed_at: datetime,
    dynamic_state: CompetitionDynamicState,
) -> str:
    canonical = dumps(
        {
            "target": target.model_dump(mode="json"),
            "observed_at_utc": observed_at.astimezone(timezone.utc).isoformat(),
            "dynamic_state": dynamic_state.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return f"competition-snapshot-v1:{sha256(canonical.encode('utf-8')).hexdigest()}"


class CompetitionSnapshotBuilder:
    """Read one verified edition through the Repository interface, without IO of its own."""

    def __init__(self, repository: CompetitionRepository) -> None:
        self._repository = repository

    def build(
        self, target: CompetitionTarget, observed_at: datetime
    ) -> CompetitionSnapshot:
        validated_target = CompetitionTarget.model_validate(target)
        if validated_target.track_id is not None:
            raise SnapshotTargetUnsupportedError(
                "Track-level snapshots need independently observed track facts"
            )
        if not isinstance(observed_at, datetime):
            raise TypeError("observed_at must be an aware datetime")
        observed_at = TypeAdapter(AwareDatetime).validate_python(observed_at)

        competition = self._repository.get_competition(validated_target.competition_id)
        edition = self._repository.get_edition(validated_target.edition_id)
        if competition.id != validated_target.competition_id or (
            edition.id != validated_target.edition_id
            or edition.competition_id != competition.id
        ):
            raise SnapshotTargetMismatchError(
                "Edition does not belong to target competition"
            )
        tracks = self._repository.list_tracks(edition.id)
        if any(track.edition_id != edition.id for track in tracks):
            raise SnapshotTargetMismatchError("Track does not belong to target edition")

        state = CompetitionDynamicState(
            registration_window=_window_observation(
                edition.registration_window, edition.source, "registration_window"
            ),
            competition_window=_window_observation(
                edition.competition_window, edition.source, "competition_window"
            ),
            track_membership=_track_observation(tracks, edition.source),
        )
        return CompetitionSnapshot(
            snapshot_id=_snapshot_id(validated_target, observed_at, state),
            target=validated_target,
            observed_at=observed_at,
            dynamic_state=state,
        )
