"""Real Verified Seed -> Repository -> Competition Tool -> JSON boundary."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

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
from competition_copilot.repositories import CompetitionRepository
from competition_copilot.tools import (
    GetCompetitionEditionTool,
    GetCompetitionTool,
    GetCompetitionTrackTool,
    ListCompetitionEditionsTool,
    ListCompetitionsTool,
    ListEditionTracksTool,
    ToolErrorCode,
)

ROOT = Path(__file__).resolve().parents[3]
SEED_DIR = ROOT / "data/seed"
FORBIDDEN_ARTIFACT_KEYS = {
    "schema_version",
    "artifact_type",
    "raw_fixture_path",
    "approval",
    "verification",
    "raw_payload",
}


@pytest.fixture(scope="module")
def seeds() -> list[CompetitionSeedEnvelope]:
    paths = sorted(SEED_DIR.glob("*.json"))
    assert paths, "P4 integration requires at least one Verified Seed"
    return [deserialize_seed(path.read_bytes()) for path in paths]


@pytest.fixture(scope="module")
def repository() -> CompetitionRepository:
    return JsonSeedCompetitionRepository(SEED_DIR)


@pytest.fixture(scope="module")
def tools(repository: CompetitionRepository) -> dict[str, Any]:
    return {
        "list_competitions": ListCompetitionsTool(repository),
        "get_competition": GetCompetitionTool(repository),
        "list_competition_editions": ListCompetitionEditionsTool(repository),
        "get_competition_edition": GetCompetitionEditionTool(repository),
        "list_edition_tracks": ListEditionTracksTool(repository),
        "get_competition_track": GetCompetitionTrackTool(repository),
    }


def _assert_json_primitives(value: object) -> None:
    if value is None or type(value) in (str, int, float, bool):
        return
    if isinstance(value, list):
        for item in value:
            _assert_json_primitives(item)
        return
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value)
        for item in value.values():
            _assert_json_primitives(item)
        return
    pytest.fail(f"Non-JSON value: {type(value).__name__}")


def _assert_no_artifact_keys(value: object) -> None:
    if isinstance(value, dict):
        assert not FORBIDDEN_ARTIFACT_KEYS.intersection(value)
        for item in value.values():
            _assert_no_artifact_keys(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_artifact_keys(item)


def _json_result(result: Any) -> dict[str, Any]:
    dumped = result.model_dump(mode="json")
    assert set(dumped) == {"success", "data", "error"}
    _assert_json_primitives(dumped)
    _assert_no_artifact_keys(dumped)
    assert json.loads(result.model_dump_json()) == dumped
    assert type(result).model_validate_json(result.model_dump_json()) == result
    return dumped


def _assert_success(result: Any) -> dict[str, Any]:
    dumped = _json_result(result)
    assert result.success is True
    assert result.data is not None
    assert result.error is None
    assert dumped["success"] is True
    assert dumped["data"] is not None
    assert dumped["error"] is None
    return dumped


def _assert_error(result: Any, code: ToolErrorCode) -> dict[str, Any]:
    dumped = _json_result(result)
    assert result.success is False
    assert result.data is None
    assert result.error is not None
    assert result.error.code is code
    assert dumped["success"] is False
    assert dumped["data"] is None
    assert dumped["error"]["code"] == code.value
    assert dumped["error"]["message"]
    assert "RepositoryEntityNotFoundError" not in result.model_dump_json()
    return dumped


def test_real_seed_repository_construction_and_six_tool_metadata(
    seeds: list[CompetitionSeedEnvelope],
    repository: CompetitionRepository,
    tools: dict[str, Any],
) -> None:
    assert repository.list_competitions()
    assert repository.list_editions()
    assert seeds
    assert set(tools) == {
        "list_competitions",
        "get_competition",
        "list_competition_editions",
        "get_competition_edition",
        "list_edition_tracks",
        "get_competition_track",
    }
    for name, tool in tools.items():
        assert tool.metadata.name == name
        assert tool.metadata.description.strip()
        assert tool.metadata.input_schema["type"] == "object"
        assert set(tool.metadata.output_schema["properties"]) == {
            "success",
            "data",
            "error",
        }


def test_each_verified_seed_version_reaches_formal_tool_domain(
    seeds: list[CompetitionSeedEnvelope], tools: dict[str, Any]
) -> None:
    assert {seed.schema_version for seed in seeds} >= {"1.0", "1.1"}
    for seed in seeds:
        competition = tools["get_competition"].execute(
            {"competition_id": seed.competition.id}
        )
        edition = tools["get_competition_edition"].execute(
            {"edition_id": seed.edition.id}
        )
        tracks = tools["list_edition_tracks"].execute(
            {"edition_id": seed.edition.id}
        )
        _assert_success(competition)
        _assert_success(edition)
        _assert_success(tracks)
        assert competition.data.competition == seed.competition
        assert edition.data.edition == seed.edition
        assert tracks.data.tracks == seed.tracks


def test_all_real_competitions_match_list_and_get_tools(
    repository: CompetitionRepository, tools: dict[str, Any]
) -> None:
    expected = repository.list_competitions()
    listed = tools["list_competitions"].execute({})
    dumped = _assert_success(listed)
    assert listed.data.competitions == expected
    assert [item["id"] for item in dumped["data"]["competitions"]] == [
        item.id for item in expected
    ]
    assert len({item.id for item in expected}) == len(expected)

    for competition in expected:
        result = tools["get_competition"].execute(
            {"competition_id": competition.id}
        )
        _assert_success(result)
        assert isinstance(result.data.competition, Competition)
        assert result.data.competition == competition
        assert result.data.competition == repository.get_competition(competition.id)


def test_all_real_editions_match_parent_list_and_get_tools(
    repository: CompetitionRepository, tools: dict[str, Any]
) -> None:
    expected_editions = repository.list_editions()
    seen: dict[str, CompetitionEdition] = {}
    competition_ids = {item.id for item in repository.list_competitions()}

    for competition_id in competition_ids:
        expected = repository.list_editions_by_competition(competition_id)
        result = tools["list_competition_editions"].execute(
            {"competition_id": competition_id}
        )
        dumped = _assert_success(result)
        assert result.data.editions == expected
        assert [item["id"] for item in dumped["data"]["editions"]] == [
            item.id for item in expected
        ]
        for edition in result.data.editions:
            assert edition.competition_id == competition_id
            assert edition.id not in seen
            seen[edition.id] = edition

    assert set(seen) == {edition.id for edition in expected_editions}
    for edition in expected_editions:
        result = tools["get_competition_edition"].execute({"edition_id": edition.id})
        _assert_success(result)
        assert isinstance(result.data.edition, CompetitionEdition)
        assert result.data.edition == edition == seen[edition.id]
        assert result.data.edition == repository.get_edition(edition.id)
        assert edition.competition_id in competition_ids


def test_all_real_tracks_match_parent_list_and_get_tools(
    repository: CompetitionRepository, tools: dict[str, Any]
) -> None:
    seen: dict[str, CompetitionTrack] = {}
    zero_track_editions = []
    for edition in repository.list_editions():
        expected = repository.list_tracks(edition.id)
        result = tools["list_edition_tracks"].execute({"edition_id": edition.id})
        dumped = _assert_success(result)
        assert result.data.tracks == expected
        assert [item["id"] for item in dumped["data"]["tracks"]] == [
            item.id for item in expected
        ]
        if not expected:
            zero_track_editions.append(edition.id)
            assert dumped["data"]["tracks"] == []
        for track in result.data.tracks:
            assert track.edition_id == edition.id
            assert track.id not in seen
            seen[track.id] = track

    assert zero_track_editions, "Real dataset should exercise zero-track Tools"
    assert seen, "Real dataset should exercise GetCompetitionTrack"
    for track in seen.values():
        result = tools["get_competition_track"].execute({"track_id": track.id})
        _assert_success(result)
        assert isinstance(result.data.track, CompetitionTrack)
        assert result.data.track == track == repository.get_track(track.id)


def test_unknown_entities_and_parents_map_to_tool_not_found(
    repository: CompetitionRepository, tools: dict[str, Any]
) -> None:
    unknown = "integration-test-unknown-id"
    assert unknown not in {item.id for item in repository.list_competitions()}
    assert unknown not in {item.id for item in repository.list_editions()}
    assert all(unknown not in {track.id for track in repository.list_tracks(edition.id)}
               for edition in repository.list_editions())
    for name, field in (
        ("get_competition", "competition_id"),
        ("list_competition_editions", "competition_id"),
        ("get_competition_edition", "edition_id"),
        ("list_edition_tracks", "edition_id"),
        ("get_competition_track", "track_id"),
    ):
        _assert_error(tools[name].execute({field: unknown}), ToolErrorCode.NOT_FOUND)


def test_invalid_ids_remain_structured_errors_with_real_repository(
    tools: dict[str, Any]
) -> None:
    for name, field in (
        ("get_competition", "competition_id"),
        ("list_competition_editions", "competition_id"),
        ("get_competition_edition", "edition_id"),
        ("list_edition_tracks", "edition_id"),
        ("get_competition_track", "track_id"),
    ):
        _assert_error(tools[name].execute({field: "   "}), ToolErrorCode.INVALID_INPUT)


def test_real_nested_domain_values_serialize_without_artifact_data(
    repository: CompetitionRepository, tools: dict[str, Any]
) -> None:
    editions = repository.list_editions()
    with_source = [edition for edition in editions if edition.source is not None]
    with_time = [
        edition for edition in editions
        if edition.registration_window is not None
        or edition.competition_window is not None
    ]
    assert with_source, "Real dataset should exercise nested SourceMetadata"
    assert with_time, "Real dataset should exercise TimeWindow JSON"

    source_result = tools["get_competition_edition"].execute(
        {"edition_id": with_source[0].id}
    )
    source_json = _assert_success(source_result)["data"]["edition"]["source"]
    assert isinstance(source_json["source_url"], str)
    assert isinstance(source_json["source_type"], str)
    assert isinstance(source_json["verification_status"], str)
    assert datetime.fromisoformat(source_json["observed_at"].replace("Z", "+00:00")).utcoffset() is not None

    for edition in with_time:
        result = tools["get_competition_edition"].execute(
            {"edition_id": edition.id}
        )
        serialized = _assert_success(result)["data"]["edition"]
        for field in ("registration_window", "competition_window"):
            window = getattr(edition, field)
            if window is None:
                assert serialized[field] is None
                continue
            for endpoint in ("start_at", "end_at"):
                value = getattr(window, endpoint)
                encoded = serialized[field][endpoint]
                if value is None:
                    assert encoded is None
                else:
                    parsed = datetime.fromisoformat(encoded.replace("Z", "+00:00"))
                    assert parsed == value
                    assert parsed.utcoffset() == value.utcoffset()

    assert any(competition.short_name is None for competition in repository.list_competitions())
    no_short_name = next(competition for competition in repository.list_competitions()
                         if competition.short_name is None)
    result = tools["get_competition"].execute({"competition_id": no_short_name.id})
    assert _assert_success(result)["data"]["competition"]["short_name"] is None


def test_real_tools_are_read_only_and_repeatable(
    repository: CompetitionRepository, tools: dict[str, Any]
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

    list_tool = tools["list_competitions"]
    get_tool = tools["get_competition"]
    first_list = _json_result(list_tool.execute({}))
    first_get = _json_result(get_tool.execute({"competition_id": competitions[0].id}))
    assert _json_result(list_tool.execute({})) == first_list
    assert _json_result(get_tool.execute({"competition_id": competitions[0].id})) == first_get

    for competition in competitions:
        tools["list_competition_editions"].execute({"competition_id": competition.id})
    for edition in editions:
        tools["list_edition_tracks"].execute({"edition_id": edition.id})

    assert repository.list_competitions() == competitions
    assert repository.list_editions() == editions
    for competition_id, expected in editions_by_parent.items():
        assert repository.list_editions_by_competition(competition_id) == expected
    for edition_id, expected in tracks_by_parent.items():
        assert repository.list_tracks(edition_id) == expected
