"""Thin read projection Tool; all assembly belongs to Application."""

from pydantic import ValidationError

from competition_copilot.application.competition_detail import (
    CompetitionDetailProjection,
    CompetitionDetailQuery,
    CompetitionDetailReader,
)
from competition_copilot.repositories.competition import RepositoryEntityNotFoundError
from competition_copilot.tools.contracts import (
    Tool,
    ToolError,
    ToolErrorCode,
    ToolMetadata,
    ToolResult,
)


class GetCompetitionDetailsTool(Tool[CompetitionDetailProjection]):
    metadata = ToolMetadata(name="get_competition_details",
        description="Read authoritative exact-target competition details without decisions.",
        input_model=CompetitionDetailQuery, output_model=ToolResult[CompetitionDetailProjection])

    def __init__(self, reader: CompetitionDetailReader):
        self.reader = reader

    def execute(self, input_data: object) -> ToolResult[CompetitionDetailProjection]:
        try:
            query = CompetitionDetailQuery.model_validate(input_data)
        except ValidationError:
            return ToolResult(success=False, error=ToolError(
                code=ToolErrorCode.INVALID_INPUT, message="Invalid competition detail query."))
        try:
            return ToolResult(success=True, data=self.reader.read(query))
        except RepositoryEntityNotFoundError:
            return ToolResult(success=False, error=ToolError(
                code=ToolErrorCode.NOT_FOUND, message="Competition detail target not found."))
        except Exception:
            return ToolResult(success=False, error=ToolError(
                code=ToolErrorCode.INTERNAL_ERROR, message="Competition detail read failed."))
