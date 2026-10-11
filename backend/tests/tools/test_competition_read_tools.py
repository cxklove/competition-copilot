"""P4.2 read tools use only the Repository contract and Domain models."""

import pytest

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.repositories import (
    CompetitionRepository,
    RepositoryEntityNotFoundError,
)
from competition_copilot.tools import (
    GetCompetitionEditionTool,
    GetCompetitionTool,
    GetCompetitionTrackTool,
    ListCompetitionEditionsTool,
    ListCompetitionsTool,
    ListEditionTracksTool,
    ToolErrorCode,
)


class FakeCompetitionRepository(CompetitionRepository):
    def __init__(self) -> None:
        self.competitions = [
            Competition(id="zeta", name="Zeta"),
            Competition(id="alpha", name="Alpha"),
        ]
        self.editions = [
            CompetitionEdition(
                id="zeta-2027", competition_id="zeta", year=2027, name="2027"
            ),
            CompetitionEdition(
                id="zeta-2026", competition_id="zeta", year=2026, name="2026"
            ),
        ]
        self.tracks = [
            CompetitionTrack(id="track-z", edition_id="zeta-2027", name="Z"),
            CompetitionTrack(id="track-a", edition_id="zeta-2027", name="A"),
        ]
        self.calls: list[tuple[str, str | None]] = []

    def list_competitions(self) -> list[Competition]:
        self.calls.append(("list_competitions", None))
        return list(self.competitions)

    def get_competition(self, competition_id: str) -> Competition:
        self.calls.append(("get_competition", competition_id))
        for competition in self.competitions:
            if competition.id == competition_id:
                return competition
        raise RepositoryEntityNotFoundError("competition", competition_id)

    def list_editions(self) -> list[CompetitionEdition]:
        self.calls.append(("list_editions", None))
        return list(self.editions)

    def get_edition(self, edition_id: str) -> CompetitionEdition:
        self.calls.append(("get_edition", edition_id))
        for edition in self.editions:
            if edition.id == edition_id:
                return edition
        raise RepositoryEntityNotFoundError("edition", edition_id)

    def list_editions_by_competition(
        self, competition_id: str
    ) -> list[CompetitionEdition]:
        self.calls.append(("list_editions_by_competition", competition_id))
        if competition_id not in {item.id for item in self.competitions}:
            raise RepositoryEntityNotFoundError("competition", competition_id)
        return [e for e in self.editions if e.competition_id == competition_id]

    def list_tracks(self, edition_id: str) -> list[CompetitionTrack]:
        self.calls.append(("list_tracks", edition_id))
        if edition_id not in {item.id for item in self.editions}:
            raise RepositoryEntityNotFoundError("edition", edition_id)
        return [track for track in self.tracks if track.edition_id == edition_id]

    def get_track(self, track_id: str) -> CompetitionTrack:
        self.calls.append(("get_track", track_id))
        for track in self.tracks:
            if track.id == track_id:
                return track
        raise RepositoryEntityNotFoundError("track", track_id)


def test_list_competitions_preserves_repository_order_and_empty_success() -> None:
    repository = FakeCompetitionRepository()
    result = ListCompetitionsTool(repository).execute({})

    assert result.success is True
    assert result.data is not None
    assert result.data.competitions == repository.competitions
    assert [item.id for item in result.data.competitions] == ["zeta", "alpha"]
    assert repository.calls == [("list_competitions", None)]

    repository.competitions = []
    empty = ListCompetitionsTool(repository).execute({})
    assert empty.success is True
    assert empty.data is not None
    assert empty.data.competitions == []


@pytest.mark.parametrize(
    ("tool_type", "input_data", "method", "expected_id", "field"),
    [
        (GetCompetitionTool, {"competition_id": "zeta"}, "get_competition", "zeta", "competition"),
        (
            ListCompetitionEditionsTool,
            {"competition_id": "zeta"},
            "list_editions_by_competition",
            "zeta",
            "editions",
        ),
        (GetCompetitionEditionTool, {"edition_id": "zeta-2027"}, "get_edition", "zeta-2027", "edition"),
        (ListEditionTracksTool, {"edition_id": "zeta-2027"}, "list_tracks", "zeta-2027", "tracks"),
        (GetCompetitionTrackTool, {"track_id": "track-z"}, "get_track", "track-z", "track"),
    ],
)
def test_exact_repository_method_mapping_and_structured_output(
    tool_type: type,
    input_data: dict[str, str],
    method: str,
    expected_id: str,
    field: str,
) -> None:
    repository = FakeCompetitionRepository()
    result = tool_type(repository).execute(input_data)

    assert result.success is True
    assert result.error is None
    assert result.data is not None
    assert getattr(result.data, field)
    assert repository.calls == [(method, expected_id)]
    assert type(result).model_validate_json(result.model_dump_json()) == result


def test_child_lists_preserve_order_and_distinguish_empty_from_unknown() -> None:
    repository = FakeCompetitionRepository()
    editions = ListCompetitionEditionsTool(repository)
    tracks = ListEditionTracksTool(repository)

    zeta = editions.execute({"competition_id": "zeta"})
    alpha = editions.execute({"competition_id": "alpha"})
    many = tracks.execute({"edition_id": "zeta-2027"})
    zero = tracks.execute({"edition_id": "zeta-2026"})

    assert zeta.success and zeta.data is not None
    assert [item.id for item in zeta.data.editions] == ["zeta-2027", "zeta-2026"]
    assert alpha.success and alpha.data is not None and alpha.data.editions == []
    assert many.success and many.data is not None
    assert [item.id for item in many.data.tracks] == ["track-z", "track-a"]
    assert zero.success and zero.data is not None and zero.data.tracks == []

    for tool, request in [
        (editions, {"competition_id": "unknown"}),
        (tracks, {"edition_id": "unknown"}),
    ]:
        result = tool.execute(request)
        assert result.success is False
        assert result.data is None
        assert result.error is not None
        assert result.error.code is ToolErrorCode.NOT_FOUND


