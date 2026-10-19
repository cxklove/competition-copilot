"""Protocol-neutral tool contracts. Validation is syntax, never business authority."""

import json
from enum import StrEnum
from typing import Generic, Self, TypeVar

from pydantic import BaseModel, model_validator

from competition_copilot.agents.capabilities import AgentCapabilityResult
from competition_copilot.agents.contracts import (
    AgentContract,
    ReferenceKind,
    ResultReference,
)
from competition_copilot.domain.digital_twin import StableId

PayloadT = TypeVar("PayloadT", bound=BaseModel)


class McpToolInput(AgentContract, Generic[PayloadT]):
    """Caller-owned IDs plus unchanged capability payload; no session inference.

    arguments_ref and result_ref identify caller-managed invocation artifacts.
    Their shape does not prove existence or authorization. No AgentIntent input.
    """

    invocation_id: StableId
    source_request_id: StableId
    arguments_ref: ResultReference
    result_ref: ResultReference
    payload: PayloadT

    @model_validator(mode="after")
    def reference_kinds(self) -> Self:
        if self.arguments_ref.kind != ReferenceKind.CAPABILITY_ARGUMENTS:
            raise ValueError("Expected CAPABILITY_ARGUMENTS reference")
        if self.result_ref.kind != ReferenceKind.TOOL_RESULT:
            raise ValueError("Expected TOOL_RESULT reference")
        return self


class McpToolErrorCode(StrEnum):
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    MISSING_CONTEXT = "MISSING_CONTEXT"
    CAPABILITY_NOT_EXPOSED = "CAPABILITY_NOT_EXPOSED"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"


class McpToolError(AgentContract):
    """Safe category only; raw exception prose cannot enter this contract."""

    code: McpToolErrorCode


class McpToolResult(AgentContract):
    """Canonical receipt OR pre-invocation transport error, never new truth.

    A canonical ERROR remains in result.error. Domain negatives in a successful
    receipt remain successful. Wire isError mapping belongs to P13.3.
    """

    result: AgentCapabilityResult | None = None
    error: McpToolError | None = None

    @model_validator(mode="after")
    def one_outcome(self) -> Self:
        if (self.result is None) == (self.error is None):
            raise ValueError("Provide canonical result or transport error")
        return self


def canonical_schema(model: type[BaseModel], *, mode="validation") -> dict:
    """Fresh JSON-safe schema; sorting preserves field/array semantics."""
    return json.loads(json.dumps(
        model.model_json_schema(mode=mode), sort_keys=True, allow_nan=False,
    ))
