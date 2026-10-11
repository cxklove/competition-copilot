"""P4.3 JSON and error boundary checks for every Competition read tool."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

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
from competition_copilot.domain.temporal import TimeWindow
from competition_copilot.repositories import RepositoryEntityNotFoundError
from competition_copilot.tools import (
    GetCompetitionEditionTool,
    GetCompetitionTool,
    GetCompetitionTrackTool,
    ListCompetitionEditionsTool,
    ListCompetitionsTool,
    ListEditionTracksTool,
    ToolErrorCode,
)


class MemoryRepository:
    """Keep Tool serialization tests independent of all P2/P3 artifacts."""

    def __init__(self) -> None:
        source = SourceMetadata(
            source_url="https://example.org/official/2026",
            source_type=SourceType.OFFICIAL,
            observed_at=datetime(2026, 1, 2, 12, 30, tzinfo=timezone.utc),
            verification_status=VerificationStatus.VERIFIED,
        )
        start = datetime(2026, 3, 31, 16, 0, tzinfo=timezone(timedelta(hours=8)))
        end = datetime(2026, 4, 2, 18, 0, tzinfo=timezone(timedelta(hours=8)))
        self.competitions = [
            Competition(id="zeta", name="Zeta", official_url="https://example.org"),
            Competition(id="alpha", name="Alpha"),
        ]
        self.editions = [
            CompetitionEdition(
                id="zeta-2026",
                competition_id="zeta",
                year=2026,
                name="Zeta 2026",
                registration_window=TimeWindow(start_at=start, end_at=None),
                competition_window=TimeWindow(start_at=start, end_at=end),
                source=source,
            ),
            CompetitionEdition(
                id="zeta-empty",
                competition_id="zeta",
                year=2027,
                name="Zeta Empty",
            ),
        ]
        self.tracks = [
            CompetitionTrack(
                id="track-z", edition_id="zeta-2026", name="Track Z", source=source
            ),
            CompetitionTrack(id="track-a", edition_id="zeta-2026", name="Track A"),
        ]
        self.calls: list[tuple[str, str | None]] = []

    def list_competitions(self) -> list[Competition]:
        self.calls.append(("list_competitions", None))
        return list(self.competitions)

    def get_competition(self, competition_id: str) -> Competition:
        self.calls.append(("get_competition", competition_id))
        for item in self.competitions:
            if item.id == competition_id:
                return item
        raise RepositoryEntityNotFoundError("competition", competition_id)

    def list_editions(self) -> list[CompetitionEdition]:
        self.calls.append(("list_editions", None))
        return list(self.editions)

    def get_edition(self, edition_id: str) -> CompetitionEdition:
        self.calls.append(("get_edition", edition_id))
        for item in self.editions:
            if item.id == edition_id:
                return item
        raise RepositoryEntityNotFoundError("edition", edition_id)

    def list_editions_by_competition(
        self, competition_id: str
    ) -> list[CompetitionEdition]:
        self.calls.append(("list_editions_by_competition", competition_id))
        if competition_id not in {item.id for item in self.competitions}:
            raise RepositoryEntityNotFoundError("competition", competition_id)
        return [item for item in self.editions if item.competition_id == competition_id]

    def list_tracks(self, edition_id: str) -> list[CompetitionTrack]:
        self.calls.append(("list_tracks", edition_id))
        if edition_id not in {item.id for item in self.editions}:
            raise RepositoryEntityNotFoundError("edition", edition_id)
        return [item for item in self.tracks if item.edition_id == edition_id]

    def get_track(self, track_id: str) -> CompetitionTrack:
        self.calls.append(("get_track", track_id))
        for item in self.tracks:
            if item.id == track_id:
                return item
        raise RepositoryEntityNotFoundError("track", track_id)


TOOL_CASES = [
    (ListCompetitionsTool, {}, "competitions"),
    (GetCompetitionTool, {"competition_id": "zeta"}, "competition"),
    (ListCompetitionEditionsTool, {"competition_id": "zeta"}, "editions"),
    (GetCompetitionEditionTool, {"edition_id": "zeta-2026"}, "edition"),
    (ListEditionTracksTool, {"edition_id": "zeta-2026"}, "tracks"),
    (GetCompetitionTrackTool, {"track_id": "track-z"}, "track"),
]


def assert_json_primitives(value: object) -> None:
    if value is None or type(value) in (str, int, float, bool):
        return
    if isinstance(value, list):
        for item in value:
            assert_json_primitives(item)
        return
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value)
        for item in value.values():
            assert_json_primitives(item)
        return
    pytest.fail(f"Non-JSON value: {type(value).__name__}")


@pytest.mark.parametrize(("tool_type", "input_data", "payload_field"), TOOL_CASES)
def test_all_six_success_results_have_one_json_shape_and_round_trip(
    tool_type: type, input_data: dict[str, str], payload_field: str
) -> None:
    result = tool_type(MemoryRepository()).execute(input_data)
    assert result.success is True
    assert result.data is not None
    assert result.error is None
    assert getattr(result.data, payload_field)

    dumped = result.model_dump(mode="json")
    assert set(dumped) == {"success", "data", "error"}
    assert dumped["success"] is True
    assert dumped["error"] is None
    assert_json_primitives(dumped)
    assert json.loads(result.model_dump_json()) == dumped
    assert type(result).model_validate_json(result.model_dump_json()) == result


def test_empty_lists_remain_explicit_successful_json_arrays() -> None:
    repository = MemoryRepository()
    repository.competitions = []
    all_competitions = ListCompetitionsTool(repository).execute({})
    assert all_competitions.model_dump(mode="json")["data"]["competitions"] == []
    assert all_competitions.success is True

    repository = MemoryRepository()
    no_editions = ListCompetitionEditionsTool(repository).execute(
        {"competition_id": "alpha"}
    )
    no_tracks = ListEditionTracksTool(repository).execute(
        {"edition_id": "zeta-empty"}
    )
    assert no_editions.success is True
    assert no_editions.model_dump(mode="json")["data"]["editions"] == []
    assert no_tracks.success is True
    assert no_tracks.model_dump(mode="json")["data"]["tracks"] == []


def test_list_competitions_invalid_input_is_serializable_without_repository_call() -> None:
    repository = MemoryRepository()
    result = ListCompetitionsTool(repository).execute({"unexpected": "value"})

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ToolErrorCode.INVALID_INPUT
    assert repository.calls == []
    assert_json_primitives(result.model_dump(mode="json"))
    assert type(result).model_validate_json(result.model_dump_json()) == result
    assert "ValidationError" not in result.model_dump_json()


def test_nested_aware_datetimes_partial_window_source_url_and_enums() -> None:
    repository = MemoryRepository()
    edition_result = GetCompetitionEditionTool(repository).execute(
        {"edition_id": "zeta-2026"}
    )
    edition = edition_result.model_dump(mode="json")["data"]["edition"]
    registration = edition["registration_window"]
    competition = edition["competition_window"]

    assert registration == {"start_at": "2026-03-31T16:00:00+08:00", "end_at": None}
    assert competition["start_at"] == "2026-03-31T16:00:00+08:00"
    assert competition["end_at"] == "2026-04-02T18:00:00+08:00"
    assert edition["source"]["source_url"] == "https://example.org/official/2026"
    assert edition["source"]["source_type"] == "official"
    assert edition["source"]["verification_status"] == "verified"
    assert edition["source"]["observed_at"] == "2026-01-02T12:30:00Z"
    assert_json_primitives(edition_result.model_dump(mode="json"))

    track = GetCompetitionTrackTool(repository).execute(
        {"track_id": "track-z"}
    ).model_dump(mode="json")["data"]["track"]
    assert track["source"] == edition["source"]
    assert "raw_payload" not in json.dumps(edition_result.model_dump(mode="json"))

    competition_result = GetCompetitionTool(repository).execute(
        {"competition_id": "zeta"}
    )
    competition_url = competition_result.model_dump(mode="json")["data"][
        "competition"
    ]["official_url"]
    assert isinstance(competition_url, str)
    assert competition_url.startswith("https://example.org")
    assert competition_result.model_dump(mode="json")["data"]["competition"]["short_name"] is None


@pytest.mark.parametrize(
    ("tool_type", "input_data"),
    [(tool_type, input_data) for tool_type, input_data, _ in TOOL_CASES[1:]],
)
def test_invalid_input_is_serializable_and_never_calls_repository(
    tool_type: type, input_data: dict[str, str]
) -> None:
    id_field = next(iter(input_data))
    for invalid in ("", "   ", 42, None):
        repository = MemoryRepository()
        result = tool_type(repository).execute({id_field: invalid})
        assert result.success is False
        assert result.data is None
        assert result.error is not None
        assert result.error.code is ToolErrorCode.INVALID_INPUT
        assert repository.calls == []
        assert_json_primitives(result.model_dump(mode="json"))
        assert type(result).model_validate_json(result.model_dump_json()) == result
        assert "ValidationError" not in result.model_dump_json()

    repository = MemoryRepository()
    missing = tool_type(repository).execute({})
    assert missing.error is not None
    assert missing.error.code is ToolErrorCode.INVALID_INPUT
    assert repository.calls == []


@pytest.mark.parametrize(
    ("tool_type", "input_data"),
    [(tool_type, input_data) for tool_type, input_data, _ in TOOL_CASES[1:]],
)
def test_not_found_error_is_stable_json_without_exception_leakage(
    tool_type: type, input_data: dict[str, str]
) -> None:
    id_field = next(iter(input_data))
    result = tool_type(MemoryRepository()).execute({id_field: "unknown"})
    dumped = result.model_dump(mode="json")

    assert dumped["success"] is False
    assert dumped["data"] is None
    assert dumped["error"]["code"] == "NOT_FOUND"
    assert dumped["error"]["message"]
    assert_json_primitives(dumped)
    assert type(result).model_validate_json(result.model_dump_json()) == result
    assert "RepositoryEntityNotFoundError" not in result.model_dump_json()


@pytest.mark.parametrize(("tool_type", "input_data", "method"), [
    (ListCompetitionsTool, {}, "list_competitions"),
    (GetCompetitionTool, {"competition_id": "zeta"}, "get_competition"),
    (ListCompetitionEditionsTool, {"competition_id": "zeta"}, "list_editions_by_competition"),
    (GetCompetitionEditionTool, {"edition_id": "zeta-2026"}, "get_edition"),
    (ListEditionTracksTool, {"edition_id": "zeta-2026"}, "list_tracks"),
    (GetCompetitionTrackTool, {"track_id": "track-z"}, "get_track"),
])
def test_unexpected_errors_use_internal_error_without_details(
    monkeypatch: pytest.MonkeyPatch,
    tool_type: type,
    input_data: dict[str, str],
    method: str,
) -> None:
    repository = MemoryRepository()

    def fail(*_args: object) -> object:
        raise RuntimeError("private path and implementation detail")

    monkeypatch.setattr(repository, method, fail)
    result = tool_type(repository).execute(input_data)
    dumped = result.model_dump(mode="json")
    assert dumped["error"]["code"] == "INTERNAL_ERROR"
    assert dumped["success"] is False and dumped["data"] is None
    assert "private path" not in result.model_dump_json()
    assert "Traceback" not in result.model_dump_json()
    assert type(result).model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize(("tool_type", "input_data", "payload_field"), TOOL_CASES)
def test_metadata_schemas_have_concrete_output_and_no_artifact_details(
    tool_type: type, input_data: dict[str, str], payload_field: str
) -> None:
    del input_data
    metadata = tool_type(MemoryRepository()).metadata
    input_schema = metadata.input_schema
    output_schema = metadata.output_schema
    assert metadata.name and metadata.description.strip()
    assert input_schema["type"] == "object"
    data_schema = output_schema["properties"]["data"]
    refs = [branch["$ref"] for branch in data_schema["anyOf"] if "$ref" in branch]
    assert len(refs) == 1
    output_definition = refs[0].removeprefix("#/$defs/")
    assert payload_field in output_schema["$defs"][output_definition]["properties"]
    assert set(output_schema["properties"]) == {"success", "data", "error"}
    assert_json_primitives(input_schema)
    assert_json_primitives(output_schema)
    forbidden = (
        "JsonSeedCompetitionRepository",
        "CompetitionSeedEnvelope",
        "RawCompetitionData",
        "HumanReviewManifest",
        "raw_payload",
        "raw_fixture_path",
    )
    schema_text = json.dumps((input_schema, output_schema))
    assert not any(name in schema_text for name in forbidden)


def test_serialized_lists_keep_repository_order() -> None:
    repository = MemoryRepository()
    competitions = ListCompetitionsTool(repository).execute({})
    tracks = ListEditionTracksTool(repository).execute({"edition_id": "zeta-2026"})
    assert [item["id"] for item in competitions.model_dump(mode="json")["data"]["competitions"]] == ["zeta", "alpha"]
    assert [item["id"] for item in tracks.model_dump(mode="json")["data"]["tracks"]] == ["track-z", "track-a"]


def test_result_rejects_all_ambiguous_success_error_states() -> None:
    output_type = GetCompetitionTool.metadata.output_model
    competition = MemoryRepository().competitions[0].model_dump(mode="json")
    for invalid in (
        {"success": True, "data": None, "error": None},
        {"success": True, "data": {"competition": competition}, "error": {"code": "NOT_FOUND", "message": "missing"}},
        {"success": False, "data": {"competition": competition}, "error": {"code": "NOT_FOUND", "message": "missing"}},
        {"success": False, "data": None, "error": None},
    ):
        with pytest.raises(ValidationError):
            output_type.model_validate(invalid)


def test_error_codes_are_machine_readable_strings() -> None:
    assert {code.value for code in ToolErrorCode} == {
        "INVALID_INPUT",
        "NOT_FOUND",
        "INTERNAL_ERROR",
    }
