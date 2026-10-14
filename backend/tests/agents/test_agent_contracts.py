"""Offline contract tests; no graph, model, capability or Domain execution."""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.agents.contracts import (
    AgentContext,
    AgentError,
    AgentErrorCode,
    AgentIntent,
    AgentRequest,
    AgentResponse,
    ApprovalAction,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResponse,
    AuditReferences,
    CapabilityId,
    CapabilityInvocationRequest,
    ClarificationReason,
    ClarificationRequest,
    ContextField,
    ReasonReference,
    ReferenceKind,
    ResultReference,
    ToolResultReference,
    WorkflowStatus,
)
from competition_copilot.agents.state import AgentState
from competition_copilot.domain.replanning import PlanReference
from competition_copilot.tools.contracts import ToolError, ToolErrorCode, ToolResult

TIME = datetime(2026, 10, 14, 8, tzinfo=timezone.utc)


def ref(kind, identifier="artifact-1"):
    return ResultReference(kind=kind, ref_id=identifier)


@pytest.fixture
def plan_ref():
    return PlanReference(
        plan_id="plan-1", student_id="student-1", version=1,
        target={"competition_id": "competition-1", "edition_id": "edition-1",
                "track_id": "track-1"},
        updated_at=TIME, milestone_ids=("m1",), content_digest="a" * 64,
    )


@pytest.fixture
def agent_request(plan_ref):
    return AgentRequest(
        request_id="request-1", user_message="Please revise my plan",
        context=AgentContext(plan_ref=plan_ref),
    )


@pytest.fixture
def audit():
    decision = ref(ReferenceKind.REPLANNING_DECISION, "decision-fingerprint")
    return AuditReferences(
        results=(decision, ref(ReferenceKind.EVIDENCE), ref(ReferenceKind.EVENT),
                 ref(ReferenceKind.SOURCE)),
        reasons=(ReasonReference(result=decision, reason_code="TARGET_TRACK_REMOVED"),),
    )


@pytest.fixture
def invocation(agent_request):
    return CapabilityInvocationRequest(
        invocation_id="invoke-1", source_request_id=agent_request.request_id,
        intent=AgentIntent.REQUEST_PLAN_REVISION, capability=CapabilityId.REVISE_PLAN,
        arguments_ref=ref(ReferenceKind.CAPABILITY_ARGUMENTS), requires_approval=True,
    )


@pytest.fixture
def approval(agent_request, invocation, audit):
    return ApprovalRequest(
        approval_request_id="approval-1", source_request_id=agent_request.request_id,
        invocation_id=invocation.invocation_id, action=ApprovalAction.PLAN_REVISION,
        summary="Approve cancellation of this plan only",
        before_plan=agent_request.context.plan_ref,
        decision_ref=ref(ReferenceKind.REPLANNING_DECISION, "decision-fingerprint"),
        affected_scope_ref=ref(ReferenceKind.AFFECTED_SCOPE),
        resolution_ref=ref(ReferenceKind.SCOPE_RESOLUTION),
        proposed_input_ref=ref(ReferenceKind.REPLANNING_INPUT),
        instruction_refs=(ref(ReferenceKind.REVISION_INSTRUCTION),),
        audit=audit, created_at=TIME,
    )


def submitted(approval, decision=ApprovalDecision.APPROVE, **overrides):
    return ApprovalResponse(**{
        "approval_request_id": approval.approval_request_id,
        "source_request_id": approval.source_request_id,
        "decision": decision, "submitted_at": TIME + timedelta(seconds=1),
        **overrides,
    })


def test_minimal_request_does_not_guess_context():
    agent_request = AgentRequest(request_id="r", user_message="Can I participate?")
    assert agent_request.context == AgentContext()
    assert AgentState(request=agent_request).intent == AgentIntent.UNKNOWN
    with pytest.raises(ValidationError):
        AgentRequest(user_message="Missing caller ID")


@pytest.mark.parametrize("intent", list(AgentIntent))
def test_known_and_unknown_intents_are_interaction_only(intent):
    state = AgentState(request=AgentRequest(request_id="r", user_message="Hello"),
                       intent=intent)
    assert state.intent == intent


