"""Explicit Workspace reads never invoke decision/planning/mutation authorities."""

import json
from copy import deepcopy
from unittest.mock import patch

import pytest
from test_generated_huawei_replanning import artifacts
from test_local_cloud_llm import ROOT, Chat, host, invoke, request
from test_profile_freshness_runtime import generate
from test_profile_runtime import STUDENT, read, update

from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.integrations.local_runtime.composition import create_local_host


def workspace(target, context=None):
    body = request("Read workspace", context or {"student_id": STUDENT,
        "competition_id": "comap-mcm", "edition_id": "comap-mcm-2027"})
    body["request"]["intent"] = "GET_PLANNING_WORKSPACE"
    return invoke(target, body)


def test_no_llm_no_decision_execution_and_explicit_read_metadata(monkeypatch):
    chat = Chat(intent_failure=True)
    target = host(chat)
    executed = []
    original = AgentCapabilityFacade.execute

    def observe(self, invocation, *args, **kwargs):
        executed.append(invocation.capability.value)
        return original(self, invocation, *args, **kwargs)

    monkeypatch.setattr(AgentCapabilityFacade, "execute", observe)
    result = workspace(target)
    assert result["runtime"]["response"]["outcome"] == "COMPLETED", result
    value = artifacts(result, "PlanningWorkspaceProjection")[0]
    assert value["section_availability"]["plan"] == "NOT_SELECTED"
    assert value["preparation_suggestions"]
    assert executed == ["get_planning_workspace"] and not chat.calls
    metadata = next(m for m in AgentCapabilityFacade().list_capabilities() if m.capability == "get_planning_workspace")
    assert metadata.access == "READ" and not metadata.requires_explicit_approval


def test_exact_registered_plan_current_then_stale_and_current_advisory():
    target = create_local_host(ROOT)
    generated = generate(target, "BUILD_PLAN")
    original = deepcopy(artifacts(generated, "CompetitionPlan")[0])
    reference = generated["runtime"]["response"]["plan_refs"][0]
    context = {"student_id": STUDENT, "competition_id": "comap-mcm",
        "edition_id": "comap-mcm-2027", "plan_ref": reference}
    executed = []
    execute = AgentCapabilityFacade.execute

    def observe(self, invocation, *args, **kwargs):
        executed.append(invocation.capability.value)
        return execute(self, invocation, *args, **kwargs)

    with patch.object(AgentCapabilityFacade, "execute", observe):
        current = artifacts(workspace(target, context), "PlanningWorkspaceProjection")[0]
    assert executed == ["get_planning_workspace"]
    assert current["plan_ref"] == reference
    assert json.loads(current["plan_original_json"]) == original
    assert any(c["field"] == "mathematical-modeling" and c["value"] == "Mathematical Modeling"
               for c in current["confirmed_constraints"])
    assert len(current["preparation_suggestions"]) == 3
    assert all(t["source_basis"]["skill_id"] == "mathematical-modeling"
               for t in current["preparation_suggestions"])
    assert any("REQUIREMENT_PROFICIENCY_UNSPECIFIED" in p["reason_codes"]
               for p in current["pending_confirmations"])
    assert any(t["kind"] == "VERIFIED" and t["value"] for t in current["time_references"])
    assert current["plan_freshness"]["status"] == "CURRENT"
    profile = read(target)[1][0]
    update(target, profile, {"weekly_available_hours": 7.5})
    stale_result = workspace(target, context)
    stale = artifacts(stale_result, "PlanningWorkspaceProjection")[0]
    assert stale["plan_freshness"]["status"] == "STALE"
    assert stale["plan_input_profile_ref"] != stale["current_profile_ref"]
    assert all(t["profile_ref"] == stale["current_profile_ref"] for t in stale["preparation_suggestions"])
    assert target.plan_registry.resolve(current_plan_ref(reference)).model_dump(mode="json") == original
    assert not target.plan_registry.revisions(original["id"])
    assert not artifacts(stale_result, "PlanDiff")
    assert not artifacts(stale_result, "CompetitionEvent")


def current_plan_ref(value):
    from competition_copilot.domain.replanning import PlanReference
    return PlanReference.model_validate(value)


@pytest.mark.parametrize("context", [
    {"student_id": STUDENT},
    {"competition_id": "comap-mcm"},
    {"student_id": "not-authorized", "competition_id": "comap-mcm"},
    {"student_id": STUDENT, "competition_id": "comap-mcm", "edition_id": "huawei-ict-2026"},
])
def test_unavailable_or_invalid_context_is_never_auto_filled(context):
    target = create_local_host(ROOT)
    result = workspace(target, context)
    assert result["runtime"]["response"]["outcome"] != "COMPLETED"
    assert not artifacts(result, "PlanningWorkspaceProjection")


def test_local_agentarts_workspace_semantic_parity_without_cross_host_ref_equality():
    from test_agentarts_transport import HARNESS, post

    body = {"request": {"request_id": "workspace-parity", "user_message": "Read workspace",
        "intent": "GET_PLANNING_WORKSPACE", "context": {"student_id": STUDENT,
            "competition_id": "comap-mcm", "edition_id": "comap-mcm-2027"}}}
    with HARNESS["running"]() as env:
        left_status, left = post(env["local"], body, path="/runtime/invoke")
        right_status, right = post(env["bridge"], body)
    assert left_status == right_status == 200
    a = artifacts(left, "PlanningWorkspaceProjection")[0]
    b = artifacts(right, "PlanningWorkspaceProjection")[0]
    for name in ("target", "profile_context", "confirmed_constraints", "pending_confirmations", "time_references", "section_availability"):
        assert a[name] == b[name]
    assert [t["title"] for t in a["preparation_suggestions"]] == [t["title"] for t in b["preparation_suggestions"]]
    for projection in (a, b):
        assert all(t["profile_ref"] == projection["current_profile_ref"] for t in projection["preparation_suggestions"])
