"""Synthetic verified-Seed tests for the JSON infrastructure adapter."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pytest

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    SourceType,
    VerificationStatus,
)
from competition_copilot.infrastructure.repositories import (
    JsonSeedCompetitionRepository,
    SeedRepositoryLoadError,
)
from competition_copilot.ingestion.candidate import CandidateStatus
from competition_copilot.ingestion.seed import (
    CompetitionSeedEnvelope,
    SeedApprovalRecord,
    serialize_seed,
)
from competition_copilot.ingestion.verification import SourceVerificationRecord
from competition_copilot.repositories import (
    RepositoryDuplicateIdError,
    RepositoryEntityNotFoundError,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _seed(
    *,
    competition_id: str = "alpha",
    competition_name: str = "Alpha",
    edition_id: str = "alpha-2026",
    year: int = 2026,
    track_ids: tuple[str, ...] = (),
    version: Literal["1.0", "1.1"] = "1.1",
) -> CompetitionSeedEnvelope:
    source = SourceMetadata(
        source_url="https://example.org/official",
        source_type=SourceType.OFFICIAL,
        observed_at=NOW,
        verification_status=VerificationStatus.VERIFIED,
    )
    candidate_id = f"{edition_id}-candidate"
    return CompetitionSeedEnvelope(
        schema_version=version,
        artifact_type="verified_competition_seed",
        raw_fixture_path=f"data/raw/{edition_id}.json",
        approval=SeedApprovalRecord(
            candidate_id=candidate_id,
            status=CandidateStatus.APPROVED,
            reviewed_at=NOW,
            review_note="Explicit human approval",
        ),
        verification=SourceVerificationRecord(
            candidate_id=candidate_id,
            verified_at=NOW,
            verification_note="Explicit source verification",
            previous_status=VerificationStatus.PENDING,
            new_status=VerificationStatus.VERIFIED,
            source_url=source.source_url,
        ),
        validation_issues=[],
        competition=Competition(id=competition_id, name=competition_name),
        competition_source=source,
        edition=CompetitionEdition(
            id=edition_id,
            competition_id=competition_id,
            year=year,
            name=f"Edition {edition_id}",
            source=source,
        ),
        tracks=[
            CompetitionTrack(id=track_id, edition_id=edition_id, name=track_id, source=source)
            for track_id in track_ids
        ],
        **({"temporal_provenance": []} if version == "1.1" else {}),
    )


def _write(directory: Path, filename: str, seed: CompetitionSeedEnvelope) -> Path:
    path = directory / filename
    path.write_bytes(serialize_seed(seed))
    return path


def test_existing_empty_directory_is_a_valid_empty_repository(tmp_path: Path) -> None:
    repository = JsonSeedCompetitionRepository(tmp_path)

    assert repository.list_competitions() == []
    assert repository.list_editions() == []


@pytest.mark.parametrize(
    ("method", "entity_type"),
    [
        ("list_editions_by_competition", "competition"),
        ("list_tracks", "edition"),
    ],
)
def test_unknown_parent_raises_not_found_even_with_other_entities_present(
    tmp_path: Path, method: str, entity_type: str
) -> None:
    _write(tmp_path, "known.json", _seed(version="1.0"))
    repository = JsonSeedCompetitionRepository(tmp_path)

    with pytest.raises(RepositoryEntityNotFoundError) as raised:
        getattr(repository, method)("unknown")

    assert raised.value.entity_type == entity_type
    assert raised.value.requested_id == "unknown"


def test_discovery_ignores_nested_and_non_json_files(tmp_path: Path) -> None:
    _write(tmp_path, "valid.json", _seed(version="1.0"))
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "invalid.json").write_text("{invalid json", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("{invalid json", encoding="utf-8")

    repository = JsonSeedCompetitionRepository(tmp_path)

    assert [item.id for item in repository.list_competitions()] == ["alpha"]


@pytest.mark.parametrize(
    ("path_kind", "reason"),
    [("missing", "SEED_DIRECTORY_MISSING"), ("file", "SEED_DIRECTORY_INVALID")],
)
def test_invalid_seed_directory_fails(
    tmp_path: Path, path_kind: str, reason: str
) -> None:
    path = tmp_path / "seeds"
    if path_kind == "file":
        path.write_text("not a directory", encoding="utf-8")

    with pytest.raises(SeedRepositoryLoadError) as raised:
        JsonSeedCompetitionRepository(path)

    assert raised.value.reason == reason
    assert raised.value.artifact_path == path


@pytest.mark.parametrize(
    ("method", "entity_type"),
    [
        ("get_competition", "competition"),
        ("get_edition", "edition"),
        ("get_track", "track"),
    ],
)
def test_unknown_single_entity_uses_contract_error(
    tmp_path: Path, method: str, entity_type: str
) -> None:
    repository = JsonSeedCompetitionRepository(tmp_path)

    with pytest.raises(RepositoryEntityNotFoundError) as raised:
        getattr(repository, method)("unknown")

    assert raised.value.entity_type == entity_type
    assert raised.value.requested_id == "unknown"


@pytest.mark.parametrize("version", ["1.0", "1.1"])
def test_single_zero_track_seed_loads_without_raw_or_manifest(
    tmp_path: Path, version: Literal["1.0", "1.1"]
) -> None:
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    seed = _seed(version=version)
    _write(seed_dir, "alpha.json", seed)

    repository = JsonSeedCompetitionRepository(seed_dir)

    assert repository.list_competitions() == [seed.competition]
    assert repository.get_competition("alpha") == seed.competition
    assert repository.list_editions() == [seed.edition]
    assert repository.get_edition("alpha-2026") == seed.edition
    assert repository.list_editions_by_competition("alpha") == [seed.edition]
    assert repository.list_tracks("alpha-2026") == []
    assert not isinstance(repository.get_edition("alpha-2026"), CompetitionSeedEnvelope)
    assert not hasattr(repository.get_edition("alpha-2026"), "raw_fixture_path")


def test_ordering_track_lookup_detachment_and_eager_snapshot(tmp_path: Path) -> None:
    _write(tmp_path, "z-first.json", _seed(edition_id="alpha-2027", year=2027))
    _write(
        tmp_path,
        "a-second.json",
        _seed(
            competition_id="zeta",
            edition_id="zeta-2025",
            year=2025,
            track_ids=("z-track", "a-track"),
        ),
    )
    _write(tmp_path, "m-third.json", _seed(edition_id="alpha-2025", year=2025))

    repository = JsonSeedCompetitionRepository(tmp_path)

    assert [item.id for item in repository.list_competitions()] == ["alpha", "zeta"]
    assert [item.id for item in repository.list_editions()] == [
        "alpha-2025",
        "zeta-2025",
        "alpha-2027",
    ]
    assert [item.id for item in repository.list_editions_by_competition("alpha")] == [
        "alpha-2025",
        "alpha-2027",
    ]
    assert [item.id for item in repository.list_tracks("zeta-2025")] == [
        "z-track",
        "a-track",
    ]
    assert repository.get_track("z-track").id == "z-track"

    returned = repository.get_competition("alpha")
    returned.name = "Caller mutation"
    repository.list_tracks("zeta-2025")[0].name = "Caller mutation"
    assert repository.get_competition("alpha").name == "Alpha"
    assert repository.get_track("z-track").name == "z-track"

    for path in tmp_path.glob("*.json"):
        path.unlink()
    assert len(repository.list_editions()) == 3
    assert repository.get_track("a-track").id == "a-track"


def test_identical_competition_is_merged_across_editions(tmp_path: Path) -> None:
    _write(tmp_path, "one.json", _seed())
    _write(tmp_path, "two.json", _seed(edition_id="alpha-2027", year=2027))

    repository = JsonSeedCompetitionRepository(tmp_path)

    assert [item.id for item in repository.list_competitions()] == ["alpha"]
    assert [item.id for item in repository.list_editions_by_competition("alpha")] == [
        "alpha-2026",
        "alpha-2027",
    ]


def test_multi_edition_and_cross_competition_relationships(tmp_path: Path) -> None:
    _write(tmp_path, "z.json", _seed(track_ids=("track-a", "track-b")))
    _write(
        tmp_path,
        "a.json",
        _seed(edition_id="alpha-2027", year=2027, track_ids=("track-c",)),
    )
    _write(
        tmp_path,
        "m.json",
        _seed(
            competition_id="beta",
            competition_name="Beta",
            edition_id="beta-2026",
            track_ids=("track-d",),
        ),
    )
    repository = JsonSeedCompetitionRepository(tmp_path)

    assert [item.id for item in repository.list_competitions()] == ["alpha", "beta"]
    assert repository.get_competition("alpha").name == "Alpha"
    assert [item.id for item in repository.list_editions_by_competition("alpha")] == [
        "alpha-2026",
        "alpha-2027",
    ]
    assert [item.id for item in repository.list_editions_by_competition("beta")] == [
        "beta-2026"
    ]
    assert repository.get_edition("alpha-2026").competition_id == "alpha"
    assert repository.get_edition("alpha-2027").competition_id == "alpha"
    assert repository.get_edition("beta-2026").competition_id == "beta"
    assert [item.id for item in repository.list_tracks("alpha-2026")] == [
        "track-a",
        "track-b",
    ]
    assert [item.id for item in repository.list_tracks("alpha-2027")] == ["track-c"]
    assert [item.id for item in repository.list_tracks("beta-2026")] == ["track-d"]
    for track_id, edition_id in (
        ("track-a", "alpha-2026"),
        ("track-b", "alpha-2026"),
        ("track-c", "alpha-2027"),
        ("track-d", "beta-2026"),
    ):
        assert repository.get_track(track_id).edition_id == edition_id


def test_many_track_order_and_repeated_queries_are_stable(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "edition.json",
        _seed(track_ids=("track-c", "track-a", "track-b")),
    )
    repository = JsonSeedCompetitionRepository(tmp_path)

    for _ in range(3):
        assert [item.id for item in repository.list_competitions()] == ["alpha"]
        assert [item.id for item in repository.list_editions()] == ["alpha-2026"]
        assert [item.id for item in repository.list_editions_by_competition("alpha")] == [
            "alpha-2026"
        ]
        assert [item.id for item in repository.list_tracks("alpha-2026")] == [
            "track-c",
            "track-a",
            "track-b",
        ]


def test_new_seed_is_visible_only_to_a_new_repository_instance(tmp_path: Path) -> None:
    _write(tmp_path, "first.json", _seed(track_ids=("first-track",)))
    first = JsonSeedCompetitionRepository(tmp_path)
    before = first.list_competitions()

    _write(
        tmp_path,
        "second.json",
        _seed(competition_id="beta", competition_name="Beta", edition_id="beta-2027"),
    )
    assert first.list_competitions() == before
    assert [item.id for item in first.list_editions()] == ["alpha-2026"]
    with pytest.raises(RepositoryEntityNotFoundError):
        first.get_competition("beta")

    second = JsonSeedCompetitionRepository(tmp_path)
    assert [item.id for item in second.list_competitions()] == ["alpha", "beta"]
    assert [item.id for item in second.list_editions()] == [
        "alpha-2026",
        "beta-2027",
    ]

    for path in tmp_path.glob("*.json"):
        path.unlink()
    assert first.get_track("first-track").id == "first-track"
    assert second.get_competition("beta").name == "Beta"
    assert second.list_editions_by_competition("beta")[0].id == "beta-2027"
    assert second.list_tracks("alpha-2026")[0].id == "first-track"


def test_returned_collections_and_domain_objects_are_isolated(tmp_path: Path) -> None:
    _write(tmp_path, "edition.json", _seed(track_ids=("one", "two")))
    repository = JsonSeedCompetitionRepository(tmp_path)

    for items in (
        repository.list_competitions(),
        repository.list_editions(),
        repository.list_editions_by_competition("alpha"),
        repository.list_tracks("alpha-2026"),
    ):
        assert isinstance(items, list)
        items.clear()

    assert all(isinstance(item, Competition) for item in repository.list_competitions())
    assert all(isinstance(item, CompetitionEdition) for item in repository.list_editions())
    assert all(isinstance(item, CompetitionTrack) for item in repository.list_tracks("alpha-2026"))
    assert [item.id for item in repository.list_competitions()] == ["alpha"]
    assert [item.id for item in repository.list_editions()] == ["alpha-2026"]
    assert [item.id for item in repository.list_editions_by_competition("alpha")] == [
        "alpha-2026"
    ]
    assert [item.id for item in repository.list_tracks("alpha-2026")] == [
        "one",
        "two",
    ]

    competition = repository.get_competition("alpha")
    edition = repository.get_edition("alpha-2026")
    track = repository.get_track("one")
    assert isinstance(competition, Competition)
    assert isinstance(edition, CompetitionEdition)
    assert isinstance(track, CompetitionTrack)
    for entity in (competition, edition, track):
        assert not isinstance(entity, CompetitionSeedEnvelope)
        assert not {
            "schema_version",
            "artifact_type",
            "raw_fixture_path",
            "approval",
            "verification",
            "raw_payload",
        }.intersection(entity.model_dump())


def test_conflicting_competition_fails_without_choosing_a_winner(tmp_path: Path) -> None:
    _write(tmp_path, "a.json", _seed())
    conflict = _write(
        tmp_path,
        "b.json",
        _seed(competition_name="Different Alpha", edition_id="alpha-2027"),
    )

    with pytest.raises(SeedRepositoryLoadError) as raised:
        JsonSeedCompetitionRepository(tmp_path)

    assert raised.value.reason == "CONFLICTING_COMPETITION"
    assert raised.value.artifact_path == conflict


def test_duplicate_edition_fails_as_load_and_contract_error(tmp_path: Path) -> None:
    _write(tmp_path, "a.json", _seed())
    duplicate = _write(tmp_path, "b.json", _seed())

    with pytest.raises(SeedRepositoryLoadError) as raised:
        JsonSeedCompetitionRepository(tmp_path)

    assert isinstance(raised.value, RepositoryDuplicateIdError)
    assert raised.value.reason == "DUPLICATE_EDITION_ID"
    assert raised.value.artifact_path == duplicate


def test_duplicate_track_fails_as_load_and_contract_error(tmp_path: Path) -> None:
    _write(tmp_path, "a.json", _seed(track_ids=("same-track",)))
    duplicate = _write(
        tmp_path,
        "b.json",
        _seed(edition_id="alpha-2027", track_ids=("same-track",)),
    )

    with pytest.raises(SeedRepositoryLoadError) as raised:
        JsonSeedCompetitionRepository(tmp_path)

    assert isinstance(raised.value, RepositoryDuplicateIdError)
    assert raised.value.reason == "DUPLICATE_TRACK_ID"
    assert raised.value.artifact_path == duplicate


def test_invalid_json_fails_atomic_construction(tmp_path: Path) -> None:
    _write(tmp_path, "a.json", _seed())
    bad = tmp_path / "b.json"
    bad.write_text("{invalid json", encoding="utf-8")

    with pytest.raises(SeedRepositoryLoadError) as raised:
        JsonSeedCompetitionRepository(tmp_path)

    assert raised.value.reason == "INVALID_SEED"
    assert raised.value.artifact_path == bad


def test_unsupported_seed_version_fails(tmp_path: Path) -> None:
    payload = json.loads(serialize_seed(_seed()))
    payload["schema_version"] = "9.9"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SeedRepositoryLoadError) as raised:
        JsonSeedCompetitionRepository(tmp_path)

    assert raised.value.reason == "INVALID_SEED"
    assert raised.value.artifact_path == bad


def test_invalid_seed_relationship_fails(tmp_path: Path) -> None:
    payload = json.loads(serialize_seed(_seed()))
    payload["edition"]["competition_id"] = "missing"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SeedRepositoryLoadError) as raised:
        JsonSeedCompetitionRepository(tmp_path)

    assert raised.value.reason == "INVALID_SEED"
    assert raised.value.artifact_path == bad
