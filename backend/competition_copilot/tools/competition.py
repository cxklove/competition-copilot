"""Read-only Competition, Edition, and Track tools."""

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
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


def _require_nonblank_id(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


class ListCompetitionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ListCompetitionsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    competitions: list[Competition]


class ListCompetitionsTool(Tool[ListCompetitionsOutput]):
    """List every official Competition in Repository order."""

    metadata = ToolMetadata(
        name="list_competitions",
        description="List all verified competitions.",
        input_model=ListCompetitionsInput,
        output_model=ToolResult[ListCompetitionsOutput],
    )

    def __init__(self, repository: CompetitionRepository) -> None:
        self._repository = repository

    def execute(self, input_data: object) -> ToolResult[ListCompetitionsOutput]:
        try:
            ListCompetitionsInput.model_validate(input_data)
        except ValidationError:
            return ToolResult[ListCompetitionsOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.INVALID_INPUT,
                    message="Invalid list competitions input.",
                ),
            )

        try:
            return ToolResult[ListCompetitionsOutput](
                success=True,
                data=ListCompetitionsOutput(
                    competitions=self._repository.list_competitions()
                ),
            )
        except RepositoryEntityNotFoundError:
            return ToolResult[ListCompetitionsOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.NOT_FOUND,
                    message="Competition not found.",
                ),
            )
        except Exception:
            return ToolResult[ListCompetitionsOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.INTERNAL_ERROR,
                    message="Tool execution failed.",
                ),
            )


class GetCompetitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    competition_id: str = Field(strict=True)

    @field_validator("competition_id")
    @classmethod
    def require_nonblank_id(cls, value: str) -> str:
        return _require_nonblank_id(value, "competition_id")


class GetCompetitionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    competition: Competition


class GetCompetitionTool(Tool[GetCompetitionOutput]):
    """Read one Competition by its exact ID."""

    metadata = ToolMetadata(
        name="get_competition",
        description="Get one verified competition by ID.",
        input_model=GetCompetitionInput,
        output_model=ToolResult[GetCompetitionOutput],
    )

    def __init__(self, repository: CompetitionRepository) -> None:
        self._repository = repository

    def execute(self, input_data: object) -> ToolResult[GetCompetitionOutput]:
        try:
            request = GetCompetitionInput.model_validate(input_data)
        except ValidationError:
            return ToolResult[GetCompetitionOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.INVALID_INPUT,
                    message="Invalid competition ID input.",
                ),
            )

        try:
            return ToolResult[GetCompetitionOutput](
                success=True,
                data=GetCompetitionOutput(
                    competition=self._repository.get_competition(
                        request.competition_id
                    )
                ),
            )
        except RepositoryEntityNotFoundError:
            return ToolResult[GetCompetitionOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.NOT_FOUND,
                    message="Competition not found.",
                ),
            )
        except Exception:
            return ToolResult[GetCompetitionOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.INTERNAL_ERROR,
                    message="Tool execution failed.",
                ),
            )


class ListCompetitionEditionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    competition_id: str = Field(strict=True)

    @field_validator("competition_id")
    @classmethod
    def require_nonblank_id(cls, value: str) -> str:
        return _require_nonblank_id(value, "competition_id")


class ListCompetitionEditionsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    editions: list[CompetitionEdition]


class ListCompetitionEditionsTool(Tool[ListCompetitionEditionsOutput]):
    """List the Editions of one Competition in Repository order."""

    metadata = ToolMetadata(
        name="list_competition_editions",
        description="List the editions of one verified competition.",
        input_model=ListCompetitionEditionsInput,
        output_model=ToolResult[ListCompetitionEditionsOutput],
    )

    def __init__(self, repository: CompetitionRepository) -> None:
        self._repository = repository

    def execute(self, input_data: object) -> ToolResult[ListCompetitionEditionsOutput]:
        try:
            request = ListCompetitionEditionsInput.model_validate(input_data)
        except ValidationError:
            return ToolResult[ListCompetitionEditionsOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.INVALID_INPUT,
                    message="Invalid competition ID input.",
                ),
            )

        try:
            return ToolResult[ListCompetitionEditionsOutput](
                success=True,
                data=ListCompetitionEditionsOutput(
                    editions=self._repository.list_editions_by_competition(
                        request.competition_id
                    )
                ),
            )
        except RepositoryEntityNotFoundError:
            return ToolResult[ListCompetitionEditionsOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.NOT_FOUND,
                    message="Competition not found.",
                ),
            )
        except Exception:
            return ToolResult[ListCompetitionEditionsOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.INTERNAL_ERROR,
                    message="Tool execution failed.",
                ),
            )


class GetCompetitionEditionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    edition_id: str = Field(strict=True)

    @field_validator("edition_id")
    @classmethod
    def require_nonblank_id(cls, value: str) -> str:
        return _require_nonblank_id(value, "edition_id")


class GetCompetitionEditionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    edition: CompetitionEdition


class GetCompetitionEditionTool(Tool[GetCompetitionEditionOutput]):
    """Read one Edition by its exact ID."""

    metadata = ToolMetadata(
        name="get_competition_edition",
        description="Get one verified competition edition by ID.",
        input_model=GetCompetitionEditionInput,
        output_model=ToolResult[GetCompetitionEditionOutput],
    )

    def __init__(self, repository: CompetitionRepository) -> None:
        self._repository = repository

    def execute(self, input_data: object) -> ToolResult[GetCompetitionEditionOutput]:
        try:
            request = GetCompetitionEditionInput.model_validate(input_data)
        except ValidationError:
            return ToolResult[GetCompetitionEditionOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.INVALID_INPUT,
                    message="Invalid edition ID input.",
                ),
            )

        try:
            return ToolResult[GetCompetitionEditionOutput](
                success=True,
                data=GetCompetitionEditionOutput(
                    edition=self._repository.get_edition(request.edition_id)
                ),
            )
        except RepositoryEntityNotFoundError:
            return ToolResult[GetCompetitionEditionOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.NOT_FOUND,
                    message="Edition not found.",
                ),
            )
        except Exception:
            return ToolResult[GetCompetitionEditionOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.INTERNAL_ERROR,
                    message="Tool execution failed.",
                ),
            )


class ListEditionTracksInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    edition_id: str = Field(strict=True)

    @field_validator("edition_id")
    @classmethod
    def require_nonblank_id(cls, value: str) -> str:
        return _require_nonblank_id(value, "edition_id")


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


class GetCompetitionTrackInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    track_id: str = Field(strict=True)

    @field_validator("track_id")
    @classmethod
    def require_nonblank_id(cls, value: str) -> str:
        return _require_nonblank_id(value, "track_id")


class GetCompetitionTrackOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    track: CompetitionTrack


class GetCompetitionTrackTool(Tool[GetCompetitionTrackOutput]):
    """Read one Track by its exact ID."""

    metadata = ToolMetadata(
        name="get_competition_track",
        description="Get one verified competition track by ID.",
        input_model=GetCompetitionTrackInput,
        output_model=ToolResult[GetCompetitionTrackOutput],
    )

    def __init__(self, repository: CompetitionRepository) -> None:
        self._repository = repository

    def execute(self, input_data: object) -> ToolResult[GetCompetitionTrackOutput]:
        try:
            request = GetCompetitionTrackInput.model_validate(input_data)
        except ValidationError:
            return ToolResult[GetCompetitionTrackOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.INVALID_INPUT,
                    message="Invalid track ID input.",
                ),
            )

        try:
            return ToolResult[GetCompetitionTrackOutput](
                success=True,
                data=GetCompetitionTrackOutput(
                    track=self._repository.get_track(request.track_id)
                ),
            )
        except RepositoryEntityNotFoundError:
            return ToolResult[GetCompetitionTrackOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.NOT_FOUND,
                    message="Track not found.",
                ),
            )
        except Exception:
            return ToolResult[GetCompetitionTrackOutput](
                success=False,
                error=ToolError(
                    code=ToolErrorCode.INTERNAL_ERROR,
                    message="Tool execution failed.",
                ),
            )
