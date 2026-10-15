"""One-turn human replies; IDs/times and authenticated actor belong to caller."""

from typing import Protocol, Self

from pydantic import AwareDatetime, Field, model_validator

from competition_copilot.agents.contracts import (
    AgentContract,
    AgentIntent,
    ApprovalResponse,
    CapabilityInvocationRequest,
    ClarificationRequest,
    ContextField,
    ReferenceKind,
    ResultReference,
)
from competition_copilot.domain.digital_twin import StableId
from competition_copilot.domain.replanning import PlanReference
from competition_copilot.domain.student import StudentProfile


class ClarificationValues(AgentContract):
    competition_id: StableId | None = None
    edition_id: StableId | None = None
    track_id: StableId | None = None
    student: StudentProfile | None = None
    plan_ref: PlanReference | None = None
    intent: AgentIntent | None = None
    invocation: CapabilityInvocationRequest | None = None
    arguments_json: StableId | None = None

    @property
    def provided_fields(self) -> tuple[ContextField, ...]:
        names = {
            "competition_id": ContextField.COMPETITION, "edition_id": ContextField.EDITION,
            "track_id": ContextField.TRACK, "student": ContextField.STUDENT_PROFILE,
            "plan_ref": ContextField.PLAN, "intent": ContextField.INTENT,
            "invocation": ContextField.CAPABILITY_INVOCATION,
            "arguments_json": ContextField.CAPABILITY_ARGUMENTS,
        }
        return tuple(sorted((field for key, field in names.items()
                             if getattr(self, key) is not None), key=lambda f: f.value))


class ClarificationResponse(AgentContract):
    clarification_id: StableId
    source_request_id: StableId
    values: ClarificationValues
    submitted_at: AwareDatetime

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if not self.values.provided_fields:
            raise ValueError("Provide at least one requested clarification field")
        return self


class HumanMessage(AgentContract):
    interaction_id: StableId
    source_request_id: StableId
    text: StableId
    submitted_at: AwareDatetime


class ClarificationOption(AgentContract):
    """Caller-prepared read-capability choice; never model-created entity truth."""
    field: ContextField
    value: StableId
    label: StableId
    source_ref: ResultReference

    @model_validator(mode="after")
    def identity_only(self) -> Self:
        if self.field not in (ContextField.COMPETITION, ContextField.EDITION, ContextField.TRACK):
            raise ValueError("Language proposals only select existing target choices")
        if self.source_ref.kind not in (ReferenceKind.TOOL_RESULT, ReferenceKind.COMPETITION_RESULT):
            raise ValueError("Choices require caller-owned read result references")
        return self


class ClarificationSelection(AgentContract):
    field: ContextField
    value: StableId


class ClarificationResolutionProposal(AgentContract):
    clarification_id: StableId
    source_request_id: StableId
    selections: tuple[ClarificationSelection, ...]
    ambiguous: bool = Field(strict=True)


class HumanResponseInterpreter(Protocol):
    def clarify(self, message: HumanMessage, question: ClarificationRequest,
                options: tuple[ClarificationOption, ...]) -> ClarificationResolutionProposal:
        ...


class HumanResume(AgentContract):
    """Trusted runtime continuation command, not a browser authentication token."""
    clarification: ClarificationResponse | None = None
    approval: ApprovalResponse | None = None
    message: HumanMessage | None = None
    approved_by_ref: StableId | None = None
    current_plan: PlanReference | None = None
    executed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def exactly_one_reply(self) -> Self:
        if sum(v is not None for v in (self.clarification, self.approval, self.message)) != 1:
            raise ValueError("Submit exactly one structured or natural-language reply")
        return self
