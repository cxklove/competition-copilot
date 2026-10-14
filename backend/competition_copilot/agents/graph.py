"""Bounded deterministic LangGraph; structured caller selection only, no model.

The channel wrapper contains the public AgentState, not a parallel lifecycle model.
Facade receipts wait in a private channel until a coherent terminal snapshot exists.
"""

import json
from collections.abc import Iterator

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langsmith import tracing_context
from pydantic import ValidationError
from typing_extensions import TypedDict

from competition_copilot.agents.capabilities import (
    AgentCapabilityFacade,
    AgentCapabilityResult,
    CapabilityStatus,
)
from competition_copilot.agents.contracts import (
    AgentContract,
    AgentError,
    AgentErrorCode,
    AgentIntent,
    AgentResponse,
    ApprovalDecision,
    ApprovalRequest,
    AuditReferences,
    ClarificationReason,
    ClarificationRequest,
    ContextField,
    ReferenceKind,
    ResultReference,
    ToolResultReference,
    WorkflowStatus,
)
from competition_copilot.agents.state import AgentState
from competition_copilot.domain.digital_twin import StableId
from competition_copilot.tools.contracts import ToolResult


class GraphInput(AgentContract):
    """Technical input wrapper, with no duplicated AgentState fields.

    All correlation IDs are caller-owned. arguments_json contains a P12.2 typed
    artifact envelope, validated by the Facade before capability execution.
    approval_proposal is caller-prepared interaction metadata, never authority.
    """

    state: AgentState
    clarification_id: StableId
    result_ref: ResultReference
    arguments_json: StableId | None = None
    approval_proposal: ApprovalRequest | None = None


class _Channels(TypedDict, total=False):
    frame: GraphInput
    state: AgentState
    receipt: AgentCapabilityResult
    response: AgentResponse
    branch: str
    missing_fields: tuple[ContextField, ...]
    clarification_reason: ClarificationReason


def _replace(state: AgentState, **changes) -> AgentState:
    return AgentState.model_validate({**state.model_dump(), **changes})


def _merge_audit(*audits: AuditReferences) -> AuditReferences:
    results, reasons = {}, {}
    for audit in audits:
        for ref in audit.results:
            results[(ref.kind, ref.ref_id)] = ref
        for ref in audit.reasons:
            reasons[(ref.result.kind, ref.result.ref_id, ref.reason_code)] = ref
    return AuditReferences(results=tuple(results.values()), reasons=tuple(reasons.values()))


def _failure(state: AgentState, code: AgentErrorCode, message: str):
    error = AgentError(code=code, message=message)
    response = AgentResponse(request_id=state.request.request_id, intent=state.intent,
                             outcome=WorkflowStatus.FAILED, message=message,
                             audit=state.audit, error=error)
    return {"state": _replace(state, status=WorkflowStatus.FAILED,
                              clarification=None, error=error, final_response=response),
            "response": response, "branch": "failure"}


def _reject_constant(value):
    raise ValueError("Non-finite JSON constant: " + value)


