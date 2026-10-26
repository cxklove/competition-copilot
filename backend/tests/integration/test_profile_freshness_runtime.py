"""Shared Runtime lineage, edits, explicit reruns, history retention and races."""
from copy import deepcopy
from unittest.mock import patch

import pytest
from test_generated_huawei_replanning import artifacts
from test_local_cloud_llm import ROOT, Chat, host, invoke, request
from test_profile_runtime import STUDENT, read, update
from test_profile_skill_runtime import call

from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.integrations.local_runtime.composition import create_local_host
from competition_copilot.repositories.student import StudentProfileSnapshot

CONTEXT = {"student_id": STUDENT, "competition_id": "comap-mcm", "edition_id": "comap-mcm-2027"}
CASES = [("GET_RECOMMENDATIONS", "RecommendationRankingResult"),
         ("ANALYZE_SKILL_GAP", "SkillGapDecision"), ("BUILD_PLAN", "CompetitionPlan")]


def generate(target, intent):
    context = {"student_id": STUDENT} if intent == "GET_RECOMMENDATIONS" else CONTEXT
    body = request("Explicit analysis", context)
    body["request"]["intent"] = intent
    value = invoke(target, body)
    assert value["runtime"]["response"]["outcome"] == "COMPLETED", value
    return value


def freshness(target, identities, student=STUDENT):
    body = request("Read input versions", {**CONTEXT, "student_id": student})
    body["request"].update(intent="GET_PROFILE_ANALYSES", profile_result_refs=identities)
    value = invoke(target, body)
    assert value["runtime"]["response"]["outcome"] == "COMPLETED", value
    return artifacts(value, "ProfileAnalysesProjection")[0]["analyses"]


@pytest.mark.parametrize("intent,model", CASES)
@pytest.mark.parametrize("mutation", ["profile", "skill_add", "skill_update", "skill_remove"])
def test_current_edit_stale_preserved_and_explicit_rerun(intent, model, mutation):
    target = create_local_host(ROOT)
    result = generate(target, intent)
    entry = next(a for a in result["presentation"]["artifacts"] if a["model"] == model)
    identity, original = entry["ref"]["ref_id"], deepcopy(entry["value"])
    old = read(target)[1][0]
    assert freshness(target, [identity])[0]["profile_freshness"]["status"] == "CURRENT"
    if mutation == "profile":
        update(target, old, {"major": "Changed"})
    else:
        operation = mutation.split("_")[1]
        skill = "mathematical-modeling"
        if operation == "add":
            catalog = artifacts(call(target, "GET_SKILL_CATALOG"), "SkillCatalogProjection")[0]
            existing = {s["skill_id"] for s in old["skills"]}
            skill = next(s["skill_id"] for s in catalog["skills"] if s["skill_id"] not in existing)
        command = {"operation": operation, "skill_id": skill, "expected_profile_ref": old["profile_ref"]}
        if operation != "remove":
            command["level"] = "advanced"
        saved = call(target, operation.upper() + "_PROFILE_SKILL", command)
        assert saved["runtime"]["response"]["outcome"] == "COMPLETED", saved
    assert freshness(target, [identity])[0]["profile_freshness"]["status"] == "STALE"
    assert entry["value"] == original  # score/rank/gap/status/version unchanged
    if model == "CompetitionPlan":
        binding = target.profile_input_bindings[identity]
        assert target.plan_registry.resolve(binding.plan_ref).model_dump(mode="json") == original
        assert target.plan_registry.revisions(original["id"]) == ()
    # Explicit rerun alone creates a new decision/plan and uses the new ref.
    rerun = generate(target, intent)
    new_entry = next(a for a in rerun["presentation"]["artifacts"] if a["model"] == model)
    statuses = freshness(target, [identity, new_entry["ref"]["ref_id"]])
    assert [a["profile_freshness"]["status"] for a in statuses] == ["STALE", "CURRENT"]
    assert statuses[1]["profile_freshness"]["input_profile_ref"] == read(target)[1][0]["profile_ref"]


