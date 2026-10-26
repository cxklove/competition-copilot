"""Explicit profile actions use real Runtime/Graph/Facade; no cloud API."""

from unittest.mock import patch

import pytest
from test_generated_huawei_replanning import artifacts
from test_local_cloud_llm import ROOT, Chat, host, invoke, request

from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.integrations.local_runtime.composition import create_local_host

STUDENT = "local-recommendation-demo"


def read(target, student=STUDENT):
    body = request("Read profile", {"student_id": student})
    body["request"]["intent"] = "GET_PROFILE"
    result = invoke(target, body)
    return result, artifacts(result, "StudentProfileProjection")


def update(target, profile, fields, *, student=STUDENT):
    body = request("Save profile", {"student_id": student})
    body["request"].update(intent="UPDATE_PROFILE", profile_update={
        "expected_profile_ref": profile["profile_ref"], "patch": fields})
    return invoke(target, body)


def test_explicit_read_edit_classification_no_llm_or_business_execution():
    chat = Chat(intent_failure=True)
    target = host(chat)
    calls = []
    original = AgentCapabilityFacade.execute

    def observe(self, invocation, *args, **kwargs):
        metadata = next(m for m in self.list_capabilities() if m.capability == invocation.capability)
        calls.append((invocation.capability, metadata.access, metadata.requires_explicit_approval))
        return original(self, invocation, *args, **kwargs)

    with patch.object(AgentCapabilityFacade, "execute", observe):
        result, values = read(target)
        assert result["runtime"]["response"]["outcome"] == "COMPLETED"
        before = values[0]
        saved = update(target, before, {"major": "Computer Science", "weekly_available_hours": 7.5})
        assert saved["runtime"]["response"]["outcome"] == "COMPLETED", saved
        mutation = artifacts(saved, "ProfileMutationResult")[0]
        assert mutation["profile"]["major"] == "Computer Science"
        assert mutation["profile"]["weekly_available_hours"] == 7.5
        assert mutation["profile"]["skills"] == before["skills"]
        assert not saved["runtime"].get("continuation_ref")
        assert read(target)[1][0] == mutation["profile"]
        conflict = update(target, before, {"major": "Must not win"})
        assert "PROFILE_VERSION_CONFLICT" in conflict["runtime"]["response"]["error"]["message"]
    assert calls == [("get_profile", "READ", False), ("update_profile", "MUTATING", False),
                     ("get_profile", "READ", False), ("update_profile", "MUTATING", False)]
    assert chat.calls == []


def test_authorized_scope_and_missing_student_no_default():
    target = create_local_host(ROOT, permitted_profile_ids=("local-undergraduate",))
    result, _ = read(target)
    assert "PROFILE_EDIT_FORBIDDEN" in result["runtime"]["response"]["error"]["message"]
    result, _ = read(target, "missing-profile")
    assert "PROFILE_NOT_FOUND" in result["runtime"]["response"]["error"]["message"]
    body = request("Read", {})
    body["request"]["intent"] = "GET_PROFILE"
    result = invoke(target, body)
    assert result["runtime"]["response"]["outcome"] == "NEEDS_CLARIFICATION"
    assert not artifacts(result, "StudentProfileProjection")


def test_repository_restart_and_forbidden_update():
    target = create_local_host(ROOT)
    before = read(target)[1][0]
    update(target, before, {"major": "Temporary"})
    assert read(target)[1][0]["major"] == "Temporary"
    restarted = read(create_local_host(ROOT))[1][0]
    assert restarted["major"] == before["major"]
    assert restarted["profile_ref"]["host_scope"] != before["profile_ref"]["host_scope"]
    limited = create_local_host(ROOT, permitted_profile_ids=())
    own_ref = limited.profile_repository.get(STUDENT).profile_ref.model_dump(mode="json")
    denied = update(limited, {"profile_ref": own_ref}, {"major": "Forbidden"})
    assert "PROFILE_EDIT_FORBIDDEN" in denied["runtime"]["response"]["error"]["message"]


@pytest.mark.parametrize("intent", ["GET_RECOMMENDATIONS", "ANALYZE_SKILL_GAP", "BUILD_PLAN"])
def test_preparation_profile_reference_and_single_authoritative_state(intent):
    target = create_local_host(ROOT)
    before = read(target)[1][0]
    saved = update(target, before, {"weekly_available_hours": 7.5})
    expected = artifacts(saved, "ProfileMutationResult")[0]["profile"]["profile_ref"]
    body = request("Explicit analysis", {"student_id": STUDENT, "competition_id": "comap-mcm",
        "edition_id": "comap-mcm-2027"})
    body["request"]["intent"] = intent
    seen = []
    original = AgentCapabilityFacade.execute

    def during(self, invocation, arguments, **kwargs):
        if invocation.capability in ("get_recommendations", "analyze_skill_gap", "build_plan"):
            # Mutate the authoritative repository AFTER preparation, BEFORE completion.
            snap = target.profile_repository.get(STUDENT)
            from competition_copilot.repositories.student import StudentProfileSnapshot
            target.profile_repository.replace(StudentProfileSnapshot.model_validate({
                **snap.domain_profile().model_dump(), "major": "Changed during invocation"}),
                expected=snap.profile_ref, updated_at=snap.updated_at, actor="trusted-test-operator")
            payload = arguments["payload"]
            if invocation.capability == "get_recommendations":
                seen.extend(item["student_profile"]["weekly_available_hours"] for item in payload["contexts"])
            if invocation.capability == "analyze_skill_gap":
                seen.append(payload["context"]["student_profile"]["weekly_available_hours"])
        return original(self, invocation, arguments, **kwargs)

    with patch.object(AgentCapabilityFacade, "execute", during):
        result = invoke(target, body)
    assert result["runtime"]["response"]["outcome"] == "COMPLETED", result
    entries = [a for a in result["presentation"]["artifacts"] if a["ref"]["ref_id"] in target.profile_input_bindings]
    assert entries
    assert all(target.profile_input_bindings[a["ref"]["ref_id"]].input_profile_ref.model_dump(mode="json") == expected for a in entries)
    assert target.profile_repository.get(STUDENT).profile_ref != expected
    assert all(value == 7.5 for value in seen)
    if intent == "BUILD_PLAN":
        entry = next(a for a in entries if a["model"] == "CompetitionPlan")
        assert target.profile_input_bindings[entry["ref"]["ref_id"]].plan_id == entry["value"]["id"]


@pytest.mark.parametrize("fields", [{"skills": []}, {"major": " "}, {"weekly_available_hours": -1},
    {"weekly_available_hours": 169}, {"education_level": "phd"}, {"owner": "attacker"}])
def test_runtime_invalid_patch_safe_error_and_no_mutation(fields):
    target = create_local_host(ROOT)
    before = read(target)[1][0]
    result = update(target, before, fields)
    assert result["runtime"]["error"]["code"] == "INVALID_RUNTIME_PAYLOAD"
    assert read(target)[1][0] == before


def test_natural_language_cannot_authorize_profile_write():
    from test_local_cloud_llm import proposal
    target = host(Chat(proposals=[proposal("UPDATE_PROFILE", "update_profile")]))
    before = target.profile_repository.get(STUDENT)
    result = invoke(target, request("Change my major", {"student_id": STUDENT}))
    assert result["runtime"]["response"]["outcome"] != "COMPLETED"
    assert target.profile_repository.get(STUDENT) == before
