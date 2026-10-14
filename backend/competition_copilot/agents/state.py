"""Immutable workflow snapshots; no transitions, reducers or execution engine."""

from typing import Self

from pydantic import Field, model_validator

from competition_copilot.agents.contracts import (
    AgentContract,
    AgentError,
    AgentIntent,
    AgentRequest,
    AgentResponse,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResponse,
    AuditReferences,
    CapabilityId,
    CapabilityInvocationRequest,
    ClarificationRequest,
    ToolResultReference,
    WorkflowStatus,
)


class AgentState(AgentContract):
    """Pydantic state schema/public JSON projection for later graph conversion.

    Stores one current invocation/interaction, not conversation or Plan history.
    READY_TO_EXECUTE records workflow readiness, never Domain authorization.
    """

    request: AgentRequest
    intent: AgentIntent = AgentIntent.UNKNOWN
    status: WorkflowStatus = WorkflowStatus.RECEIVED
    invocation: CapabilityInvocationRequest | None = None
    tool_result: ToolResultReference | None = None
    clarification: ClarificationRequest | None = None
    approval_request: ApprovalRequest | None = None
    approval_response: ApprovalResponse | None = None
    audit: AuditReferences = Field(default_factory=AuditReferences)
    final_response: AgentResponse | None = None
    error: AgentError | None = None

    @model_validator(mode="after")
    def coherent_snapshot(self) -> Self:
        request_id = self.request.request_id
        if self.invocation and (
            self.invocation.source_request_id != request_id
            or self.invocation.intent != self.intent
        ):
            raise ValueError("Invocation request/intent mismatch")
        if self.tool_result and (
            self.invocation is None
            or self.tool_result.invocation_id != self.invocation.invocation_id
        ):
            raise ValueError("Result requires matching invocation")
        if self.tool_result and self.status not in (
            WorkflowStatus.COMPLETED, WorkflowStatus.FAILED
        ):
            raise ValueError("Unexecuted snapshot cannot contain a tool result")
        if (self.status == WorkflowStatus.NEEDS_CLARIFICATION) != (
            self.clarification is not None
        ):
            raise ValueError("Clarification belongs only to clarification state")
        if self.clarification and self.clarification.source_request_id != request_id:
            raise ValueError("Clarification request mismatch")
        if self.approval_request:
            if (
                self.approval_request.source_request_id != request_id
                or self.invocation is None
                or self.approval_request.invocation_id != self.invocation.invocation_id
                or not self.invocation.requires_approval
                or self.invocation.capability != CapabilityId.REVISE_PLAN
                or self.request.context.plan_ref != self.approval_request.before_plan
            ):
                raise ValueError("Approval proposal must bind invocation and before Plan")
            if self.status not in (
                WorkflowStatus.WAITING_FOR_APPROVAL, WorkflowStatus.READY_TO_EXECUTE,
                WorkflowStatus.COMPLETED, WorkflowStatus.FAILED,
            ):
                raise ValueError("Approval proposal belongs only to approval lifecycle")
        if self.approval_response:
            if (
                self.approval_request is None
                or self.approval_response.approval_request_id
                != self.approval_request.approval_request_id
                or self.approval_response.source_request_id != request_id
                or self.approval_response.submitted_at < self.approval_request.created_at
            ):
                raise ValueError("Approval response must match explicit proposal")
        if self.status == WorkflowStatus.WAITING_FOR_APPROVAL:
            if self.approval_request is None or self.approval_response is not None:
                raise ValueError("Waiting requires an unanswered approval proposal")
        if self.status in (WorkflowStatus.READY_TO_ROUTE, WorkflowStatus.READY_TO_EXECUTE):
            if self.intent == AgentIntent.UNKNOWN:
                raise ValueError("Readiness requires an explicit known intent")
        if self.status == WorkflowStatus.READY_TO_EXECUTE:
            if self.invocation is None or self.tool_result is not None:
                raise ValueError("Execution readiness requires an unexecuted invocation")
        if self.tool_result or self.status == WorkflowStatus.READY_TO_EXECUTE:
            if self.invocation and self.invocation.requires_approval and (
                self.approval_response is None
                or self.approval_response.decision != ApprovalDecision.APPROVE
            ):
                raise ValueError("Protected invocation requires explicit APPROVE")
        terminal = self.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED)
        if terminal != (self.final_response is not None):
            raise ValueError("Terminal snapshot requires final response")
        if self.final_response and (
            self.final_response.request_id != request_id
            or self.final_response.intent != self.intent
            or self.final_response.outcome != self.status
            or self.final_response.error != self.error
        ):
            raise ValueError("Final response must match state")
        if self.final_response and (
            any(r not in self.final_response.audit.results for r in self.audit.results)
            or any(r not in self.final_response.audit.reasons for r in self.audit.reasons)
        ):
            raise ValueError("Final response cannot discard retained audit references")
        if (self.status == WorkflowStatus.FAILED) != (self.error is not None):
            raise ValueError("Only workflow failure has Agent error")
        if self.status == WorkflowStatus.COMPLETED and (
            self.approval_request is not None and self.approval_response is None
        ):
            raise ValueError("Completed workflow cannot retain pending approval")
        return self
