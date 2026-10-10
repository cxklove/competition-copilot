"""Read-only P3 Repository consumption of the real verified Seed corpus."""

import tomllib
from pathlib import Path

import pytest

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.infrastructure.repositories import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.ingestion.seed import (
    CompetitionSeedEnvelope,
    deserialize_seed,
)
from competition_copilot.repositories import (
    CompetitionRepository,
    RepositoryEntityNotFoundError,
)

ROOT = Path(__file__).resolve().parents[3]
SEED_DIR = ROOT / "data/seed"
FORBIDDEN_ARTIFACT_FIELDS = {
    "schema_version",
    "artifact_type",
    "raw_fixture_path",
    "approval",
    "verification",
    "raw_payload",
}


@pytest.fixture(scope="module")
def seeds() -> list[CompetitionSeedEnvelope]:
    seed_files = sorted(SEED_DIR.glob("*.json"))
    assert seed_files, "P3 integration requires verified Seed files"
    return [deserialize_seed(path.read_bytes()) for path in seed_files]


@pytest.fixture(scope="module")
def repository() -> CompetitionRepository:
    return JsonSeedCompetitionRepository(SEED_DIR)


def test_real_seed_domain_graph_is_complete_and_ordered(
    seeds: list[CompetitionSeedEnvelope], repository: CompetitionRepository
) -> None:
    competitions: dict[str, Competition] = {}
    editions: dict[str, CompetitionEdition] = {}
    tracks: dict[str, CompetitionTrack] = {}
    track_ids_by_edition: dict[str, list[str]] = {}

    for seed in seeds:
        existing = competitions.get(seed.competition.id)
        if existing is not None:
            assert existing == seed.competition
        competitions[seed.competition.id] = seed.competition
        assert seed.edition.id not in editions
        editions[seed.edition.id] = seed.edition
        track_ids_by_edition[seed.edition.id] = []
        for track in seed.tracks:
            assert track.id not in tracks
            tracks[track.id] = track
            track_ids_by_edition[seed.edition.id].append(track.id)

    competition_ids = sorted(competitions)
    edition_ids = sorted(editions, key=lambda key: (editions[key].year, key))
    assert repository.list_competitions() == [
        competitions[competition_id] for competition_id in competition_ids
    ]
    assert repository.list_editions() == [editions[edition_id] for edition_id in edition_ids]

    for competition_id in competition_ids:
        assert repository.get_competition(competition_id) == competitions[competition_id]
        child_ids = [
            edition_id
            for edition_id in edition_ids
            if editions[edition_id].competition_id == competition_id
        ]
        assert repository.list_editions_by_competition(competition_id) == [
            editions[edition_id] for edition_id in child_ids
        ]
        for edition_id in child_ids:
            assert repository.get_edition(edition_id) == editions[edition_id]
            assert editions[edition_id].competition_id == competition_id

    for edition_id in edition_ids:
        edition = editions[edition_id]
        assert repository.get_competition(edition.competition_id) == competitions[
            edition.competition_id
        ]
        actual_tracks = repository.list_tracks(edition_id)
        assert [track.id for track in actual_tracks] == track_ids_by_edition[edition_id]
        for track in actual_tracks:
            assert track == tracks[track.id]
            assert track.edition_id == edition_id
            assert repository.get_track(track.id) == track

    assert sum(len(ids) for ids in track_ids_by_edition.values()) == len(tracks)


def test_real_zero_track_and_unknown_parent_are_distinct(
    seeds: list[CompetitionSeedEnvelope], repository: CompetitionRepository
) -> None:
    zero_track_ids = [seed.edition.id for seed in seeds if not seed.tracks]
    assert zero_track_ids
    for edition_id in zero_track_ids:
        assert repository.list_tracks(edition_id) == []

    for method, entity_type in (
        (repository.list_editions_by_competition, "competition"),
        (repository.list_tracks, "edition"),
    ):
        with pytest.raises(RepositoryEntityNotFoundError) as raised:
            method("__unknown__")
        assert raised.value.entity_type == entity_type
        assert raised.value.requested_id == "__unknown__"


def test_both_seed_versions_expose_only_domain_entities(
    seeds: list[CompetitionSeedEnvelope], repository: CompetitionRepository
) -> None:
    versions = {seed.schema_version for seed in seeds}
    assert {"1.0", "1.1"} <= versions

    for seed in seeds:
        entities = (
            repository.get_competition(seed.competition.id),
            repository.get_edition(seed.edition.id),
            *(repository.get_track(track.id) for track in seed.tracks),
        )
        assert isinstance(entities[0], Competition)
        assert isinstance(entities[1], CompetitionEdition)
        assert all(isinstance(entity, CompetitionTrack) for entity in entities[2:])
        for entity in entities:
            assert not isinstance(entity, CompetitionSeedEnvelope)
            assert not FORBIDDEN_ARTIFACT_FIELDS.intersection(entity.model_dump())


def test_real_queries_are_stable_and_return_detached_collections(
    repository: CompetitionRepository,
) -> None:
    competitions = repository.list_competitions()
    editions = repository.list_editions()
    editions_by_parent = {
        competition.id: repository.list_editions_by_competition(competition.id)
        for competition in competitions
    }
    tracks_by_parent = {
        edition.id: repository.list_tracks(edition.id) for edition in editions
    }

    for _ in range(3):
        assert repository.list_competitions() == competitions
        assert repository.list_editions() == editions
        for competition_id, expected in editions_by_parent.items():
            assert repository.list_editions_by_competition(competition_id) == expected
        for edition_id, expected in tracks_by_parent.items():
            assert repository.list_tracks(edition_id) == expected

    competitions.clear()
    editions.clear()
    assert repository.list_competitions()
    assert repository.list_editions()

    parent_editions = next(iter(editions_by_parent))
    expected_editions = editions_by_parent[parent_editions].copy()
    editions_by_parent[parent_editions].clear()
    assert repository.list_editions_by_competition(parent_editions) == expected_editions

    edition_with_tracks = next(
        edition_id for edition_id, tracks in tracks_by_parent.items() if tracks
    )
    expected_tracks = tracks_by_parent[edition_with_tracks].copy()
    tracks_by_parent[edition_with_tracks].clear()
    assert repository.list_tracks(edition_with_tracks) == expected_tracks


def test_repository_is_read_only() -> None:
    for method in ("save", "create", "update", "delete", "upsert"):
        assert not hasattr(CompetitionRepository, method)
        assert not hasattr(JsonSeedCompetitionRepository, method)


def test_repository_packages_are_configured() -> None:
    configuration = tomllib.loads((ROOT / "backend/pyproject.toml").read_text("utf-8"))
    packages = set(configuration["tool"]["setuptools"]["packages"])
    assert {
        "competition_copilot.repositories",
        "competition_copilot.infrastructure",
        "competition_copilot.infrastructure.repositories",
    } <= packages