@pytest.mark.parametrize("intent,model", CASES)
def test_race_retains_preparation_reference_and_reads_stale(intent, model):
    target = create_local_host(ROOT)
    expected = target.profile_repository.get(STUDENT).profile_ref
    original = AgentCapabilityFacade.execute

    def during(self, invocation, *args, **kwargs):
        if invocation.capability in ("get_recommendations", "analyze_skill_gap", "build_plan"):
            current = target.profile_repository.get(STUDENT)
            target.profile_repository.replace(StudentProfileSnapshot.model_validate({
                **current.domain_profile().model_dump(), "major": "Edited while executing"}),
                expected=current.profile_ref, actor="test-operator", updated_at=current.updated_at)
        return original(self, invocation, *args, **kwargs)

    with patch.object(AgentCapabilityFacade, "execute", during):
        result = generate(target, intent)
    entry = next(a for a in result["presentation"]["artifacts"] if a["model"] == model)
    value = freshness(target, [entry["ref"]["ref_id"]])[0]["profile_freshness"]
    assert value["status"] == "STALE"
    assert value["input_profile_ref"] == expected.model_dump(mode="json")


def test_legacy_restart_identity_and_zero_llm_or_business_calls_on_read():
    chat = Chat(intent_failure=True)
    target = host(chat)
    generated = generate(target, "GET_RECOMMENDATIONS")
    identity = next(a["ref"]["ref_id"] for a in generated["presentation"]["artifacts"] if a["model"] == "RecommendationRankingResult")
    chat.calls.clear()
    calls = []
    original = AgentCapabilityFacade.execute

    def observe(self, invocation, *args, **kwargs):
        calls.append(invocation.capability.value)
        return original(self, invocation, *args, **kwargs)

    with patch.object(AgentCapabilityFacade, "execute", observe):
        assert freshness(target, [identity, "legacy-result"])[1]["profile_freshness"]["status"] == "UNKNOWN"
    assert calls == ["get_profile_analyses"] and not chat.calls
    assert freshness(target, [identity], "local-graduate") == []
    restarted = create_local_host(ROOT)
    assert freshness(restarted, [identity])[0]["profile_freshness"]["status"] == "UNKNOWN"


@pytest.mark.parametrize("intent,model", CASES[1:])
def test_query_target_and_selected_plan_must_match_exactly(intent, model):
    target = create_local_host(ROOT)
    result = generate(target, intent)
    identity = next(a["ref"]["ref_id"] for a in result["presentation"]["artifacts"] if a["model"] == model)
    body = request("Read wrong target", {**CONTEXT, "track_id": "different-track"})
    body["request"].update(intent="GET_PROFILE_ANALYSES", profile_result_refs=[identity])
    response = invoke(target, body)
    assert artifacts(response, "ProfileAnalysesProjection")[0]["analyses"] == []
    if model == "CompetitionPlan":
        reference = target.profile_input_bindings[identity].plan_ref.model_dump(mode="json")
        reference["version"] += 1
        body = request("Read wrong plan", {**CONTEXT, "plan_ref": reference})
        body["request"].update(intent="GET_PROFILE_ANALYSES", profile_result_refs=[identity])
        assert artifacts(invoke(target, body), "ProfileAnalysesProjection")[0]["analyses"] == []


def test_changed_prepared_arguments_do_not_inherit_repository_reference():
    target = create_local_host(ROOT)
    original = AgentCapabilityFacade.execute

    def changed(self, invocation, arguments, **kwargs):
        if invocation.capability == "get_recommendations":
            for context in arguments["payload"]["contexts"]:
                context["student_profile"]["major"] = "Different explicit input"
        return original(self, invocation, arguments, **kwargs)

    with patch.object(AgentCapabilityFacade, "execute", changed):
        result = generate(target, "GET_RECOMMENDATIONS")
    identity = next(a["ref"]["ref_id"] for a in result["presentation"]["artifacts"] if a["model"] == "RecommendationRankingResult")
    assert identity not in target.profile_input_bindings
    assert freshness(target, [identity])[0]["profile_freshness"]["status"] == "UNKNOWN"
