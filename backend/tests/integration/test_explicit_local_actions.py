"""Explicit user operations use the real graph/Facade, never cloud intent inference."""

from unittest.mock import patch

import pytest
from test_generated_huawei_replanning import artifacts
from test_local_cloud_llm import NOW, Chat, count, host, invoke, request

from competition_copilot.agents.capabilities import AgentCapabilityFacade

CONTEXT = {"student_id": "local-recommendation-demo", "competition_id": "comap-mcm",
           "edition_id": "comap-mcm-2027"}


def action(intent, context=CONTEXT, identity="explicit"):
    body = request("unrelated text must not select the operation", context, identity)
    body["request"]["intent"] = intent
    return body


def approval(pending, choice):
    question = pending["runtime"]["response"]["approval_request"]
    return {"continuation_ref": pending["runtime"]["continuation_ref"], "approval": {
        "approval_request_id": question["approval_request_id"],
        "source_request_id": question["source_request_id"], "decision": choice,
        "submitted_at": NOW.isoformat()}}


@pytest.mark.parametrize("intent,capability,model", [
    ("CHECK_ELIGIBILITY", "check_eligibility", "EligibilityDecision"),
    ("GET_RECOMMENDATIONS", "get_recommendations", "RecommendationRankingResult"),
    ("ANALYZE_SKILL_GAP", "analyze_skill_gap", "SkillGapDecision"),
    ("BUILD_PLAN", "build_plan", "CompetitionPlan"),
])
def test_explicit_actions_reach_real_facade_even_when_intent_model_fails(intent, capability, model):
    chat = Chat(intent_failure=True)
    target = host(chat)
    calls = []
    execute = AgentCapabilityFacade.execute

    def record(self, invocation, *args, **kwargs):
        calls.append(invocation.capability)
        return execute(self, invocation, *args, **kwargs)

    with patch.object(AgentCapabilityFacade, "execute", record):
        result = invoke(target, action(intent))
    assert result["runtime"]["response"]["intent"] == intent
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    assert len(artifacts(result, model)) == 1
    assert calls.count(capability) == 1
    if intent == "BUILD_PLAN":
        assert calls.index("analyze_skill_gap") < calls.index("build_plan")
    if intent == "GET_RECOMMENDATIONS":
        assert calls.count("check_eligibility") == 12
    assert count(chat, "IntentRoutingProposal") == 0
    assert target.handler_invocations == 1


def test_missing_context_still_requires_backend_clarification_without_inference():
    chat = Chat(intent_failure=True)
    result = invoke(host(chat), action("CHECK_ELIGIBILITY", {}))
    response = result["runtime"]["response"]
    assert response["outcome"] == "NEEDS_CLARIFICATION"
    assert set(response["clarification"]["fields"]) == {"STUDENT_PROFILE", "COMPETITION", "EDITION"}
    assert count(chat, "IntentRoutingProposal") == 0


def test_explicit_revision_keeps_exact_registry_binding_approval_and_replay_guards():
    chat = Chat(intent_failure=True)
    target = host(chat)
    context = {**CONTEXT, "competition_id": "huawei-ict", "edition_id": "huawei-ict-2026",
               "track_id": "huawei-ict-2026-innovation"}
    generated = invoke(target, action("BUILD_PLAN", context, "build"))
    ref = generated["runtime"]["response"]["plan_refs"][0]
    selected = {**context, "plan_ref": ref}
    pending = invoke(target, action("REQUEST_PLAN_REVISION", selected, "reject"))
    assert pending["runtime"]["response"]["outcome"] == "WAITING_FOR_APPROVAL"
    assert pending["runtime"]["response"]["approval_request"]["before_plan"] == ref
    assert not artifacts(pending, "PlanDiff")
    rejected = invoke(target, approval(pending, "REJECT"))
    assert rejected["runtime"]["response"]["outcome"] == "COMPLETED"
    assert not artifacts(rejected, "PlanDiff")
    pending = invoke(target, action("REQUEST_PLAN_REVISION", selected, "approve"))
    body = approval(pending, "APPROVE")
    approved = invoke(target, body)
    diff = artifacts(approved, "PlanDiff")[0]
    assert diff["before"]["id"] == ref["plan_id"]
    assert diff["after"]["version"] == ref["version"] + 1
    assert diff["after"]["status"] == "cancelled"
    assert invoke(target, body)["runtime"]["error"]["code"] == "CORE_VALIDATION_ERROR"
    assert invoke(target, action("REQUEST_PLAN_REVISION", selected, "stale"))["runtime"]["error"]["code"] == "CORE_VALIDATION_ERROR"
    assert count(chat, "IntentRoutingProposal") == 0


def test_chat_without_explicit_intent_still_calls_cloud_once_and_fails_closed():
    chat = Chat(intent_failure=True)
    result = invoke(host(chat), request("please analyze my skills", CONTEXT))
    assert result["runtime"]["response"]["message"] == "INTENT_MODEL_FAILED"
    assert count(chat, "IntentRoutingProposal") == 1


@pytest.mark.parametrize("intent", ["APPROVE_PLAN_REVISION", "REJECT_PLAN_REVISION", "UNKNOWN"])
def test_explicit_operation_cannot_supply_approval_or_fallback_to_model(intent):
    chat = Chat(intent_failure=True)
    result = invoke(host(chat), action(intent))
    assert result["runtime"]["response"]["outcome"] != "COMPLETED"
    assert not artifacts(result, "PlanDiff")
    assert count(chat, "IntentRoutingProposal") == 0


def test_invalid_intent_and_forged_authority_rejected_before_handler():
    target = host(Chat(intent_failure=True))
    for fields in ({"intent": "FAKE_ACTION"}, {"intent": "BUILD_PLAN", "approved_by_ref": "forged"}):
        body = request("build", CONTEXT)
        body["request"].update(fields)
        assert invoke(target, body)["runtime"]["error"]["code"] == "INVALID_RUNTIME_PAYLOAD"
    assert target.handler_invocations == 0
