"""Independent repository profile resolution and deferred exact-target preparation."""

import json
from unittest.mock import patch

import pytest
from test_generated_huawei_replanning import artifacts
from test_local_cloud_llm import NOW, ROOT, Chat, host, invoke, proposal, request
from test_profile_runtime import STUDENT, read, update

from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.agents.contracts import AgentRequest, ResultReference
from competition_copilot.agents.routing import (
    IntentRoutingProposal,
    PendingArgumentPreparation,
    RoutingProposalValidator,
)
from competition_copilot.application.skill_gap_inputs import prepare_skill_gap_context
from competition_copilot.integrations.local_runtime.composition import create_local_host

TARGET = {"competition_id": "comap-mcm", "edition_id": "comap-mcm-2027"}


def pending_frame(target):
    session = next(iter(target._pending.values()))[1]
    return json.loads(session.adapter._bindings.pending)


def test_repository_hydration_precedes_even_routing_admission_preflight():
    target = create_local_host(ROOT)
    events = []
    lookup = target.profile_repository.get_record
    validate = RoutingProposalValidator.validate

    def record(student_id):
        events.append(("profile", student_id))
        return lookup(student_id)

    def admission(self, *args, **kwargs):
        assert events and events[0] == ("profile", STUDENT)
        events.append(("routing", None))
        return validate(self, *args, **kwargs)

    body = request("plan", {"student_id": STUDENT, "competition_id": "comap-mcm"})
    body["request"]["intent"] = "BUILD_PLAN"
    with patch.object(target.profile_repository, "get_record", record), patch.object(
            RoutingProposalValidator, "validate", admission):
        result = invoke(target, body)
    assert result["runtime"]["response"]["clarification"]["fields"] == ["EDITION"]
    assert len([e for e in events if e[0] == "routing"]) == 2


@pytest.mark.parametrize("mode", ["explicit", "offline", "cloud"])
@pytest.mark.parametrize("selection,fields", [
    ({"competition_id": "comap-mcm"}, ["EDITION"]),
    ({}, ["COMPETITION"]),
])
def test_profile_and_reference_resolved_before_target_clarification(mode, selection, fields):
    chat = Chat(proposals=[proposal("BUILD_PLAN", "build_plan", missing_context=["STUDENT_PROFILE"])])
    target = host(chat) if mode == "cloud" else create_local_host(ROOT)
    expected = target.profile_repository.get(STUDENT).profile_ref
    body = request("为这个比赛生成备赛计划", {"student_id": STUDENT, **selection})
    if mode == "explicit":
        body["request"]["intent"] = "BUILD_PLAN"
    calls = []
    original = AgentCapabilityFacade.execute

    def observe(self, invocation, *args, **kwargs):
        calls.append(invocation.capability)
        return original(self, invocation, *args, **kwargs)

    with patch.object(AgentCapabilityFacade, "execute", observe):
        result = invoke(target, body)
    question = result["runtime"]["response"]["clarification"]
    assert question["fields"] == fields
    assert question["reason"] == "MISSING_REQUIRED_CONTEXT"
    frame = pending_frame(target)
    assert frame["pending_preparation"]["profile_ref"] == expected.model_dump(mode="json")
    assert not {"build_plan", "analyze_skill_gap"}.intersection(calls)
    assert frame["state"]["request"]["context"].get("edition_id") is None
    assert frame["state"]["request"]["context"].get("track_id") is None


@pytest.mark.parametrize("student", [None, "repository-profile-does-not-exist"])
def test_missing_student_or_repository_profile_cannot_be_synthesized(student):
    target = create_local_host(ROOT)
    body = request("plan", {**TARGET, **({"student_id": student} if student else {})})
    body["request"]["intent"] = "BUILD_PLAN"
    result = invoke(target, body)
    question = result["runtime"]["response"]["clarification"]
    assert question["fields"] == ["STUDENT_PROFILE"]
    assert question["reason"] == "MISSING_STUDENT_PROFILE"
    assert pending_frame(target)["pending_preparation"]["profile_ref"] is None
    assert target.profile_repository.get(student) is None
    # Even a crafted advanced reply cannot create/replace authoritative profile state.
    result = invoke(target, {"continuation_ref": result["runtime"]["continuation_ref"], "clarification": {
        "clarification_id": question["clarification_id"], "source_request_id": "cloud-request",
        "submitted_at": NOW.isoformat(), "values": {"student": {"id": student or "invented"}}}})
    assert result["runtime"]["response"]["outcome"] == "NEEDS_CLARIFICATION"
    assert result["runtime"]["response"]["clarification"]["reason"] == "MISSING_STUDENT_PROFILE"
    assert target.profile_repository.get(student or "invented") is None


