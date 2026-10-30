"""Bounded LangGraph; optional untrusted intent proposals, deterministic guards.

The channel wrapper contains the public AgentState, not a parallel lifecycle model.
Facade receipts wait in a private channel until a coherent terminal snapshot exists.
"""

import json
from collections.abc import Callable, Iterator

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langsmith import tracing_context
from pydantic import AwareDatetime, ValidationError
from typing_extensions import TypedDict

from competition_copilot.agents.capabilities import (
    AgentCapabilityFacade,
    AgentCapabilityResult,
    CapabilityArguments,
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
    CapabilityInvocationRequest,
    ClarificationChoice,
    ClarificationReason,
    ClarificationRequest,
    ContextField,
    ReferenceKind,
    ResultReference,
    ToolResultReference,
    WorkflowStatus,
)
from competition_copilot.agents.explanation import (
    ExplanationContext,
    ExplanationModel,
    ExplanationRendering,
    build_explanation_context,
    generate_explanation,
)
from competition_copilot.agents.human_contracts import (
    ClarificationOption,
    HumanResponseInterpreter,
    HumanResume,
)
from competition_copilot.agents.human_interactions import (
    build_approved_replanning_input,
    explicit_approval_response,
    prepare_approval,
    resolve_clarification,
    validate_explicit_approval,
    validate_language_clarification,
    validate_pending_revision,
)
from competition_copilot.agents.routing import (
    INTENT_CAPABILITIES,
    IntentModel,
    IntentModelInput,
    IntentRoutingProposal,
    PendingArgumentPreparation,
    ProposedTargets,
    RoutingProposalValidator,
    RoutingValidationResult,
    RoutingValidationStatus,
    context_conflicts,
    explicit_intent_proposal,
    routing_catalog,
)
from competition_copilot.agents.state import AgentState
from competition_copilot.application.instruction_preparation import PlanRevisionProposal
from competition_copilot.domain.digital_twin import StableId
from competition_copilot.domain.plan import CompetitionPlan
from competition_copilot.domain.replanning_input import ReplanningInput
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
    routing_invocation_id: StableId | None = None
    routing_arguments_ref: ResultReference | None = None
    resume: HumanResume | None = None
    clarification_options: tuple[ClarificationOption, ...] = ()
    approval_request_id: StableId | None = None
    interaction_created_at: AwareDatetime | None = None
    revision_proposal: ReplanningInput | PlanRevisionProposal | None = None
    prepared_revision: PlanRevisionProposal | None = None
    pending_preparation: PendingArgumentPreparation | None = None


class _PreparedRevisionPayload(AgentContract):
    before: CompetitionPlan


def _revision_source(frame, state, facade):
    if frame.prepared_revision is None:
        checked = facade.validate_arguments(state.invocation, _arguments(frame))
        source = checked.payload.replanning_input
        if checked.payload.before != source.before:
            raise ValueError("Execution Plan differs from proposed input")
        return source
    source = PlanRevisionProposal.model_validate(frame.prepared_revision)
    checked = CapabilityArguments[_PreparedRevisionPayload].model_validate(_arguments(frame))
    if (state.invocation is None or state.invocation.capability != "revise_plan"
        or not state.invocation.requires_approval
        or state.invocation.source_request_id != state.request.request_id
        or checked.artifact_ref != state.invocation.arguments_ref
        or checked.payload.before != source.before
        or state.request.context.plan_ref != source.operation.expected_plan):
        raise ValueError("Prepared operation binding mismatch")
    return source


class GraphTurn(AgentContract):
    """Execution bundle, reusing public State/Response; caller manages continuity."""
    continuation: GraphInput
    response: AgentResponse


class _Channels(TypedDict, total=False):
    frame: GraphInput
    state: AgentState
    receipt: AgentCapabilityResult
    response: AgentResponse
    branch: str
    missing_fields: tuple[ContextField, ...]
    clarification_reason: ClarificationReason
    proposal: IntentRoutingProposal
    routing_validation: RoutingValidationResult
    human_resolution: str
    explanation_context: ExplanationContext
    explanation_rendering: ExplanationRendering


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
        return self.run_turn(value).response

    def run_turn(self, value: GraphInput | dict) -> GraphTurn:
        with tracing_context(enabled=False):
            result = self.compiled.invoke(self._input(value), config={"callbacks": []})
        frame = GraphInput(**{**result["frame"].model_dump(), "state": result["state"], "resume": None})
        return GraphTurn(continuation=frame, response=AgentResponse.model_validate(result["response"]))

    def resume(self, prior: GraphInput | dict, response: HumanResume | dict) -> GraphTurn:
        prior = GraphInput.model_validate(prior)
        frame = GraphInput(**{**prior.model_dump(), "resume": HumanResume.model_validate(response)})
        return self.run_turn(frame)

    def stream(self, value: GraphInput | dict) -> Iterator[dict]:
        """Offline node update inspection; no persistent trace or telemetry export."""
        with tracing_context(enabled=False):
            yield from self.compiled.stream(self._input(value), stream_mode="updates",
                                            config={"callbacks": []})


