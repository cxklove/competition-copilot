"""One read-only Competition Tool proving the P4.1 boundary."""

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from competition_copilot.domain.competition import CompetitionTrack
from competition_copilot.repositories import (
    CompetitionRepository,
    RepositoryEntityNotFoundError,
)
from competition_copilot.tools.contracts import (
    Tool,
    ToolError,
    ToolErrorCode,
    ToolMetadata,
    ToolResult,
)


class ListEditionTracksInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    edition_id: str = Field(strict=True)

    @field_validator("edition_id")
    @classmethod
    def require_nonblank_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("edition_id must not be blank")
        return value


class ListEditionTracksOutput(BaseModel):
    """Keep the list shape explicit while reusing the formal Domain model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tracks: list[CompetitionTrack]


class ListEditionTracksTool(Tool[ListEditionTracksOutput]):
    """Read one Edition's reviewed Track list without choosing or ranking."""

    metadata = ToolMetadata(
        name="list_edition_tracks",
        description="List the verified tracks of one competition edition.",
        input_model=ListEditionTracksInput,
        output_model=ToolResult[ListEditionTracksOutput],
    )

    def __init__(self, repository: CompetitionRepository) -> None:
        self._repository = repository

    def execute(self, input_data: object) -> ToolResult[ListEditionTracksOutput]:
        try:
            request = ListEditionTracksInput.model_validate(input_data)
        except ValidationError:
            return ToolResult[ListEditionTracksOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.INVALID_INPUT,
                    message="Invalid edition ID input.",
                ),
            )

        try:
            return ToolResult[ListEditionTracksOutput](
                success=True,
                data=ListEditionTracksOutput(
                    tracks=self._repository.list_tracks(request.edition_id)
                ),
            )
        except RepositoryEntityNotFoundError:
            return ToolResult[ListEditionTracksOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.NOT_FOUND,
                    message="Edition not found.",
                ),
            )
        except Exception:
            return ToolResult[ListEditionTracksOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.INTERNAL_ERROR,
                    message="Tool execution failed.",
                ),
            )