@pytest.mark.parametrize("raw", ["ELIGIBLE", "INELIGIBLE", "REPLAN", "KEEP", "fix plan"])
def test_business_decisions_are_not_agent_intents(raw):
    with pytest.raises(ValidationError):
        AgentState(request=AgentRequest(request_id="r", user_message="Hello"), intent=raw)


def test_optional_context_and_plan_consistency(plan_ref):
    context = AgentContext(student_id="student-1", competition_id="competition-1",
                           edition_id="edition-1", track_id="track-1", plan_ref=plan_ref)
    assert context.plan_ref == plan_ref
    for kwargs in ({"track_id": "x"}, {"edition_id": "x"},
                   {"plan_ref": plan_ref, "student_id": "different"},
                   {"profile_ref": ref(ReferenceKind.EVENT)}):
        with pytest.raises(ValidationError):
            AgentContext(**kwargs)


@pytest.mark.parametrize("reason,fields", [
    (ClarificationReason.MISSING_REQUIRED_CONTEXT, (ContextField.COMPETITION,)),
    (ClarificationReason.AMBIGUOUS_INTENT, (ContextField.INTENT,)),
    (ClarificationReason.AMBIGUOUS_TARGET, (ContextField.TRACK,)),
])
def test_clarification_state_and_response(agent_request, reason, fields):
    question = ClarificationRequest(
        clarification_id="clarify-1", source_request_id=agent_request.request_id,
        reason=reason, fields=fields, question="Which target or capability?",
    )
    state = AgentState(request=agent_request, status=WorkflowStatus.NEEDS_CLARIFICATION,
                       clarification=question)
    response = AgentResponse(request_id=agent_request.request_id, intent=AgentIntent.UNKNOWN,
                             outcome=state.status, message=question.question,
                             clarification=question)
    assert state.request.context == agent_request.context
    assert response.clarification.fields == fields


def test_clarification_invalid_shape(agent_request):
    for overrides in ({"reason": "guess"}, {"fields": ()},
                      {"fields": (ContextField.INTENT, ContextField.INTENT)}):
        with pytest.raises(ValidationError):
            ClarificationRequest(**{
                "clarification_id": "q", "source_request_id": agent_request.request_id,
                "reason": ClarificationReason.AMBIGUOUS_INTENT,
                "fields": (ContextField.INTENT,), "question": "Which intent?",
                **overrides,
            })


def test_approval_waiting_does_not_grant_authority(agent_request, invocation, approval):
    state = AgentState(request=agent_request, intent=invocation.intent,
                       status=WorkflowStatus.WAITING_FOR_APPROVAL,
                       invocation=invocation, approval_request=approval)
    assert state.approval_response is None
    assert not hasattr(approval, "authority")
    response = AgentResponse(request_id=agent_request.request_id, intent=invocation.intent,
                             outcome=state.status, message="Approval needed",
                             approval_request=approval)
    assert response.approval_request == approval


@pytest.mark.parametrize("decision", list(ApprovalDecision))
def test_explicit_approval_or_rejection(approval, decision):
    assert submitted(approval, decision).decision == decision


@pytest.mark.parametrize("decision", [None, "AUTO_APPROVE", "ASSUMED_APPROVED",
                                      "SILENT_APPROVAL", "Probably fine", True])
def test_implicit_approval_rejected(approval, decision):
    with pytest.raises(ValidationError):
        submitted(approval, decision)


def test_ready_execution_requires_matching_explicit_approval(agent_request, invocation, approval):
    kwargs = dict(request=agent_request, intent=invocation.intent,
                  status=WorkflowStatus.READY_TO_EXECUTE, invocation=invocation,
                  approval_request=approval)
    for response in (None, submitted(approval, ApprovalDecision.REJECT),
                     submitted(approval, approval_request_id="other"),
                     submitted(approval, source_request_id="other"),
                     submitted(approval, submitted_at=TIME - timedelta(seconds=1))):
        with pytest.raises(ValidationError):
            AgentState(**kwargs, approval_response=response)
    state = AgentState(**kwargs, approval_response=submitted(approval))
    assert state.status == WorkflowStatus.READY_TO_EXECUTE
    assert state.approval_response.decision == ApprovalDecision.APPROVE