def build_competition_copilot_graph(
    facade: AgentCapabilityFacade, *, intent_model: IntentModel | None = None,
    human_interpreter: HumanResponseInterpreter | None = None,
    explanation_model: ExplanationModel | None = None,
    resume_preparer: Callable[[GraphInput], GraphInput] | None = None,
) -> CompetitionCopilotGraph:
    """Build/compile on explicit call, without checkpointer, store or external IO."""
    metadata = {m.capability: m for m in facade.list_capabilities()}
    validator = RoutingProposalValidator(facade)
    catalog = routing_catalog(facade)

    def intake(channels):
        frame = GraphInput.model_validate(channels["frame"])
        state = AgentState.model_validate(frame.state)
        if frame.resume is not None:
            if state.status not in (WorkflowStatus.NEEDS_CLARIFICATION, WorkflowStatus.WAITING_FOR_APPROVAL):
                return _failure(state, AgentErrorCode.INVALID_WORKFLOW_TRANSITION, "No pending interaction")
            return {"state": state, "branch": ("clarification_resolution" if state.status ==
                WorkflowStatus.NEEDS_CLARIFICATION else "approval_resolution")}
        if state.status not in (
            WorkflowStatus.RECEIVED, WorkflowStatus.READY_TO_ROUTE,
            WorkflowStatus.READY_TO_EXECUTE, WorkflowStatus.WAITING_FOR_APPROVAL,
        ):
            raise ValueError("Terminal/clarification snapshots cannot restart execution")
        return {"state": state, "branch": "intent"}

    def clarification_resolution(channels):
        state, frame = channels["state"], channels["frame"]
        reply = frame.resume
        try:
            response = reply.clarification
            if response is None:
                if reply.message is None or human_interpreter is None:
                    raise ValueError("A clarification response is required")
                proposed = human_interpreter.clarify(reply.message, state.clarification,
                                                      frame.clarification_options)
                response = validate_language_clarification(reply.message, state.clarification,
                                                           proposed, frame.clarification_options)
                if response is None:
                    return {"branch": "clarification", "missing_fields": state.clarification.fields,
                        "clarification_reason": state.clarification.reason,
                        "human_resolution": "CLARIFICATION_UNRESOLVED"}
            state, args = resolve_clarification(state, response, _arguments(frame),
                state.invocation.arguments_ref if state.invocation else frame.routing_arguments_ref)
            reference = ResultReference(kind="CLARIFICATION_RESPONSE", ref_id=
                response.clarification_id + "/response/" + response.submitted_at.isoformat())
            state = _replace(state, audit=_merge_audit(state.audit, AuditReferences(results=(reference,))))
            frame = GraphInput(**{**frame.model_dump(), "state": state,
                                  "arguments_json": json.dumps(args, sort_keys=True)})
            if state.clarification is None and frame.pending_preparation and resume_preparer:
                prepared = GraphInput.model_validate(resume_preparer(frame))
                if prepared.state != state:
                    raise ValueError("Argument preparation cannot replace resolved state")
                frame = prepared
        except Exception:
            return _failure(channels["state"], AgentErrorCode.INVALID_WORKFLOW_TRANSITION,
                            "Clarification response rejected")
        if state.clarification is not None:
            return {"frame": frame, "state": state, "branch": "clarification",
                "missing_fields": state.clarification.fields,
                "clarification_reason": state.clarification.reason,
                "human_resolution": "CLARIFICATION_PARTIAL"}
        return {"frame": frame, "state": state, "branch": "intent",
                "human_resolution": "CLARIFICATION_RESOLVED"}

    def approval_resolution(channels):
        state, frame = channels["state"], channels["frame"]
        reply, pending = frame.resume, state.approval_request
        try:
            source = _revision_source(frame, state, facade)
            # Pending interactions are candidates too, including ambiguous replies.
            validate_pending_revision(pending, source, state.request, state.invocation)
            if reply.current_plan is not None and reply.current_plan != pending.before_plan:
                raise ValueError("Approval is stale: current Plan changed")
            response = reply.approval
            if response is None:
                if reply.message is None:
                    raise ValueError("Approval reply required")
                response = explicit_approval_response(pending, reply.message)
                if response is None:
                    return {"branch": "approval", "human_resolution": "AMBIGUOUS_CONSENT"}
            validate_explicit_approval(pending, response, source, state.request, state.invocation,
                                      reply.current_plan)
            refs = (ResultReference(kind="APPROVAL_REQUEST", ref_id=pending.approval_request_id),
                ResultReference(kind="APPROVAL_RESPONSE", ref_id=pending.approval_request_id +
                    "/response/" + response.submitted_at.isoformat()))
            audit = _merge_audit(state.audit, pending.audit, AuditReferences(results=refs))
            if response.decision == ApprovalDecision.REJECT:
                result = AgentResponse(request_id=state.request.request_id, intent=state.intent,
                    outcome="COMPLETED", message="Revision rejected; no capability executed", audit=audit)
                terminal = _replace(state, status=WorkflowStatus.COMPLETED,
                    approval_response=response, audit=audit, final_response=result)
                context = build_explanation_context(terminal)
                rendering = generate_explanation(context, explanation_model)
                result = AgentResponse(**{**result.model_dump(), "message": rendering.message,
                                          "plan_refs": context.plan_refs})
                return {"state": _replace(terminal, final_response=result),
                    "response": result, "branch": "end", "human_resolution": "APPROVAL_REJECTED",
                    "explanation_context": context, "explanation_rendering": rendering}
            approved = build_approved_replanning_input(pending, response, source, state.request,
                state.invocation, current_plan=reply.current_plan, approved_by_ref=reply.approved_by_ref,
                executed_at=reply.executed_at)
            if reply.executed_at is None or reply.executed_at < response.submitted_at:
                raise ValueError("Explicit execution time must follow approval")
            audit = _merge_audit(audit, AuditReferences(results=(
                ResultReference(kind="REPLANNING_INPUT", ref_id=approved.id),
                ResultReference(kind="AUTHORITY", ref_id=approved.id + (
                    "#/plan_status_instruction/authority" if approved.plan_status_instruction
                    else "#/instructions/0/authority")),
            )))
            args = {"artifact_ref": state.invocation.arguments_ref.model_dump(mode="json"),
                "payload": {"before": approved.before.model_dump(mode="json"),
                    "replanning_input": approved.model_dump(mode="json"),
                    "executed_at": reply.executed_at.isoformat()}}
            state = _replace(state, status=WorkflowStatus.READY_TO_EXECUTE,
                             approval_response=response, audit=audit)
            frame = GraphInput(**{**frame.model_dump(), "state": state, "revision_proposal": source,
                                  "arguments_json": json.dumps(args, sort_keys=True)})
            return {"frame": frame, "state": state, "branch": "route",
                    "human_resolution": "APPROVAL_ACCEPTED_AUTHORITY_BOUND"}
        except Exception:
            return _failure(channels["state"], AgentErrorCode.INVALID_WORKFLOW_TRANSITION,
                            "Approval response rejected: binding, authority or stale context")

    def intent(channels):
        state = channels["state"]
        if state.intent == AgentIntent.UNKNOWN and (state.request.intent is not None or intent_model is not None):
            # Explicit known intent always bypasses the model. No parameters,
            # identities, approvals or Domain results may come from the model.
            try:
                raw = explicit_intent_proposal(state.request)
                if raw is None:
                    raw = intent_model.propose(IntentModelInput(request=state.request, catalog=catalog))
            except Exception:
                return _failure(state, AgentErrorCode.TOOL_UNAVAILABLE, "INTENT_MODEL_FAILED")
            try:
                proposal = IntentRoutingProposal.model_validate(raw)
            except (ValueError, TypeError):
                return _failure(state, AgentErrorCode.UNSUPPORTED_INTENT, "INVALID_ROUTING_PROPOSAL")
            frame = channels["frame"]
            try:
                validation = validator.validate(proposal, state.request,
                    invocation_id=frame.routing_invocation_id,
                    arguments_ref=frame.routing_arguments_ref, arguments=_arguments(frame),
                    pending_preparation=frame.pending_preparation)
            except (ValueError, TypeError):
                return _failure(state, AgentErrorCode.SERIALIZATION_ERROR, "Invalid routing arguments")
            trace = {"proposal": proposal, "routing_validation": validation}
            if validation.status == RoutingValidationStatus.REJECTED:
                return {**trace, **_failure(state, AgentErrorCode.UNSUPPORTED_INTENT,
                                           validation.reason.value)}
            if validation.status == RoutingValidationStatus.CLARIFICATION:
                if (validation.reason == "APPROVAL_REQUIRED" and frame.approval_request_id
                    and frame.interaction_created_at and frame.routing_invocation_id
                    and frame.routing_arguments_ref and proposal.ambiguity == "NONE"
                    and not proposal.missing_context):
                    try:
                        args = _arguments(frame)
                        if context_conflicts(state.request, args["payload"], proposal.targets):
                            raise ValueError("Context conflict")
                        invocation = CapabilityInvocationRequest(
                            invocation_id=frame.routing_invocation_id,
                            source_request_id=state.request.request_id, intent=proposal.intent,
                            capability=proposal.candidate_capability, requires_approval=True,
                            arguments_ref=frame.routing_arguments_ref)
                        prepared_state = _replace(state, intent=proposal.intent, invocation=invocation)
                        source = _revision_source(frame, prepared_state, facade)
                        prepare_approval(source, state.request, invocation,
                            approval_request_id=frame.approval_request_id, created_at=frame.interaction_created_at)
                        return {**trace, "state": _replace(state, intent=proposal.intent,
                            invocation=invocation, status=WorkflowStatus.READY_TO_ROUTE), "branch": "route"}
                    except Exception:
                        return {**trace, **_failure(state, AgentErrorCode.MISSING_CONTEXT,
                                                   "Invalid prepared mutation proposal")}
                return {**trace, "branch": "clarification",
                        "missing_fields": validation.missing_context,
                        "clarification_reason": validation.clarification_reason}
            state = _replace(state, intent=proposal.intent, invocation=validation.invocation,
                             status=WorkflowStatus.READY_TO_ROUTE)
            return {**trace, "state": state, "branch": "route"}
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
        if state.invocation.capability not in INTENT_CAPABILITIES[state.intent]:
            return _failure(state, AgentErrorCode.UNSUPPORTED_INTENT, "INCOMPATIBLE_CAPABILITY")
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
            if context_conflicts(state.request, args["payload"], ProposedTargets(),
                                 capability=state.invocation.capability):
                return _failure(state, AgentErrorCode.INVALID_WORKFLOW_TRANSITION, "CONTEXT_CONFLICT")
            if (frame.prepared_revision is not None and state.invocation.capability == "revise_plan"
                and state.approval_response is None):
                try:
                    _revision_source(frame, state, facade)
                    if frame.approval_request_id is None or frame.interaction_created_at is None:
                        raise ValueError("Pending approval metadata required")
                    return {"branch": "approval"}
                except (ValueError, TypeError):
                    return _failure(state, AgentErrorCode.APPROVAL_REQUIRED, "Invalid prepared operation")
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
                    if frame.approval_request_id is not None and frame.interaction_created_at is not None:
                        return {"branch": "approval"}
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
            options=tuple(ClarificationChoice(**option.model_dump())
                          for option in frame.clarification_options
                          if option.field in channels["missing_fields"]),
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
            source = _revision_source(frame, state, facade)
            if proposal is None:
                if source.decision.outcome == "keep_current_plan":
                    result = AgentResponse(request_id=state.request.request_id, intent=state.intent,
                        outcome="COMPLETED", message="No revision required; no capability executed", audit=state.audit)
                    return {"state": _replace(state, status=WorkflowStatus.COMPLETED, final_response=result),
                            "response": result}
                if source.decision.outcome == "undetermined":
                    question = ClarificationRequest(clarification_id=frame.clarification_id,
                        source_request_id=state.request.request_id, reason="MISSING_REQUIRED_CONTEXT",
                        fields=(ContextField.CAPABILITY_ARGUMENTS,),
                        question="Resolve the referenced Domain uncertainty before proposing revision")
                    result = AgentResponse(request_id=state.request.request_id, intent=state.intent,
                        outcome="NEEDS_CLARIFICATION", message=question.question, clarification=question, audit=state.audit)
                    return {"state": _replace(state, status=WorkflowStatus.NEEDS_CLARIFICATION, clarification=question),
                            "response": result}
                proposal = prepare_approval(source, state.request, state.invocation,
                    approval_request_id=frame.approval_request_id, created_at=frame.interaction_created_at)
            # New and supplied requests must match the same current P11 input.
            validate_pending_revision(proposal, source, state.request, state.invocation)
            state = _replace(state, status=WorkflowStatus.WAITING_FOR_APPROVAL,
                             approval_request=proposal, audit=_merge_audit(state.audit, proposal.audit))
        except (ValueError, ValidationError):
            return _failure(state, AgentErrorCode.INVALID_WORKFLOW_TRANSITION,
                            "Approval proposal does not match request/invocation/Plan")
        context = build_explanation_context(state)
        rendering = generate_explanation(context, explanation_model)
        response = AgentResponse(request_id=state.request.request_id, intent=state.intent,
                                 outcome=state.status, message=rendering.message,
                                 approval_request=proposal, audit=state.audit, plan_refs=context.plan_refs)
        return {"state": state, "response": response,
                "explanation_context": context, "explanation_rendering": rendering}

    def tool_execution(channels):
        state, frame = channels["state"], channels["frame"]
        if state.status != WorkflowStatus.READY_TO_EXECUTE or state.invocation is None:
            raise ValueError("Execution requires a validated ready snapshot")
        if state.invocation.capability == "revise_plan":
            try:
                checked = facade.validate_arguments(state.invocation, _arguments(frame))
                if frame.resume is None or frame.revision_proposal is None:
                    raise ValueError("Mutation requires a validated approval continuation")
                expected = build_approved_replanning_input(state.approval_request,
                    state.approval_response, frame.revision_proposal, state.request, state.invocation,
                    current_plan=frame.resume.current_plan, approved_by_ref=frame.resume.approved_by_ref,
                    executed_at=frame.resume.executed_at)
                if (checked.payload.replanning_input != expected or checked.payload.before != expected.before
                    or checked.payload.executed_at != frame.resume.executed_at):
                    raise ValueError("Approved operation changed")
            except Exception:
                return _failure(state, AgentErrorCode.APPROVAL_REQUIRED, "Authorized revision input required")
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
        context = build_explanation_context(state, receipt)
        # These product projections/self-actions need no model explanation,
        # including when natural-language routing selected the read capability.
        rendering = generate_explanation(context, None if receipt.capability in (
            "get_competition_details", "get_my_competitions", "get_my_competition",
            "add_my_competition", "update_my_competition", "remove_my_competition",
            "select_my_competition_plan") else explanation_model)
        state = _replace(state, audit=_merge_audit(state.audit, AuditReferences(results=context.result_refs)))
        response = AgentResponse(
            request_id=state.request.request_id, intent=state.intent,
            outcome=WorkflowStatus.COMPLETED, audit=state.audit,
            message=rendering.message, plan_refs=context.plan_refs,
        )
        reference = ToolResultReference(invocation_id=state.invocation.invocation_id,
                                       result=ToolResult[ResultReference](
                                           success=True, data=receipt.result_ref))
        return {"state": _replace(state, status=WorkflowStatus.COMPLETED,
                                   tool_result=reference, final_response=response),
                "response": response, "explanation_context": context, "explanation_rendering": rendering}

    graph = StateGraph(_Channels)
    for name, node in (
        ("intake", intake), ("intent", intent), ("route", route),
        ("clarification", clarification), ("approval", approval),
        ("tool_execution", tool_execution), ("result_validation", result_validation),
        ("explain", explain),
        ("clarification_resolution", clarification_resolution), ("approval_resolution", approval_resolution),
    ):
        graph.add_node(name, node)
    graph.add_edge(START, "intake")
    graph.add_conditional_edges("intake", lambda c: c["branch"], {
        "intent": "intent", "clarification_resolution": "clarification_resolution",
        "approval_resolution": "approval_resolution", "failure": END,
    })
    graph.add_conditional_edges("clarification_resolution", lambda c: c["branch"], {
        "intent": "intent", "clarification": "clarification", "failure": END,
    })
    graph.add_conditional_edges("approval_resolution", lambda c: c["branch"], {
        "route": "route", "approval": "approval", "end": END, "failure": END,
    })
    graph.add_conditional_edges("intent", lambda c: c["branch"],
                                {"route": "route", "clarification": "clarification", "failure": END})
    graph.add_conditional_edges("route", lambda c: c["branch"], {
        "clarification": "clarification", "approval": "approval",
        "tool_execution": "tool_execution", "failure": END,
    })
    graph.add_edge("clarification", END)
    graph.add_edge("approval", END)
    graph.add_conditional_edges("tool_execution", lambda c: "failure" if c.get("branch") == "failure" else "result_validation",
                                {"failure": END, "result_validation": "result_validation"})
    graph.add_conditional_edges("result_validation", lambda c: c["branch"],
                                {"success": "explain", "failure": END})
    graph.add_edge("explain", END)
    return CompetitionCopilotGraph(graph.compile(checkpointer=None, store=None))
