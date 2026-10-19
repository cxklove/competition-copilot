"""Multi-turn NL workflows through the same composed core and Runtime transport."""

from datetime import timedelta

import pytest

pytest.importorskip("langgraph", reason="Install optional agent extra")

from agent_e2e_support import (
    FIX,
    HUMAN,
    OLD,
    P11,
    TIME,
    Harness,
    assert_grounded,
    frame,
    parity,
)
from agent_e2e_support import offline as offline

from competition_copilot.agents.contracts import AgentRequest
from competition_copilot.agents.graph import GraphInput
from competition_copilot.agents.human_contracts import (
    ClarificationOption,
    ClarificationResponse,
    HumanMessage,
    HumanResume,
)
from competition_copilot.agents.state import AgentState
from competition_copilot.domain.replanning import PlanReference


def clarification_frame():
    payload = OLD["EXPLAIN"]["eligibility_payload"]("graduate")
    del payload["competition_id"]
    # Entity choices originate in an actual P4 read, not in the interpreter.
    preparer = Harness(frame({}, "prepare choice"), "DISCOVER_COMPETITIONS", "list_competitions")
    receipt = FIX["call"](preparer.facade, "get_competition", {
        "competition_id": "gcxl-engineering-practice-innovation"})
    option = ClarificationOption(field="COMPETITION", value=receipt.data.competition.id,
        label=receipt.data.competition.name, source_ref=receipt.result_ref)
    return frame(payload, "我能参加吗？", options=(option,))


@pytest.mark.parametrize("language", [False, True])
def test_missing_target_then_structured_or_nl_clarification_runtime_parity(language):
    prepared = clarification_frame()
    local, runtime = [Harness(prepared, "CHECK_ELIGIBILITY", "check_eligibility") for _ in range(2)]
    first = local.agent.start(prepared.state.request)
    transported = runtime.runtime()
    parity(first.response, transported)
    assert first.response.outcome == "NEEDS_CLARIFICATION"
    assert first.response.clarification.fields == ("COMPETITION",)
    assert local.calls == runtime.calls == []
    pending = first.continuation
    if language:
        reply = HumanResume(message=HumanMessage(
            interaction_id=pending.state.clarification.clarification_id,
            source_request_id=prepared.state.request.request_id,
            text=prepared.clarification_options[0].label, submitted_at=TIME))
        key, body = "message", reply.message
    else:
        reply = HUMAN["clarification"](pending, competition_id=prepared.clarification_options[0].value)
        key, body = "clarification", reply.clarification
    completed = local.agent.resume(pending, reply)
    runtime.pending(transported["continuation"])
    result = runtime.runtime({"continuation_ref": "authorized-workflow-ref", key: body.model_dump(mode="json")})
    parity(completed.response, result)
    assert completed.response.outcome == "COMPLETED"
    assert local.calls == runtime.calls == ["check_eligibility"]
    assert local.receipts[0].data.status == "ineligible"
    assert completed.continuation.state.clarification_response
    assert completed.continuation.state.request.context.competition_id == prepared.clarification_options[0].value
    assert any(r.kind == "CLARIFICATION_RESPONSE" for r in completed.response.audit.results)
    assert_grounded(local, completed.response)


def test_wrong_clarification_id_through_both_entries_rejects_without_execution():
    prepared = clarification_frame()
    local, runtime = [Harness(prepared, "CHECK_ELIGIBILITY", "check_eligibility") for _ in range(2)]
    first, transported = local.agent.start(prepared.state.request), runtime.runtime()
    raw = HUMAN["clarification"](first.continuation,
        competition_id=prepared.clarification_options[0].value).clarification.model_dump()
    raw["clarification_id"] = "wrong-question"
    response = ClarificationResponse(**raw)
    result = local.agent.resume(first.continuation, HumanResume(clarification=response))
    runtime.pending(transported["continuation"])
    parity(result.response, runtime.runtime({"continuation_ref": "authorized-workflow-ref",
        "clarification": response.model_dump(mode="json")}))
    assert result.response.outcome == "FAILED" and local.calls == runtime.calls == []


def revision_frame():
    # The frozen P11.5 scenario creates a real P8 Plan and controlled (not official)
    # track-removal Event. Exercise P11.2/P11.3 through the composed facade as well.
    context = P11["real_context"].__wrapped__()
    before, student, _ = context
    setup = Harness(frame({}, "prepare controlled revision"), "DISCOVER_COMPETITIONS", "list_competitions")
    event = P11["controlled_event"](context, "replan")
    impact = FIX["call"](setup.facade, "analyze_event_impact", {
        "event": event, "student": student, "plan": before, "evaluated_at": P11["EVALUATED"]})
    decision = FIX["call"](setup.facade, "decide_replanning", {
        "impacts": [impact.data], "plan": before, "evaluated_at": P11["DECIDED"]})
    assert impact.data.outcome == "affects_plan" and decision.data.outcome == "replan"
    # Existing caller-authorized structured instruction; Agent must still collect
    # explicit current approval before the P12.5 authority bridge can execute it.
    source = P11["authorized_cancellation"](before, decision.data)
    prepared = frame({"before": before, "replanning_input": source,
        "executed_at": P11["EXECUTED"].isoformat()}, "根据这次赛道移除调整计划", context={
            "plan_ref": PlanReference.from_plan(before)})
    prepared = GraphInput(**{**prepared.model_dump(),
        "approval_request_id": "e2e-request/approval", "interaction_created_at": TIME + timedelta(minutes=1)})
    return prepared, before, source


