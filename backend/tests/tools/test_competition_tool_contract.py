"""P4.1 Tool contract checks using an in-memory Repository fake."""

import pytest
from pydantic import ValidationError

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
    ListEditionTracksInput,
    ListEditionTracksOutput,
    ListEditionTracksTool,
    Tool,
    ToolError,
    ToolErrorCode,
    ToolResult,
)


class FakeCompetitionRepository(CompetitionRepository):
    def __init__(self) -> None:
        self.competition = Competition(id="math", name="Mathematics")
        self.editions = {
            "math-tracked": CompetitionEdition(
                id="math-tracked", competition_id="math", year=2026, name="Tracked"
            ),
            "math-empty": CompetitionEdition(
                id="math-empty", competition_id="math", year=2027, name="Empty"
            ),
        }
        self.track = CompetitionTrack(
            id="math-track-a", edition_id="math-tracked", name="Track A"
        )
        self.track_calls = 0

    def list_competitions(self) -> list[Competition]:
        return [self.competition.model_copy(deep=True)]

    def get_competition(self, competition_id: str) -> Competition:
        if competition_id != self.competition.id:
            raise RepositoryEntityNotFoundError("competition", competition_id)
        return self.competition.model_copy(deep=True)

    def list_editions(self) -> list[CompetitionEdition]:
        return [edition.model_copy(deep=True) for edition in self.editions.values()]

    def get_edition(self, edition_id: str) -> CompetitionEdition:
        if edition_id not in self.editions:
            raise RepositoryEntityNotFoundError("edition", edition_id)
        return self.editions[edition_id].model_copy(deep=True)

    def list_editions_by_competition(
        self, competition_id: str
    ) -> list[CompetitionEdition]:
        self.get_competition(competition_id)
        return self.list_editions()

    def list_tracks(self, edition_id: str) -> list[CompetitionTrack]:
        self.track_calls += 1
        self.get_edition(edition_id)
        if edition_id == self.track.edition_id:
            return [self.track.model_copy(deep=True)]
        return []

    def get_track(self, track_id: str) -> CompetitionTrack:
        if track_id != self.track.id:
            raise RepositoryEntityNotFoundError("track", track_id)
        return self.track.model_copy(deep=True)


def test_tool_metadata_exposes_stable_model_schemas() -> None:
    repository = FakeCompetitionRepository()
    tool: Tool[ListEditionTracksOutput] = ListEditionTracksTool(repository)

    assert tool.metadata.name == "list_edition_tracks"
    assert tool.metadata.description
    assert tool.metadata.input_model is ListEditionTracksInput
    assert tool.metadata.output_model is ToolResult[ListEditionTracksOutput]
    assert tool.metadata.input_schema == tool.metadata.input_schema
    assert tool.metadata.output_schema == tool.metadata.output_schema
    assert "edition_id" in tool.metadata.input_schema["properties"]
    assert "success" in tool.metadata.output_schema["properties"]
    assert "data" in tool.metadata.output_schema["properties"]
    assert "error" in tool.metadata.output_schema["properties"]


def test_valid_input_returns_structured_repeatable_domain_output() -> None:
    repository = FakeCompetitionRepository()
    tool = ListEditionTracksTool(repository)

    first = tool.execute({"edition_id": "math-tracked"})
    second = tool.execute(ListEditionTracksInput(edition_id="math-tracked"))

    assert first == second
    assert first.success is True
    assert first.error is None
    assert first.data == ListEditionTracksOutput(tracks=[repository.track])
    assert isinstance(first.data.tracks[0], CompetitionTrack)
    assert ToolResult[ListEditionTracksOutput].model_validate_json(
        first.model_dump_json()
    ) == first


@pytest.mark.parametrize(
    "input_data",
    [
        {"edition_id": ""},
        {"edition_id": "   "},
        {"edition_id": 42},
        {},
        {"edition_id": "math-tracked", "query": "guess"},
        "math-tracked",
    ],
)
def test_invalid_input_returns_error_without_repository_call(
    input_data: object,
) -> None:
    repository = FakeCompetitionRepository()
    result = ListEditionTracksTool(repository).execute(input_data)

    assert result.success is False
    assert result.data is None
    assert result.error is not None
    assert result.error.code is ToolErrorCode.INVALID_INPUT
    assert repository.track_calls == 0


def test_unknown_edition_maps_repository_not_found_to_tool_error() -> None:
    result = ListEditionTracksTool(FakeCompetitionRepository()).execute(
        {"edition_id": "unknown"}
    )

    assert result.success is False
    assert result.data is None
    assert result.error is not None
    assert result.error.code is ToolErrorCode.NOT_FOUND
    assert "RepositoryEntityNotFoundError" not in result.model_dump_json()


def test_existing_zero_track_edition_is_successful_empty_list() -> None:
    result = ListEditionTracksTool(FakeCompetitionRepository()).execute(
        {"edition_id": "math-empty"}
    )

    assert result.success is True
    assert result.error is None
    assert result.data == ListEditionTracksOutput(tracks=[])


def test_unexpected_repository_failure_is_not_leaked() -> None:
    class BrokenRepository(FakeCompetitionRepository):
        def list_tracks(self, edition_id: str) -> list[CompetitionTrack]:
            raise KeyError("private infrastructure detail")

    result = ListEditionTracksTool(BrokenRepository()).execute(
        {"edition_id": "math-tracked"}
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ToolErrorCode.INTERNAL_ERROR
    assert "private infrastructure detail" not in result.model_dump_json()


@pytest.mark.parametrize(
    "result_data",
    [
        {"success": True},
        {"success": False},
        {
            "success": True,
            "data": {"tracks": []},
            "error": {"code": "NOT_FOUND", "message": "Missing"},
        },
        {"success": False, "data": {"tracks": []}},
    ],
)
def test_tool_result_rejects_ambiguous_outcomes(result_data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ToolResult[ListEditionTracksOutput].model_validate(result_data)


def test_tool_error_codes_are_stable_and_structured() -> None:
    error = ToolError(code=ToolErrorCode.NOT_FOUND, message="Edition not found.")

    assert error.model_dump(mode="json") == {
        "code": "NOT_FOUND",
        "message": "Edition not found.",
    }
