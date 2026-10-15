"""Deterministic continuation/consent and P11 authority binding; no services/IO."""

import json
import unicodedata

from competition_copilot.agents.contracts import (
    AgentContext,
    AgentIntent,
    AgentRequest,
    ApprovalRequest,
    ApprovalResponse,
    AuditReferences,
    ClarificationRequest,
    ContextField,
    ReasonReference,
    ResultReference,
)
from competition_copilot.agents.human_contracts import (
    ClarificationResolutionProposal,
    ClarificationResponse,
    ClarificationValues,
    HumanMessage,
)
from competition_copilot.agents.state import AgentState
from competition_copilot.domain.replanning import PlanReference
from competition_copilot.domain.replanning_input import (
    ReplanningInput,
    RevisionAuthority,
    replanning_decision_fingerprint,
)


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).strip().casefold().split())


# Complete-message allowlists, never substring or model-inferred consent.
_APPROVE = frozenset(("确认", "确认执行", "同意", "同意执行", "同意执行这个修改",
                      "approve", "yes, approve", "confirm", "yes, approve this change"))
_REJECT = frozenset(("取消", "不同意", "不要执行", "reject", "no", "cancel"))


def explicit_approval_response(pending: ApprovalRequest, message: HumanMessage) -> ApprovalResponse | None:
    if (message.interaction_id != pending.approval_request_id
        or message.source_request_id != pending.source_request_id
        or message.submitted_at < pending.created_at):
        raise ValueError("Approval reply does not bind pending request")
    text = _normalized(message.text)
    if text not in _APPROVE and text not in _REJECT:
        return None
    return ApprovalResponse(approval_request_id=pending.approval_request_id,
        source_request_id=pending.source_request_id, decision="APPROVE" if text in _APPROVE else "REJECT",
        submitted_at=message.submitted_at)


def _parse_arguments(text: str | None) -> dict:
    def reject(value):
        raise ValueError("Non-finite JSON constant")
    value = {} if text is None else json.loads(text, parse_constant=reject)
    if not isinstance(value, dict):
        raise ValueError("Expected structured argument envelope")
    return value


def _fill_only(before, supplied):
    if before is None:
        return supplied
    if isinstance(before, dict) and isinstance(supplied, dict):
        result = dict(before)
        for key, value in supplied.items():
            result[key] = _fill_only(before.get(key), value)
        return result
    if before != supplied:
        raise ValueError("Clarification cannot overwrite existing context")
    return before


def resolve_clarification(state: AgentState, response: ClarificationResponse,
                          arguments: dict | None, artifact_ref: ResultReference | None):
    question = state.clarification
    if state.status != "NEEDS_CLARIFICATION" or question is None:
        raise ValueError("No pending clarification")
    if (response.clarification_id != question.clarification_id
        or response.source_request_id != state.request.request_id):
        raise ValueError("Clarification reply belongs to another interaction")
    fields = response.values.provided_fields
    if not set(fields).issubset(question.fields):
        raise ValueError("Only requested clarification fields may be supplied")
    args = dict(arguments or {})
    if artifact_ref is not None:
        args = _fill_only(args, {"artifact_ref": artifact_ref.model_dump(mode="json")})
    values = response.values
    if values.arguments_json is not None:
        args = _fill_only(args, _parse_arguments(values.arguments_json))
    payload = args.get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError("Invalid pending payload")
    additions = {name: getattr(values, name) for name in ("competition_id", "edition_id", "track_id")
                 if getattr(values, name) is not None}
    if values.student is not None:
        additions["student"] = values.student.model_dump(mode="json", exclude_unset=True)
    args["payload"] = _fill_only(payload, additions)
    context = state.request.context.model_dump(mode="json")
    if values.competition_id is not None:
        context = _fill_only(context, {"competition_id": values.competition_id})
    if values.edition_id is not None and context.get("competition_id") is not None:
        context = _fill_only(context, {"edition_id": values.edition_id})
    if values.track_id is not None and context.get("edition_id") is not None:
        context = _fill_only(context, {"track_id": values.track_id})
    if values.student is not None:
        context = _fill_only(context, {"student_id": values.student.id})
    if values.plan_ref is not None:
        context = _fill_only(context, {"plan_ref": values.plan_ref.model_dump(mode="json")})
    request = AgentRequest(**{**state.request.model_dump(), "context": AgentContext.model_validate(context)})
    intent = state.intent
    if values.intent is not None:
        if intent != AgentIntent.UNKNOWN and intent != values.intent:
            raise ValueError("Clarification cannot replace explicit intent")
        intent = values.intent
    invocation = state.invocation
    if values.invocation is not None:
        if invocation is not None and invocation != values.invocation:
            raise ValueError("Clarification cannot replace explicit invocation")
        invocation = values.invocation
    remaining = tuple(f for f in question.fields if f not in fields)
    pending = (ClarificationRequest(**{**question.model_dump(), "fields": remaining,
                "question": "Provide explicit structured context: " + ", ".join(f.value for f in remaining)})
               if remaining else None)
    result = AgentState(**{**state.model_dump(), "request": request, "intent": intent,
        "invocation": invocation, "clarification": pending, "clarification_response": response,
        "status": "NEEDS_CLARIFICATION" if pending else "RECEIVED"})
    return result, args