@pytest.mark.parametrize("answer", ["APPROVE", "REJECT"])
@pytest.mark.parametrize("explanation", ["valid", "error"])
def test_real_event_replan_explicit_approval_and_reject_e2e_parity(answer, explanation):
    prepared, before, source = revision_frame()
    original = before.model_dump_json()
    local, runtime = [Harness(prepared, "REQUEST_PLAN_REVISION", "revise_plan", explanation=explanation) for _ in range(2)]
    pending, transported = local.agent.start(prepared.state.request), runtime.runtime()
    parity(pending.response, transported)
    assert pending.response.outcome == "WAITING_FOR_APPROVAL"
    assert local.calls == runtime.calls == [] and before.status == "active"
    q = pending.response.approval_request
    assert q.decision_ref and q.affected_scope_ref and q.resolution_ref and q.instruction_refs
    reply = HUMAN["approval"](pending.continuation, answer)
    completed = local.agent.resume(pending.continuation, reply)
    execution = {k: v for k, v in reply.model_dump().items()
        if k in ("current_plan", "approved_by_ref", "executed_at")}
    runtime.pending(transported["continuation"], execution)
    result = runtime.runtime({"continuation_ref": "authorized-workflow-ref",
        "approval": reply.approval.model_dump(mode="json")})
    parity(completed.response, result)
    assert completed.response.outcome == "COMPLETED"
    assert before.model_dump_json() == original and before.status == "active"
    expected = ["revise_plan"] if answer == "APPROVE" else []
    assert local.calls == runtime.calls == expected
    kinds = {r.kind for r in completed.response.audit.results}
    assert {"APPROVAL_REQUEST", "APPROVAL_RESPONSE", "REPLANNING_DECISION"} <= kinds
    if answer == "APPROVE":
        receipt = local.receipts[0]
        assert receipt.data.after.status == "cancelled"
        assert receipt.data.plan_diff.before == before
        assert receipt.data.plan_diff.status_change and "PLAN_DIFF" in kinds and "AUTHORITY" in kinds
        assert receipt.data.plan_diff.decision == source.decision
        assert receipt.data.plan_diff.trigger_event_ids == source.decision.trigger_event_ids
        authorized = receipt.data.replanning_input.plan_status_instruction.authority
        assert authorized.approval_ref == q.approval_request_id
        assert authorized.approved_at == reply.approval.submitted_at
        assert authorized.instruction_source_ref.endswith(reply.approval.submitted_at.isoformat())
        assert receipt.model_dump_json() == runtime.receipts[0].model_dump_json()
        assert completed.continuation.state.approval_response == reply.approval
        assert source.decision.trigger_event_ids
        assert "status active -> cancelled" in completed.response.message
    else:
        assert "PLAN_DIFF" not in kinds and not local.receipts
    if explanation == "valid" and answer == "APPROVE":
        assert_grounded(local, completed.response)
    if explanation == "valid":
        assert local.explanation.contexts[-1] == runtime.explanation.contexts[-1]
        assert local.explanation.drafts[-1] == runtime.explanation.drafts[-1]
        assert local.explanation.contexts[-1].authoritative_status == (
            "REVISION_COMPLETED" if answer == "APPROVE" else "REJECTED")


@pytest.mark.parametrize("case", ["wrong_id", "cross_request", "stale"])
def test_approval_rejection_boundaries_complete_local_runtime_chain(case):
    prepared, before, _ = revision_frame()
    local, runtime = [Harness(prepared, "REQUEST_PLAN_REVISION", "revise_plan") for _ in range(2)]
    pending, transported = local.agent.start(prepared.state.request), runtime.runtime()
    reply = HUMAN["approval"](pending.continuation)
    raw = reply.model_dump()
    if case == "wrong_id":
        raw["approval"]["approval_request_id"] = "wrong-action"
    elif case == "cross_request":
        raw["approval"]["source_request_id"] = "other-request"
    else:
        raw["current_plan"]["version"] += 1
    reply = HumanResume(**raw)
    completed = local.agent.resume(pending.continuation, reply)
    execution = {k: v for k, v in reply.model_dump().items()
        if k in ("current_plan", "approved_by_ref", "executed_at")}
    runtime.pending(transported["continuation"], execution)
    result = runtime.runtime({"continuation_ref": "authorized-workflow-ref",
        "approval": reply.approval.model_dump(mode="json")})
    parity(completed.response, result)
    assert completed.response.outcome == "FAILED"
    assert local.calls == runtime.calls == [] and before.status == "active"


def test_public_request_entry_rejects_preparer_overwrite():
    prepared = clarification_frame()
    harness = Harness(prepared, "CHECK_ELIGIBILITY", "check_eligibility")
    other = AgentRequest(**{**prepared.state.request.model_dump(), "user_message": "different caller request"})
    with pytest.raises(ValueError, match="preserve"):
        harness.agent.invoke(other)
    assert harness.calls == []
    restored = GraphInput.model_validate_json(prepared.model_dump_json())
    assert restored.model_dump_json() == prepared.model_dump_json()
    assert isinstance(restored.state, AgentState)