def _arguments(frame: GraphInput) -> dict | None:
    if frame.arguments_json is None:
        return None
    value = json.loads(frame.arguments_json, parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise ValueError("Arguments must be a JSON object")
    return value


class CompetitionCopilotGraph:
    """Small public invocation/projection wrapper around the actual compiled graph."""

    def __init__(self, compiled: CompiledStateGraph):
        self.compiled = compiled

    @staticmethod
    def _input(value: GraphInput | dict) -> dict:
        # Detach legacy nested Domain values too; caller objects remain unchanged.
        frame = GraphInput.model_validate(value)
        frame = GraphInput.model_validate_json(frame.model_dump_json())
        if frame.result_ref.kind != ReferenceKind.TOOL_RESULT:
            raise ValueError("Graph result_ref must be TOOL_RESULT")
        return {"frame": frame}

    def invoke(self, value: GraphInput | dict) -> AgentResponse:
        with tracing_context(enabled=False):
            result = self.compiled.invoke(self._input(value), config={"callbacks": []})
        return AgentResponse.model_validate(result["response"])

    def stream(self, value: GraphInput | dict) -> Iterator[dict]:
        """Offline node update inspection; no persistent trace or telemetry export."""
        with tracing_context(enabled=False):
            yield from self.compiled.stream(self._input(value), stream_mode="updates",
                                            config={"callbacks": []})


def build_competition_copilot_graph(facade: AgentCapabilityFacade) -> CompetitionCopilotGraph:
    """Build/compile on explicit call, without checkpointer, store or external IO."""
    metadata = {m.capability: m for m in facade.list_capabilities()}

    def intake(channels):
        frame = GraphInput.model_validate(channels["frame"])
        state = AgentState.model_validate(frame.state)
        if state.status not in (
            WorkflowStatus.RECEIVED, WorkflowStatus.READY_TO_ROUTE,
            WorkflowStatus.READY_TO_EXECUTE, WorkflowStatus.WAITING_FOR_APPROVAL,
        ):
            raise ValueError("Terminal/clarification snapshots cannot restart execution")
        return {"state": state}

    def intent(channels):
        state = channels["state"]
        if state.intent == AgentIntent.UNKNOWN:
            return {"branch": "clarification", "missing_fields": (ContextField.INTENT,),
                    "clarification_reason": ClarificationReason.AMBIGUOUS_INTENT}
        if state.status == WorkflowStatus.RECEIVED:
            state = _replace(state, status=WorkflowStatus.READY_TO_ROUTE)
        return {"state": state, "branch": "route"}

    def route(channels):
        state, frame = channels["state"], channels["frame"]
        if state.invocation is None:
            return {"branch": "clarification",
                    "missing_fields": (ContextField.CAPABILITY_INVOCATION,),
                    "clarification_reason": ClarificationReason.MISSING_REQUIRED_CONTEXT}
        capability = metadata.get(state.invocation.capability)
        if capability is None:
            return _failure(state, AgentErrorCode.TOOL_UNAVAILABLE, "UNSUPPORTED_CAPABILITY")
        try:
            args = _arguments(frame)
        except (ValueError, TypeError):
            return _failure(state, AgentErrorCode.SERIALIZATION_ERROR, "Invalid arguments JSON")
        # Presence only, using the published schema; no capability planning/business checks.
        if args is None or "payload" not in args or "artifact_ref" not in args:
            missing = (ContextField.CAPABILITY_ARGUMENTS,)
        elif not isinstance(args["payload"], dict):
            return _failure(state, AgentErrorCode.CAPABILITY_EXECUTION_FAILED, "INVALID_INPUT")
        else:
            schema = json.loads(capability.input_schema_json)
            payload_schema = schema["properties"]["payload"]
            if "$ref" in payload_schema:
                payload_schema = schema["$defs"][payload_schema["$ref"].split("/")[-1]]
            missing_names = [name for name in payload_schema.get("required", ())
                             if name not in args["payload"] or args["payload"][name] is None]
            field_names = {
                "competition_id": ContextField.COMPETITION, "edition_id": ContextField.EDITION,
                "track_id": ContextField.TRACK, "student": ContextField.STUDENT_PROFILE,
                "plan": ContextField.PLAN, "before": ContextField.PLAN,
            }
            missing = tuple(sorted({field_names.get(name, ContextField.CAPABILITY_ARGUMENTS)
                                    for name in missing_names}, key=lambda field: field.value))
        if missing:
            return {"branch": "clarification", "missing_fields": missing,
                    "clarification_reason": ClarificationReason.MISSING_REQUIRED_CONTEXT}
        protected = capability.requires_explicit_approval or state.invocation.requires_approval
        if protected:
            approved = (state.approval_response is not None
                        and state.approval_response.decision == ApprovalDecision.APPROVE)
            if not approved:
                if state.approval_response is not None:
                    return _failure(state, AgentErrorCode.APPROVAL_REQUIRED, "Approval was rejected")
                if state.approval_request is None and frame.approval_proposal is None:
                    return {"branch": "clarification", "missing_fields": (ContextField.APPROVAL_CONTEXT,),
                            "clarification_reason": ClarificationReason.MISSING_APPROVAL_CONTEXT}
                return {"branch": "approval"}
        return {"state": _replace(state, status=WorkflowStatus.READY_TO_EXECUTE),
                "branch": "tool_execution"}

    def clarification(channels):
        state, frame = channels["state"], channels["frame"]
        question = ClarificationRequest(
            clarification_id=frame.clarification_id,
            source_request_id=state.request.request_id,
            reason=channels["clarification_reason"], fields=channels["missing_fields"],
            question="Provide explicit structured context: " + ", ".join(
                field.value for field in channels["missing_fields"]),
        )
        state = _replace(state, status=WorkflowStatus.NEEDS_CLARIFICATION,
                         approval_request=None, approval_response=None, clarification=question)
        response = AgentResponse(request_id=state.request.request_id, intent=state.intent,
                                 outcome=state.status, message=question.question,
                                 clarification=question, audit=state.audit)
        return {"state": state, "response": response}

    def approval(channels):
        state, frame = channels["state"], channels["frame"]
        proposal = state.approval_request or frame.approval_proposal
        try:
            state = _replace(state, status=WorkflowStatus.WAITING_FOR_APPROVAL,
                             approval_request=proposal)
        except (ValueError, ValidationError):
            return _failure(state, AgentErrorCode.INVALID_WORKFLOW_TRANSITION,
                            "Approval proposal does not match request/invocation/Plan")
        response = AgentResponse(request_id=state.request.request_id, intent=state.intent,
                                 outcome=state.status, message="Explicit approval required",
                                 approval_request=proposal, audit=state.audit)
        return {"state": state, "response": response}

    def tool_execution(channels):
        state, frame = channels["state"], channels["frame"]
        if state.status != WorkflowStatus.READY_TO_EXECUTE or state.invocation is None:
            raise ValueError("Execution requires a validated ready snapshot")
        # All capability calls go through the Facade, exactly once, with no retry loop.
        receipt = facade.execute(state.invocation, _arguments(frame), result_ref=frame.result_ref)
        return {"receipt": receipt}

    def result_validation(channels):
        state, frame = channels["state"], channels["frame"]
        try:
            receipt = AgentCapabilityResult.model_validate(channels["receipt"])
            if (receipt.invocation_id != state.invocation.invocation_id
                or receipt.source_request_id != state.request.request_id
                or receipt.capability != state.invocation.capability
                or receipt.result_ref != frame.result_ref):
                raise ValueError("Receipt correlation mismatch")
        except (ValueError, TypeError):
            return _failure(state, AgentErrorCode.INVALID_WORKFLOW_TRANSITION,
                            "Invalid capability result envelope")
        audit = _merge_audit(state.audit, receipt.audit)
        state = _replace(state, audit=audit)
        if receipt.status == CapabilityStatus.ERROR:
            return _failure(state, AgentErrorCode.CAPABILITY_EXECUTION_FAILED,
                            "Capability invocation failed: " + receipt.error.code.value)
        return {"state": state, "receipt": receipt, "branch": "success"}

    def explain(channels):
        state, receipt = channels["state"], channels["receipt"]
        response = AgentResponse(
            request_id=state.request.request_id, intent=state.intent,
            outcome=WorkflowStatus.COMPLETED, audit=state.audit,
            message="Capability completed: " + receipt.capability.value + ". See referenced result.",
        )
        reference = ToolResultReference(invocation_id=state.invocation.invocation_id,
                                       result=ToolResult[ResultReference](
                                           success=True, data=receipt.result_ref))
        return {"state": _replace(state, status=WorkflowStatus.COMPLETED,
                                   tool_result=reference, final_response=response),
                "response": response}

    graph = StateGraph(_Channels)
    for name, node in (
        ("intake", intake), ("intent", intent), ("route", route),
        ("clarification", clarification), ("approval", approval),
        ("tool_execution", tool_execution), ("result_validation", result_validation),
        ("explain", explain),
    ):
        graph.add_node(name, node)
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "intent")
    graph.add_conditional_edges("intent", lambda c: c["branch"],
                                {"route": "route", "clarification": "clarification"})
    graph.add_conditional_edges("route", lambda c: c["branch"], {
        "clarification": "clarification", "approval": "approval",
        "tool_execution": "tool_execution", "failure": END,
    })
    graph.add_edge("clarification", END)
    graph.add_edge("approval", END)
    graph.add_edge("tool_execution", "result_validation")
    graph.add_conditional_edges("result_validation", lambda c: c["branch"],
                                {"success": "explain", "failure": END})
    graph.add_edge("explain", END)
    return CompetitionCopilotGraph(graph.compile(checkpointer=None, store=None))