def test_approval_preconditions_and_evidence(agent_request, invocation, approval):
    for update in ({"decision_ref": ref(ReferenceKind.EVENT)},
                   {"instruction_refs": ()}, {"audit": AuditReferences()},
                   {"created_at": datetime(2026, 10, 14)}):
        with pytest.raises(ValidationError):
            ApprovalRequest.model_validate({**approval.model_dump(), **update})
    for update in ({"source_request_id": "other"}, {"invocation_id": "other"}):
        mismatched = ApprovalRequest.model_validate({**approval.model_dump(), **update})
        with pytest.raises(ValidationError):
            AgentState(request=agent_request, intent=invocation.intent,
                       status=WorkflowStatus.WAITING_FOR_APPROVAL,
                       invocation=invocation, approval_request=mismatched)


def test_invocation_is_only_typed_metadata(invocation):
    assert invocation.arguments_ref.kind == ReferenceKind.CAPABILITY_ARGUMENTS
    assert not hasattr(invocation, "execute")
    for update in ({"requires_approval": False}, {"capability": lambda: None},
                   {"intent": AgentIntent.UNKNOWN},
                   {"arguments_ref": ref(ReferenceKind.EVENT)}):
        with pytest.raises(ValidationError):
            CapabilityInvocationRequest.model_validate({**invocation.model_dump(), **update})


def test_business_negative_completed_without_agent_error(agent_request):
    negative = ref(ReferenceKind.ELIGIBILITY_RESULT, "eligibility-result-1")
    audit = AuditReferences(results=(negative,), reasons=(
        ReasonReference(result=negative, reason_code="INELIGIBLE"),
    ))
    response = AgentResponse(request_id=agent_request.request_id,
                             intent=AgentIntent.CHECK_ELIGIBILITY,
                             outcome=WorkflowStatus.COMPLETED,
                             message="The referenced result explains the constraints",
                             audit=audit)
    state = AgentState(request=agent_request, intent=response.intent,
                       status=response.outcome, audit=audit, final_response=response)
    assert state.error is None
    assert state.final_response.audit.reasons[0].reason_code == "INELIGIBLE"


def test_failed_response_is_workflow_error(agent_request):
    error = AgentError(code=AgentErrorCode.TOOL_UNAVAILABLE, message="Unavailable")
    response = AgentResponse(request_id=agent_request.request_id,
                             intent=AgentIntent.CHECK_ELIGIBILITY,
                             outcome=WorkflowStatus.FAILED, message="Try later", error=error)
    state = AgentState(request=agent_request, intent=response.intent, status=response.outcome,
                       error=error, final_response=response)
    assert state.error == error
    with pytest.raises(ValidationError):
        AgentError(code="INELIGIBLE", message="Not a workflow error")


def test_route_ready_snapshot_has_no_execution(agent_request):
    state = AgentState(request=agent_request, intent=AgentIntent.CHECK_ELIGIBILITY,
                       status=WorkflowStatus.READY_TO_ROUTE)
    assert state.invocation is None and state.tool_result is None


def test_final_response_cannot_drop_audit_or_mismatch_request(agent_request, audit):
    response = AgentResponse(request_id=agent_request.request_id,
                             intent=AgentIntent.EXPLAIN_REPLANNING,
                             outcome=WorkflowStatus.COMPLETED, message="Explained")
    with pytest.raises(ValidationError):
        AgentState(request=agent_request, intent=response.intent, status=response.outcome,
                   audit=audit, final_response=response)
    wrong_request = AgentResponse.model_validate({
        **response.model_dump(), "request_id": "other",
    })
    with pytest.raises(ValidationError):
        AgentState(request=agent_request, intent=response.intent, status=response.outcome,
                   final_response=wrong_request)


@pytest.mark.parametrize("outcome", list(WorkflowStatus))
def test_response_outcome_payload_is_exclusive(agent_request, outcome):
    payload = dict(request_id=agent_request.request_id, intent=AgentIntent.UNKNOWN,
                   outcome=outcome, message="Interaction")
    if outcome == WorkflowStatus.COMPLETED:
        assert AgentResponse(**payload).error is None
    else:
        with pytest.raises(ValidationError):
            AgentResponse(**payload)