def validate_language_clarification(message, question, proposal, options):
    proposal = ClarificationResolutionProposal.model_validate(proposal)
    if (message.interaction_id != question.clarification_id
        or message.source_request_id != question.source_request_id
        or proposal.clarification_id != question.clarification_id
        or proposal.source_request_id != question.source_request_id):
        raise ValueError("Language proposal belongs to another interaction")
    if proposal.ambiguous or not proposal.selections:
        return None
    matching = [o for o in options if _normalized(o.label) == _normalized(message.text)]
    keys = {(o.field, o.value) for o in matching}
    selected = {(s.field, s.value) for s in proposal.selections}
    if len(selected) != len(proposal.selections) or selected != keys:
        return None
    if len({s.field for s in proposal.selections}) != len(selected):
        return None  # Multiple possible IDs for one field must not be guessed.
    names = {ContextField.COMPETITION: "competition_id", ContextField.EDITION: "edition_id",
             ContextField.TRACK: "track_id"}
    if any(s.field not in question.fields or s.field not in names for s in proposal.selections):
        raise ValueError("Language response can only select requested read-result choices")
    return ClarificationResponse(clarification_id=question.clarification_id,
        source_request_id=question.source_request_id, submitted_at=message.submitted_at,
        values=ClarificationValues(**{names[s.field]: s.value for s in proposal.selections}))


def _ref(kind, value):
    return ResultReference(kind=kind, ref_id=value)


def prepare_approval(source: ReplanningInput, request, invocation, *, approval_request_id, created_at):
    """Project an existing formal caller proposal, never manufacture prior authority."""
    source = ReplanningInput.model_validate(source)
    if source.status != "executable" or source.decision.outcome != "replan":
        raise ValueError("Only executable REPLAN operations request mutation approval")
    if invocation is None or invocation.capability != "revise_plan" or not invocation.requires_approval:
        raise ValueError("Approval must bind the mutating invocation")
    reference = PlanReference.from_plan(source.before)
    if request.context.plan_ref != reference or created_at < source.supplied_at:
        raise ValueError("Proposal must bind exact current Plan and explicit preparation time")
    decision_ref = _ref("REPLANNING_DECISION", replanning_decision_fingerprint(source.decision))
    refs = [decision_ref, _ref("EVIDENCE", source.id + "#/decision/impacts")]
    refs.extend(_ref("EVENT", event_id) for event_id in source.decision.trigger_event_ids)
    audit = AuditReferences(results=tuple(refs), reasons=tuple(ReasonReference(
        result=decision_ref, reason_code=r.value) for r in source.decision.reason_codes))
    instructions = (*source.instructions, *((source.plan_status_instruction,) if source.plan_status_instruction else ()))
    operations = "; ".join(
        f"status {i.expected_before_status.value} -> {i.desired_after_status.value}"
        if i.operation == "update_plan_status" else
        f"milestone {i.target_milestone_id}: due_at {i.expected_before.due_at} -> {i.after.due_at}"
        for i in instructions)
    return ApprovalRequest(approval_request_id=approval_request_id, source_request_id=request.request_id,
        invocation_id=invocation.invocation_id, action="PLAN_REVISION", before_plan=reference,
        summary=f"Plan {reference.plan_id}, version {reference.version}: {operations}",
        decision_ref=decision_ref, affected_scope_ref=_ref("AFFECTED_SCOPE", source.id + "#/decision/scope"),
        resolution_ref=None if source.scope_resolution is None else _ref("SCOPE_RESOLUTION", source.scope_resolution.id),
        proposed_input_ref=_ref("REPLANNING_INPUT", source.id),
        instruction_refs=tuple(_ref("REVISION_INSTRUCTION", i.id) for i in instructions),
        audit=audit, created_at=created_at)


def validate_pending_revision(pending, source, request, invocation):
    """Shared entry/resume preconditions: executable REPLAN and exact binding.

    An existing interaction is a candidate, never proof of current validity.
    Canonical projection reads P11 results without recomputing Decision or scope.
    """
    expected = prepare_approval(source, request, invocation,
        approval_request_id=pending.approval_request_id, created_at=pending.created_at)
    if pending != expected:
        raise ValueError("Approval scope/input/Decision/Plan references changed")


def validate_explicit_approval(pending, response, source, request, invocation, current_plan):
    validate_pending_revision(pending, source, request, invocation)
    if (response.approval_request_id != pending.approval_request_id
        or response.source_request_id != pending.source_request_id
        or response.submitted_at < pending.created_at):
        raise ValueError("Approval must match exact pending interaction")
    if response.decision == "APPROVE" and current_plan != pending.before_plan:
        raise ValueError("Approval is stale: exact current Plan reference required")


def build_approved_replanning_input(pending, response, source, request, invocation, *,
                                    current_plan, approved_by_ref):
    """Rebind authority and its dependent IDs only; P11 validates all semantics."""
    validate_explicit_approval(pending, response, source, request, invocation, current_plan)
    if response.decision != "APPROVE" or not approved_by_ref:
        raise ValueError("Explicit APPROVE and trusted caller actor are required")
    authority = RevisionAuthority(kind="human_approved", approval_ref=pending.approval_request_id,
        approved_by_ref=approved_by_ref,
        instruction_source_ref=pending.approval_request_id + "/response/" + response.submitted_at.isoformat(),
        approved_at=response.submitted_at)
    updates = tuple(type(i)(**{**i.model_dump(), "authority": authority}) for i in source.instructions)
    status = source.plan_status_instruction
    if status is not None:
        status = type(status)(**{**status.model_dump(), "authority": authority})
    resolution = source.scope_resolution
    if resolution is not None:
        resolution = type(resolution)(**{**resolution.model_dump(), "authority": authority,
            "instruction_ids": tuple(i.id for i in (*updates, *((status,) if status else ())))})
    return ReplanningInput(**{**source.model_dump(), "supplied_at": response.submitted_at,
        "instructions": updates, "plan_status_instruction": status, "scope_resolution": resolution})
