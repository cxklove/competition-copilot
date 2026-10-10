"""Storage-independent contracts for structured, read-only tools."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, Protocol, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

OutputT = TypeVar("OutputT", bound=BaseModel)


class ToolErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ToolError(BaseModel):
    """Stable caller-facing failure without an infrastructure exception."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: ToolErrorCode
    message: str = Field(min_length=1)


class ToolResult(BaseModel, Generic[OutputT]):
    """Exactly one structured success payload or structured error."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    success: bool = Field(strict=True)
    data: OutputT | None = None
    error: ToolError | None = None

    @model_validator(mode="after")
    def require_one_outcome(self) -> Self:
        if self.success and (self.data is None or self.error is not None):
            raise ValueError("success requires data and forbids error")
        if not self.success and (self.data is not None or self.error is None):
            raise ValueError("failure requires error and forbids data")
        return self


@dataclass(frozen=True)
class ToolMetadata:
    """Model types expose Pydantic schemas without MCP-specific conversion."""

    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]

    @property
    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    @property
    def output_schema(self) -> dict[str, Any]:
        return self.output_model.model_json_schema()


class Tool(Protocol[OutputT]):
    """Validate untrusted input, then return a machine-readable result."""

    @property
    def metadata(self) -> ToolMetadata: ...

    def execute(self, input_data: object) -> ToolResult[OutputT]: ...