@pytest.mark.parametrize(
    ("tool_type", "field"),
    [
        (GetCompetitionTool, "competition_id"),
        (ListCompetitionEditionsTool, "competition_id"),
        (GetCompetitionEditionTool, "edition_id"),
        (ListEditionTracksTool, "edition_id"),
        (GetCompetitionTrackTool, "track_id"),
    ],
)
@pytest.mark.parametrize("bad_value", ["", "   ", 42])
def test_invalid_id_does_not_call_repository(
    tool_type: type, field: str, bad_value: object
) -> None:
    repository = FakeCompetitionRepository()
    result = tool_type(repository).execute({field: bad_value})

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ToolErrorCode.INVALID_INPUT
    assert repository.calls == []


@pytest.mark.parametrize(
    "tool_type",
    [
        GetCompetitionTool,
        ListCompetitionEditionsTool,
        GetCompetitionEditionTool,
        ListEditionTracksTool,
        GetCompetitionTrackTool,
    ],
)
def test_missing_id_is_invalid_without_repository_call(tool_type: type) -> None:
    repository = FakeCompetitionRepository()
    result = tool_type(repository).execute({})

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ToolErrorCode.INVALID_INPUT
    assert repository.calls == []


@pytest.mark.parametrize(
    ("tool_type", "input_data"),
    [
        (GetCompetitionTool, {"competition_id": "unknown"}),
        (GetCompetitionEditionTool, {"edition_id": "unknown"}),
        (GetCompetitionTrackTool, {"track_id": "unknown"}),
    ],
)
def test_get_unknown_maps_to_tool_not_found(
    tool_type: type, input_data: dict[str, str]
) -> None:
    result = tool_type(FakeCompetitionRepository()).execute(input_data)

    assert result.success is False
    assert result.data is None
    assert result.error is not None
    assert result.error.code is ToolErrorCode.NOT_FOUND
    assert "RepositoryEntityNotFoundError" not in result.model_dump_json()


def test_cross_tool_domain_consistency() -> None:
    repository = FakeCompetitionRepository()
    competitions = ListCompetitionsTool(repository).execute({})
    editions = ListCompetitionEditionsTool(repository).execute({"competition_id": "zeta"})
    tracks = ListEditionTracksTool(repository).execute({"edition_id": "zeta-2027"})

    assert competitions.data is not None
    assert editions.data is not None
    assert tracks.data is not None
    assert GetCompetitionTool(repository).execute({"competition_id": "zeta"}).data.competition == competitions.data.competitions[0]
    assert GetCompetitionEditionTool(repository).execute({"edition_id": "zeta-2027"}).data.edition == editions.data.editions[0]
    assert GetCompetitionTrackTool(repository).execute({"track_id": "track-z"}).data.track == tracks.data.tracks[0]


def test_six_tools_have_unique_stable_metadata_and_valid_schemas() -> None:
    repository = FakeCompetitionRepository()
    tools = [
        ListCompetitionsTool(repository),
        GetCompetitionTool(repository),
        ListCompetitionEditionsTool(repository),
        GetCompetitionEditionTool(repository),
        ListEditionTracksTool(repository),
        GetCompetitionTrackTool(repository),
    ]
    names = [tool.metadata.name for tool in tools]

    assert names == [
        "list_competitions",
        "get_competition",
        "list_competition_editions",
        "get_competition_edition",
        "list_edition_tracks",
        "get_competition_track",
    ]
    assert len(set(names)) == len(names)
    for tool in tools:
        assert tool.metadata.description.strip()
        assert tool.metadata.input_schema["type"] == "object"
        assert "success" in tool.metadata.output_schema["properties"]
        assert "data" in tool.metadata.output_schema["properties"]
        assert "error" in tool.metadata.output_schema["properties"]


def test_list_competitions_rejects_nonempty_input_without_repository_call() -> None:
    repository = FakeCompetitionRepository()
    result = ListCompetitionsTool(repository).execute({"query": "math"})

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ToolErrorCode.INVALID_INPUT
    assert repository.calls == []


@pytest.mark.parametrize(
    ("tool_type", "input_data", "method"),
    [
        (ListCompetitionsTool, {}, "list_competitions"),
        (GetCompetitionTool, {"competition_id": "zeta"}, "get_competition"),
        (
            ListCompetitionEditionsTool,
            {"competition_id": "zeta"},
            "list_editions_by_competition",
        ),
        (GetCompetitionEditionTool, {"edition_id": "zeta-2027"}, "get_edition"),
        (ListEditionTracksTool, {"edition_id": "zeta-2027"}, "list_tracks"),
        (GetCompetitionTrackTool, {"track_id": "track-z"}, "get_track"),
    ],
)
def test_unexpected_repository_error_uses_existing_internal_error_contract(
    monkeypatch: pytest.MonkeyPatch,
    tool_type: type,
    input_data: dict[str, str],
    method: str,
) -> None:
    repository = FakeCompetitionRepository()

    def fail(*_args: object) -> object:
        raise KeyError("private repository detail")

    monkeypatch.setattr(repository, method, fail)
    result = tool_type(repository).execute(input_data)

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ToolErrorCode.INTERNAL_ERROR
    assert "private repository detail" not in result.model_dump_json()
