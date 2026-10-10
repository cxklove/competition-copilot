"""Eager, read-only CompetitionRepository backed by verified Seed JSON files."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from pydantic import ValidationError

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.ingestion.seed import CompetitionSeedEnvelope, deserialize_seed
from competition_copilot.repositories.competition import (
    CompetitionRepository,
    RepositoryDuplicateIdError,
    RepositoryEntityNotFoundError,
    RepositoryEntityType,
)


class SeedRepositoryLoadError(ValueError):
    """A Seed directory or one of its artifacts cannot form a repository."""

    def __init__(
        self, reason: str, artifact_path: Path, detail: str
    ) -> None:
        self.reason = reason
        self.artifact_path = artifact_path
        self.detail = detail
        ValueError.__init__(self, f"{reason}: {artifact_path}: {detail}")


class _DuplicateSeedEntityError(SeedRepositoryLoadError, RepositoryDuplicateIdError):
    """A duplicate is both a repository contract and Seed load failure."""

    def __init__(
        self,
        entity_type: RepositoryEntityType,
        duplicate_id: str,
        artifact_path: Path,
    ) -> None:
        self.entity_type = entity_type
        self.duplicate_id = duplicate_id
        super().__init__(
            f"DUPLICATE_{entity_type.upper()}_ID",
            artifact_path,
            f"duplicate {entity_type} id: {duplicate_id}",
        )


@dataclass(frozen=True)
class _Indexes:
    competitions: Mapping[str, Competition]
    editions: Mapping[str, CompetitionEdition]
    tracks: Mapping[str, CompetitionTrack]
    competition_ids: tuple[str, ...]
    edition_ids: tuple[str, ...]
    edition_ids_by_competition: Mapping[str, tuple[str, ...]]
    track_ids_by_edition: Mapping[str, tuple[str, ...]]


def _load_seeds(seed_dir: Path) -> list[tuple[Path, CompetitionSeedEnvelope]]:
    if not seed_dir.exists():
        raise SeedRepositoryLoadError(
            "SEED_DIRECTORY_MISSING", seed_dir, "Seed directory does not exist"
        )
    if not seed_dir.is_dir():
        raise SeedRepositoryLoadError(
            "SEED_DIRECTORY_INVALID", seed_dir, "Seed path is not a directory"
        )
    try:
        paths = sorted(seed_dir.glob("*.json"), key=lambda path: path.name)
    except OSError as exc:
        raise SeedRepositoryLoadError(
            "SEED_DISCOVERY_FAILED", seed_dir, str(exc)
        ) from exc

    loaded = []
    for path in paths:
        try:
            seed = deserialize_seed(path.read_bytes())
        except OSError as exc:
            raise SeedRepositoryLoadError(
                "SEED_READ_FAILED", path, str(exc)
            ) from exc
        except ValidationError as exc:
            raise SeedRepositoryLoadError("INVALID_SEED", path, str(exc)) from exc
        loaded.append((path, seed))
    return loaded


def _build_indexes(
    loaded: list[tuple[Path, CompetitionSeedEnvelope]],
) -> _Indexes:
    competitions: dict[str, Competition] = {}
    editions: dict[str, CompetitionEdition] = {}
    tracks: dict[str, CompetitionTrack] = {}
    edition_paths: dict[str, Path] = {}
    track_paths: dict[str, Path] = {}
    track_ids_by_edition: dict[str, list[str]] = {}

    for path, seed in loaded:
        competition = seed.competition
        existing = competitions.get(competition.id)
        if existing is None:
            competitions[competition.id] = competition.model_copy(deep=True)
        elif existing != competition:
            raise SeedRepositoryLoadError(
                "CONFLICTING_COMPETITION",
                path,
                f"Competition {competition.id} differs from an earlier artifact",
            )

        edition = seed.edition
        if edition.id in editions:
            raise _DuplicateSeedEntityError("edition", edition.id, path)
        editions[edition.id] = edition.model_copy(deep=True)
        edition_paths[edition.id] = path

        track_ids_by_edition[edition.id] = []
        for track in seed.tracks:
            if track.id in tracks:
                raise _DuplicateSeedEntityError("track", track.id, path)
            tracks[track.id] = track.model_copy(deep=True)
            track_paths[track.id] = path
            track_ids_by_edition[edition.id].append(track.id)

    for edition in editions.values():
        if edition.competition_id not in competitions:
            raise SeedRepositoryLoadError(
                "ORPHAN_EDITION",
                edition_paths[edition.id],
                f"Edition {edition.id} has no Competition {edition.competition_id}",
            )
    for track in tracks.values():
        if track.edition_id not in editions:
            raise SeedRepositoryLoadError(
                "ORPHAN_TRACK",
                track_paths[track.id],
                f"Track {track.id} has no Edition {track.edition_id}",
            )

    edition_ids = tuple(sorted(editions, key=lambda key: (editions[key].year, key)))
    edition_ids_by_competition: dict[str, list[str]] = {}
    for edition_id in edition_ids:
        competition_id = editions[edition_id].competition_id
        edition_ids_by_competition.setdefault(competition_id, []).append(edition_id)

    return _Indexes(
        competitions=MappingProxyType(competitions),
        editions=MappingProxyType(editions),
        tracks=MappingProxyType(tracks),
        competition_ids=tuple(sorted(competitions)),
        edition_ids=edition_ids,
        edition_ids_by_competition=MappingProxyType(
            {key: tuple(value) for key, value in edition_ids_by_competition.items()}
        ),
        track_ids_by_edition=MappingProxyType(
            {key: tuple(value) for key, value in track_ids_by_edition.items()}
        ),
    )


class JsonSeedCompetitionRepository(CompetitionRepository):
    """Build all indexes from verified Seeds before exposing query methods."""

    def __init__(self, seed_dir: Path) -> None:
        loaded = _load_seeds(Path(seed_dir))
        self._indexes = _build_indexes(loaded)

    def list_competitions(self) -> list[Competition]:
        indexes = self._indexes
        return [
            indexes.competitions[key].model_copy(deep=True)
            for key in indexes.competition_ids
        ]

    def get_competition(self, competition_id: str) -> Competition:
        try:
            competition = self._indexes.competitions[competition_id]
        except KeyError:
            raise RepositoryEntityNotFoundError(
                "competition", competition_id
            ) from None
        return competition.model_copy(deep=True)

    def list_editions(self) -> list[CompetitionEdition]:
        indexes = self._indexes
        return [indexes.editions[key].model_copy(deep=True) for key in indexes.edition_ids]

    def get_edition(self, edition_id: str) -> CompetitionEdition:
        try:
            edition = self._indexes.editions[edition_id]
        except KeyError:
            raise RepositoryEntityNotFoundError("edition", edition_id) from None
        return edition.model_copy(deep=True)

    def list_editions_by_competition(
        self, competition_id: str
    ) -> list[CompetitionEdition]:
        indexes = self._indexes
        if competition_id not in indexes.competitions:
            raise RepositoryEntityNotFoundError("competition", competition_id)
        ids = indexes.edition_ids_by_competition.get(competition_id, ())
        return [indexes.editions[key].model_copy(deep=True) for key in ids]

    def list_tracks(self, edition_id: str) -> list[CompetitionTrack]:
        indexes = self._indexes
        if edition_id not in indexes.editions:
            raise RepositoryEntityNotFoundError("edition", edition_id)
        ids = indexes.track_ids_by_edition.get(edition_id, ())
        return [indexes.tracks[key].model_copy(deep=True) for key in ids]

    def get_track(self, track_id: str) -> CompetitionTrack:
        try:
            track = self._indexes.tracks[track_id]
        except KeyError:
            raise RepositoryEntityNotFoundError("track", track_id) from None
        return track.model_copy(deep=True)