def test_approval_cannot_bind_different_before_plan(agent_request, invocation, approval):
    different = PlanReference.model_validate({
        **approval.before_plan.model_dump(), "version": 2,
    })
    proposal = ApprovalRequest.model_validate({
        **approval.model_dump(), "before_plan": different,
    })
    with pytest.raises(ValidationError):
        AgentState(request=agent_request, intent=invocation.intent,
                   status=WorkflowStatus.WAITING_FOR_APPROVAL,
                   invocation=invocation, approval_request=proposal)


def test_unbound_tool_result_or_pending_approval_cannot_complete(
    agent_request, invocation, approval,
):
    result = ToolResultReference(invocation_id=invocation.invocation_id,
                                result=ToolResult[ResultReference](
                                    success=True, data=ref(ReferenceKind.PLAN_DIFF)))
    response = AgentResponse(request_id=agent_request.request_id,
                             intent=invocation.intent,
                             outcome=WorkflowStatus.COMPLETED, message="Done")
    for extras in ({"tool_result": result},
                   {"tool_result": result, "invocation": invocation,
                    "approval_request": approval}):
        with pytest.raises(ValidationError):
            AgentState(request=agent_request, intent=invocation.intent,
                       status=WorkflowStatus.COMPLETED, final_response=response, **extras)


def test_completed_approved_snapshot_preserves_interaction_trace(
    agent_request, invocation, approval, audit,
):
    response = AgentResponse(request_id=agent_request.request_id,
                             intent=invocation.intent,
                             outcome=WorkflowStatus.COMPLETED, message="Referenced result",
                             audit=audit)
    state = AgentState(
        request=agent_request, intent=invocation.intent, status=response.outcome,
        invocation=invocation, approval_request=approval,
        approval_response=submitted(approval), audit=audit, final_response=response,
        tool_result=ToolResultReference(
            invocation_id=invocation.invocation_id,
            result=ToolResult[ResultReference](
                success=True, data=ref(ReferenceKind.PLAN_DIFF),
            ),
        ),
    )
    assert AgentState.model_validate_json(state.model_dump_json()) == state


def test_contradictory_states_rejected(agent_request, invocation, approval):
    response = AgentResponse(request_id=agent_request.request_id, intent=invocation.intent,
                             outcome=WorkflowStatus.COMPLETED, message="Done")
    cases = [
        {"status": WorkflowStatus.NEEDS_CLARIFICATION},
        {"status": WorkflowStatus.READY_TO_ROUTE},
        {"status": WorkflowStatus.READY_TO_EXECUTE},
        {"status": WorkflowStatus.COMPLETED},
        {"intent": invocation.intent, "status": WorkflowStatus.COMPLETED,
         "invocation": invocation, "approval_request": approval,
         "final_response": response},
        {"approval_response": submitted(approval)},
        {"status": WorkflowStatus.WAITING_FOR_APPROVAL},
        {"error": AgentError(code=AgentErrorCode.MISSING_CONTEXT, message="Missing")},
    ]
    for case in cases:
        with pytest.raises(ValidationError):
            AgentState(request=agent_request, **case)


def test_tool_result_reference_reuses_p4_contract():
    result = ToolResultReference(invocation_id="i", result=ToolResult[ResultReference](
        success=True, data=ref(ReferenceKind.TOOL_RESULT),
    ))
    failure = ToolResultReference(invocation_id="i", result=ToolResult[ResultReference](
        success=False, error=ToolError(code=ToolErrorCode.NOT_FOUND, message="Missing"),
    ))
    assert result.result.success and not failure.result.success
    with pytest.raises(ValidationError):
        ToolResultReference(invocation_id="i", result={"success": True})


def test_reference_order_independence_and_audit_fidelity(audit):
    reordered = AuditReferences(results=tuple(reversed(audit.results)),
                                reasons=tuple(reversed(audit.reasons)))
    assert reordered.model_dump_json() == audit.model_dump_json()
    assert {r.kind for r in audit.results} >= {
        ReferenceKind.EVIDENCE, ReferenceKind.SOURCE, ReferenceKind.EVENT,
        ReferenceKind.REPLANNING_DECISION,
    }
    with pytest.raises(ValidationError):
        AuditReferences(reasons=audit.reasons)
    with pytest.raises(ValidationError):
        AuditReferences(results=audit.results + audit.results)
    with pytest.raises(ValidationError):
        AuditReferences(results=set())


