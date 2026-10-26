"""Real explicit Graph/Facade mutations, matching P7 evidence and exposure boundary."""
from unittest.mock import patch

import pytest
from test_generated_huawei_replanning import artifacts
from test_local_cloud_llm import ROOT, Chat, host, invoke, request
from test_profile_runtime import STUDENT, read, update

from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.integrations.local_runtime.composition import create_local_host


def call(target, intent, command=None, student=STUDENT):
    body = request("Explicit skills", {"student_id": student})
    body["request"]["intent"] = intent
    if command is not None:
        body["request"]["skill_command"] = command
    return invoke(target, body)


def test_real_runtime_catalog_add_update_unknown_remove_and_zero_decision_calls():
    chat = Chat(intent_failure=True)
    target = host(chat)
    before = read(target)[1][0]
    calls = []
    original = AgentCapabilityFacade.execute

    def observe(self, invocation, *args, **kwargs):
        calls.append(invocation.capability.value)
        metadata = next(m for m in self.list_capabilities() if m.capability == invocation.capability)
        assert metadata.access == ("READ" if invocation.capability == "get_skill_catalog" else "MUTATING")
        assert not metadata.requires_explicit_approval
        return original(self, invocation, *args, **kwargs)

    with patch.object(AgentCapabilityFacade, "execute", observe):
        values = artifacts(call(target, "GET_SKILL_CATALOG"), "SkillCatalogProjection")[0]
        existing = {s["skill_id"] for s in before["skills"]}
        skill = next(s["skill_id"] for s in values["skills"] if s["skill_id"] not in existing)
        current = before
        for operation, level in [("add", "beginner"), ("update", "intermediate"), ("update", "unknown"), ("remove", None)]:
            command = {"operation": operation, "skill_id": skill, "expected_profile_ref": current["profile_ref"]}
            if level is not None:
                command.update(level=level, note="User note")
            result = call(target, operation.upper() + "_PROFILE_SKILL", command)
            assert result["runtime"]["response"]["outcome"] == "COMPLETED", result
            saved = artifacts(result, "ProfileMutationResult")[0]["profile"]
            assert saved["profile_ref"]["version"] == current["profile_ref"]["version"] + 1
            current = saved
        assert current["skills"] == before["skills"]
    assert calls == ["get_skill_catalog", "add_profile_skill", "update_profile_skill", "update_profile_skill", "remove_profile_skill"]
    assert chat.calls == []


def test_new_p7_consumes_atomic_updated_evidence_and_input_ref():
    target = create_local_host(ROOT)
    before = read(target)[1][0]
    skill = next(s for s in before["skills"] if s["skill_id"] == "mathematical-modeling")
    level = "beginner" if skill["level"] != "beginner" else "advanced"
    saved = artifacts(call(target, "UPDATE_PROFILE_SKILL", {"operation": "update", "skill_id": skill["skill_id"],
        "level": level, "expected_profile_ref": before["profile_ref"]}), "ProfileMutationResult")[0]["profile"]
    body = request("Analyze", {"student_id": STUDENT, "competition_id": "comap-mcm", "edition_id": "comap-mcm-2027"})
    body["request"]["intent"] = "ANALYZE_SKILL_GAP"
    result = invoke(target, body)
    assert result["runtime"]["response"]["outcome"] == "COMPLETED", result
    assert artifacts(result, "SkillGapDecision")
    refs = [target.profile_input_bindings[a["ref"]["ref_id"]] for a in result["presentation"]["artifacts"]
            if a["ref"]["ref_id"] in target.profile_input_bindings]
    assert refs and all(r.input_profile_ref.model_dump(mode="json") == saved["profile_ref"] for r in refs)


@pytest.mark.parametrize("operation", ["add", "update", "remove"])
def test_runtime_mutations_authorized_and_stale_fail_closed(operation):
    target = create_local_host(ROOT)
    before = read(target)[1][0]
    update(target, before, {"major": "Changed"})
    command = {"operation": operation, "skill_id": "mathematical-modeling", "expected_profile_ref": before["profile_ref"]}
    result = call(target, operation.upper() + "_PROFILE_SKILL", command)
    assert "PROFILE_VERSION_CONFLICT" in result["runtime"]["response"]["error"]["message"]
    denied = create_local_host(ROOT, permitted_profile_ids=())
    command["expected_profile_ref"] = denied.profile_repository.get(STUDENT).profile_ref.model_dump(mode="json")
    result = call(denied, operation.upper() + "_PROFILE_SKILL", command)
    assert "PROFILE_EDIT_FORBIDDEN" in result["runtime"]["response"]["error"]["message"]
