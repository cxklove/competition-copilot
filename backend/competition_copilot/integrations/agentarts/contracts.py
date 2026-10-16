"""Transport envelopes reuse core contracts; no platform business state."""

from enum import StrEnum
from typing import Self

from pydantic import model_validator

from competition_copilot.agents.contracts import (
    AgentContract,
    AgentRequest,
    AgentResponse,
)
from competition_copilot.agents.graph import GraphInput
from competition_copilot.agents.human_contracts import (
    ApprovalResponse,
    ClarificationResponse,
    HumanMessage,
)
from competition_copilot.domain.digital_twin import StableId

HumanReply = ClarificationResponse | ApprovalResponse | HumanMessage


class AgentArtsInvocationEnvelope(AgentContract):
    """Either a new request or an opaque trusted-continuation ref and one reply.

    No client-supplied AgentState, GraphInput, authority or execution context.
    References are lookup keys, not authorization; the injected application
    boundary must authorize their resolution for the calling integration.
    """
    request: AgentRequest | None = None
    continuation_ref: StableId | None = None
    clarification: ClarificationResponse | None = None
    approval: ApprovalResponse | None = None
    message: HumanMessage | None = None

    @model_validator(mode="after")
    def known_shape(self) -> Self:
        replies = sum(v is not None for v in (self.clarification, self.approval, self.message))
        if self.request is not None:
            if self.continuation_ref is not None or replies:
                raise ValueError("New request cannot contain a continuation/reply")
        elif self.continuation_ref is None or replies != 1:
            raise ValueError("Resume requires a continuation reference and exactly one reply")
        return self

    @property
    def human_reply(self) -> HumanReply | None:
        return self.clarification or self.approval or self.message


class RuntimeErrorCode(StrEnum):
    INVALID_RUNTIME_PAYLOAD = "INVALID_RUNTIME_PAYLOAD"
    CORE_VALIDATION_ERROR = "CORE_VALIDATION_ERROR"
    CORE_EXECUTION_ERROR = "CORE_EXECUTION_ERROR"
    RUNTIME_DEPENDENCY_ERROR = "RUNTIME_DEPENDENCY_ERROR"


class RuntimeError(AgentContract):
    code: RuntimeErrorCode
    message: StableId


class AgentArtsInvocationResult(AgentContract):
    response: AgentResponse | None = None
    continuation: GraphInput | None = None
    error: RuntimeError | None = None

    @model_validator(mode="after")
    def exclusive_result(self) -> Self:
        if (self.response is None) == (self.error is None):
            raise ValueError("Return either core response or runtime error")
        pending = self.response is not None and self.response.outcome in (
            "NEEDS_CLARIFICATION", "WAITING_FOR_APPROVAL")
        if pending != (self.continuation is not None):
            raise ValueError("Only pending core interactions return continuation state")
        return self