def test_time_is_explicit_aware_and_utc(approval):
    offset = timezone(timedelta(hours=8))
    equivalent = ApprovalRequest.model_validate({
        **approval.model_dump(), "created_at": TIME.astimezone(offset),
    })
    assert equivalent.model_dump_json() == approval.model_dump_json()
    with pytest.raises(ValidationError):
        submitted(approval, submitted_at=datetime(2026, 10, 14))
    payload = approval.model_dump()
    del payload["created_at"]
    with pytest.raises(ValidationError):
        ApprovalRequest.model_validate(payload)


def public_values(agent_request, audit, invocation, approval):
    clarification = ClarificationRequest(
        clarification_id="q", source_request_id=agent_request.request_id,
        reason=ClarificationReason.AMBIGUOUS_INTENT,
        fields=(ContextField.INTENT,), question="Which action?",
    )
    response = AgentResponse(request_id=agent_request.request_id, intent=invocation.intent,
                             outcome=WorkflowStatus.COMPLETED, message="Completed",
                             audit=audit, plan_refs=(agent_request.context.plan_ref,))
    clarification_response = AgentResponse(
        request_id=agent_request.request_id, intent=AgentIntent.UNKNOWN,
        outcome=WorkflowStatus.NEEDS_CLARIFICATION, message="Which action?",
        clarification=clarification,
    )
    approval_response = AgentResponse(
        request_id=agent_request.request_id, intent=invocation.intent,
        outcome=WorkflowStatus.WAITING_FOR_APPROVAL, message="Approval needed",
        approval_request=approval,
    )
    return [agent_request, agent_request.context, audit, *audit.results, *audit.reasons,
            clarification, clarification_response, approval_response,
            approval, submitted(approval), submitted(approval, ApprovalDecision.REJECT),
            invocation,
            AgentState(request=agent_request),
            AgentState(request=agent_request, status=WorkflowStatus.NEEDS_CLARIFICATION,
                       clarification=clarification),
            AgentState(request=agent_request, intent=invocation.intent,
                       status=WorkflowStatus.WAITING_FOR_APPROVAL,
                       invocation=invocation, approval_request=approval),
            AgentState(request=agent_request, intent=invocation.intent,
                       status=WorkflowStatus.READY_TO_EXECUTE, invocation=invocation,
                       approval_request=approval, approval_response=submitted(approval)),
            response,
            ToolResultReference(invocation_id="i", result=ToolResult[ResultReference](
                success=True, data=ref(ReferenceKind.TOOL_RESULT))),
            AgentError(code=AgentErrorCode.MISSING_CONTEXT, message="Missing")]


def test_all_public_boundaries_json_roundtrip_and_determinism(
    agent_request, audit, invocation, approval,
):
    for value in public_values(agent_request, audit, invocation, approval):
        standard_json = json.dumps(value.model_dump(mode="json"))
        reconstructed = type(value).model_validate_json(standard_json)
        assert reconstructed == value
        assert reconstructed.model_dump_json() == value.model_dump_json()
        assert type(value).model_validate_json(value.model_dump_json()) == value
        assert type(value).model_json_schema()


def test_public_values_are_immutable(agent_request, audit, invocation, approval):
    for value in public_values(agent_request, audit, invocation, approval):
        field = next(iter(type(value).model_fields))
        with pytest.raises(ValidationError):
            setattr(value, field, getattr(value, field))
        with pytest.raises(TypeError):
            value.model_copy(update={field: getattr(value, field)})


def test_core_import_independent_of_runtime_and_provider_sdks():
    importlib.import_module("competition_copilot.agents")
    importlib.import_module("competition_copilot.agents.state")
    for module in ("competition_copilot.agents.contracts",
                   "competition_copilot.agents.state"):
        imports = vars(sys.modules[module])
        assert "RequestContext" not in imports
        assert "StateGraph" not in imports
        assert "ChatOpenAI" not in imports


@pytest.mark.parametrize("value", [object(), lambda: None, {"arbitrary": "runtime"}])
def test_runtime_objects_cannot_enter_public_fields(value):
    with pytest.raises(ValidationError):
        AgentRequest(request_id="r", user_message=value)
    with pytest.raises(ValidationError):
        ResultReference(kind=ReferenceKind.TOOL_RESULT, ref_id=value)