@pytest.mark.parametrize("intent,model", [("BUILD_PLAN", "CompetitionPlan"), ("ANALYZE_SKILL_GAP", "SkillGapDecision")])
def test_valid_edition_without_track_proceeds_and_records_snapshot(intent, model):
    target = create_local_host(ROOT)
    expected = target.profile_repository.get(STUDENT).profile_ref
    body = request("plan", {"student_id": STUDENT, **TARGET})
    body["request"]["intent"] = intent
    result = invoke(target, body)
    assert result["runtime"]["response"]["outcome"] == "COMPLETED", result
    assert artifacts(result, model)
    binding = next(b for b in target.profile_input_bindings.values() if b.kind == model)
    assert binding.input_profile_ref == expected
    assert binding.track_id is None


@pytest.mark.parametrize("intent,model", [("BUILD_PLAN", "CompetitionPlan"), ("ANALYZE_SKILL_GAP", "SkillGapDecision")])
def test_edition_continuation_uses_retained_snapshot_not_browser_profile_or_latest_ref(intent, model):
    target = create_local_host(ROOT)
    before = read(target)[1][0]
    body = request("plan", {"student_id": STUDENT, "competition_id": "comap-mcm"})
    body["request"]["intent"] = intent
    pending = invoke(target, body)
    question = pending["runtime"]["response"]["clarification"]
    assert question["fields"] == ["EDITION"]
    update(target, before, {"major": "Edited while selecting edition", "weekly_available_hours": 7.5})
    current = target.profile_repository.get(STUDENT).profile_ref
    seen = []
    def observe(repository, provider, student, *args):
        seen.append(student.model_dump(mode="json"))
        return prepare_skill_gap_context(repository, provider, student, *args)

    with patch("competition_copilot.integrations.local_runtime.composition.prepare_skill_gap_context", observe):
        result = invoke(target, {"continuation_ref": pending["runtime"]["continuation_ref"], "clarification": {
            "clarification_id": question["clarification_id"], "source_request_id": "cloud-request",
            "submitted_at": NOW.isoformat(), "values": {"edition_id": TARGET["edition_id"]}}})
    assert result["runtime"]["response"]["outcome"] == "COMPLETED", result
    assert artifacts(result, model)
    assert seen and all(p["major"] == before["major"] for p in seen)
    binding = next(b for b in target.profile_input_bindings.values() if b.kind == model)
    assert binding.input_profile_ref.model_dump(mode="json") == before["profile_ref"]
    assert binding.input_profile_ref != current
    # A genuinely new request captures the latest repository snapshot.
    body["request"]["context"].update(TARGET)
    body["request"]["request_id"] = "new-invocation"
    fresh = invoke(target, body)
    assert fresh["runtime"]["response"]["outcome"] == "COMPLETED"
    assert any(b.kind == model and b.input_profile_ref == current for b in target.profile_input_bindings.values())


def test_trusted_track_requirement_requests_only_track_and_never_grants_execution():
    # Current P7/P8 contracts permit edition-level targets. This exercises a
    # caller-declared required track without inventing a production track rule.
    target = create_local_host(ROOT)
    reference = target.profile_repository.get(STUDENT).profile_ref
    facade = AgentCapabilityFacade()
    validator = RoutingProposalValidator(facade)
    body = AgentRequest(request_id="track", user_message="plan", context={"student_id": STUDENT, **TARGET})
    ref = ResultReference(kind="CAPABILITY_ARGUMENTS", ref_id="args")
    selected = IntentRoutingProposal(intent="BUILD_PLAN", candidate_capability="build_plan",
        ambiguity="NONE", missing_context=())
    result = validator.validate(selected, body, invocation_id="invoke", arguments_ref=ref,
        arguments={"artifact_ref": ref.model_dump(mode="json"), "payload": {}},
        pending_preparation=PendingArgumentPreparation(capability="build_plan", fields=("TRACK",), profile_ref=reference))
    assert result.status == "CLARIFICATION" and result.missing_context == ("TRACK",)
    assert result.invocation is None
    # Without an unresolved-preparation notice the empty payload still fails closed.
    result = validator.validate(selected, body, invocation_id="invoke", arguments_ref=ref,
        arguments={"artifact_ref": ref.model_dump(mode="json"), "payload": {}})
    assert result.status == "CLARIFICATION" and result.invocation is None
