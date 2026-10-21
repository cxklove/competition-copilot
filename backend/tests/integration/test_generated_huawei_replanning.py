"""Generated P8 plan -> real P9/P10/P11/policy/P12, offline demo observations."""

import asyncio
import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from test_agentarts_transport import HARNESS, pair
from test_local_cloud_llm import Chat, count, models, proposal

from competition_copilot.agents.graph import GraphInput
from competition_copilot.application.controlled_plan_observation import (
    ControlledPlanObservation,
    ControlledPlanRevisionPreparer,
)
from competition_copilot.domain.plan import CompetitionPlan
from competition_copilot.domain.plan_revision_service import PlanRevisionService
from competition_copilot.domain.replanning import PlanReference
from competition_copilot.domain.student import StudentProfile
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.integrations.local_runtime.composition import create_local_host

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)
CONTEXT = {"student_id": "local-recommendation-demo", "competition_id": "huawei-ict",
           "edition_id": "huawei-ict-2026", "track_id": "huawei-ict-2026-innovation"}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    original = socket.socket.connect
    def connect(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original(sock, address)
        pytest.fail("Generated same-plan tests must remain offline")
    monkeypatch.setattr(socket.socket, "connect", connect)


def request(message, context=CONTEXT, identity="generated-huawei"):
    return {"request": {"request_id": identity, "user_message": message, "context": context}}


def invoke(host, body):
    return asyncio.run(host.invoke(body))


def artifacts(result, name):
    return [a["value"] for a in (result.get("presentation") or {}).get("artifacts", []) if a["model"] == name]


def build(host):
    result = invoke(host, request("plan"))
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    plan = CompetitionPlan.model_validate(artifacts(result, "CompetitionPlan")[0])
    assert plan.student_id == CONTEXT["student_id"] and plan.status == "draft" and plan.version == 1
    assert (plan.competition_id, plan.edition_id, plan.track_id) == tuple(CONTEXT[k] for k in ("competition_id", "edition_id", "track_id"))
    assert plan.skill_gap_audit.coverage == "missing" and plan.skill_gap_audit.gap_status == "undetermined"
    assert all(need.kind == "uncertainty_resolution" for need in plan.planning_needs)
    ref = PlanReference.from_plan(plan)
    assert host.plan_registry.resolve(ref) == plan
    return plan, ref


def approval(pending, choice):
    q = pending["runtime"]["response"]["approval_request"]
    return {"continuation_ref": pending["runtime"]["continuation_ref"], "approval": {
        "approval_request_id": q["approval_request_id"], "source_request_id": q["source_request_id"],
        "decision": choice, "submitted_at": NOW.isoformat()}}


def test_same_generated_plan_reject_then_approve_real_pipeline_audit_registry_and_replay(monkeypatch):
    preparations = []
    executions = []
    revise = PlanRevisionService.revise
    def execute(self, before, source, **kwargs):
        executions.append((before, source))
        return revise(self, before, source, **kwargs)
    monkeypatch.setattr(PlanRevisionService, "revise", execute)
    original = ControlledPlanRevisionPreparer.prepare
    def observe(self, *args, **kwargs):
        value = original(self, *args, **kwargs)
        preparations.append(value)
        assert self.history() and self.history()[-1].proposal.id == value.proposal.id
        return value
    monkeypatch.setattr(ControlledPlanRevisionPreparer, "prepare", observe)
    host = create_local_host(ROOT, clock=lambda: NOW)
    plan, ref = build(host)
    old = json.loads((ROOT / "data/local_runtime/controlled_revision.json").read_text())["proposal"]["before"]
    assert plan.id != old["id"] and plan.student_id != old["student_id"]
    context = {**CONTEXT, "plan_ref": ref.model_dump(mode="json")}
    for choice in ("REJECT", "APPROVE"):
        pending = invoke(host, request("revision", context, "generated-" + choice))
        response = pending["runtime"]["response"]
        assert response["outcome"] == "WAITING_FOR_APPROVAL" and not artifacts(pending, "PlanDiff")
        assert host.plan_registry.get_current(plan.id) == plan
        assert not executions
        prepared = preparations[-1]
        assert prepared.proposal.before == plan
        assert prepared.proposal.policy_id == "target-track-removed-cancel-v1"
        assert "human_approved" not in prepared.proposal.model_dump_json()
        assert len(prepared.source_diff.changes) == 1 and prepared.source_diff.changes[0].field == "track_membership"
        assert plan.track_id in prepared.before_snapshot.dynamic_state.track_membership.value
        assert plan.track_id not in prepared.after_snapshot.dynamic_state.track_membership.value
        assert len(prepared.events) == 1 and prepared.events[0].event_type == "track_membership_changed"
        assert prepared.events[0].target == ref.target and prepared.events[0].id != old_event_id()
        assert prepared.events[0].source.source_type == "manual"
        assert "example.invalid" in str(prepared.events[0].source.source_url)
        assert prepared.impacts[0].outcome == "affects_plan" and "target_track_removed" in prepared.impacts[0].reason_codes
        assert prepared.impacts[0].student_id == plan.student_id and prepared.impacts[0].plan == ref
        assert prepared.decision.outcome == "replan" and prepared.decision.scope.whole_plan
        stale_pending = (invoke(host, request("revision", context, "pending-before-update"))
                         if choice == "APPROVE" else None)
        body = approval(pending, choice)
        result = invoke(host, body)
        assert result["runtime"]["response"]["outcome"] == "COMPLETED"
        diffs = artifacts(result, "PlanDiff")
        if choice == "REJECT":
            assert not executions
            assert "REJECTED" in result["runtime"]["response"]["message"] and diffs == []
            assert host.plan_registry.get_current(plan.id) == plan
            assert host.plan_registry.revisions(plan.id) == ()
        else:
            assert len(diffs) == 1
            assert len(executions) == 1 and executions[0][0] == plan
            assert executions[0][1].plan_status_instruction.authority.approved_by_ref == "local-development-operator"
            assert CompetitionPlan.model_validate(diffs[0]["before"]) == plan
            after = CompetitionPlan.model_validate(diffs[0]["after"])
            assert after.status == "cancelled" and after.version == plan.version + 1
            assert host.plan_registry.get_current(plan.id) == after
            assert host.plan_registry.history(plan.id) == (plan, after)
            assert host.plan_registry.revisions(plan.id)[0].before == plan
            assert "test-only-p11-5-student" not in json.dumps(diffs[0])
            stale_result = invoke(host, approval(stale_pending, "APPROVE"))
            assert stale_result["runtime"]["response"]["outcome"] == "FAILED"
            assert len(host.plan_registry.history(plan.id)) == 2
        assert invoke(host, body)["runtime"]["error"]["code"] == "CORE_VALIDATION_ERROR"
    assert invoke(host, request("revision", context, "stale"))["runtime"]["error"]["code"] == "CORE_VALIDATION_ERROR"
    assert len(executions) == 1


def old_event_id():
    data = json.loads((ROOT / "data/local_runtime/controlled_revision.json").read_text())
    return data["proposal"]["decision"]["impacts"][0]["event"]["id"]


def test_controlled_source_cannot_claim_official_change():
    data = json.loads((ROOT / "data/local_runtime/generated_huawei_observation.json").read_text())
    assert data["fixture_kind"] == "CONTROLLED DEMO OBSERVATION"
    data["source"]["source_type"] = "official"
    with pytest.raises(ValueError, match="manual source"):
        ControlledPlanObservation.model_validate(data)


@pytest.mark.parametrize("change", [{"track_id": "huawei-ict-2026-practice"},
                                    {"competition_id": "comap-mcm", "edition_id": "comap-mcm-2027", "track_id": None}])
def test_other_generated_target_cannot_use_configured_observation(change):
    host = create_local_host(ROOT, clock=lambda: NOW)
    result = invoke(host, request("plan", {**CONTEXT, **change}))
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    ref = result["runtime"]["response"]["plan_refs"][0]
    denied = invoke(host, request("revision", {**CONTEXT, **change, "plan_ref": ref}, "other-revision"))
    assert denied["runtime"]["error"]["message"] == "NO_TARGET_CONSISTENT_REPLANNING_INPUT"


def test_wrong_student_event_or_before_membership_rejects_without_inventing_impact():
    host = create_local_host(ROOT, clock=lambda: NOW)
    plan, ref = build(host)
    raw = json.loads((ROOT / "data/local_runtime/generated_huawei_observation.json").read_text())
    repo = JsonSeedCompetitionRepository(ROOT / "data/seed")
    preparer = ControlledPlanRevisionPreparer(repo, ControlledPlanObservation.model_validate(raw))
    with pytest.raises(ValueError, match="student"):
        preparer.prepare(plan, StudentProfile(id="other-student"), observed_at=NOW)
    raw["after_membership"] = raw["before_membership"]
    assert ControlledPlanRevisionPreparer(repo, ControlledPlanObservation.model_validate(raw)).prepare(
        plan, StudentProfile(id=plan.student_id), observed_at=NOW) is None
    raw["before_membership"] = ["unobserved-track"]
    with pytest.raises(ValueError, match="before observation"):
        ControlledPlanRevisionPreparer(repo, ControlledPlanObservation.model_validate(raw)).prepare(
            plan, StudentProfile(id=plan.student_id), observed_at=NOW)
    denied = invoke(host, request("revision", {**CONTEXT, "student_id": "local-graduate",
        "plan_ref": ref.model_dump(mode="json")}))
    assert denied["runtime"]["error"]


@pytest.mark.parametrize("tamper", ["payload", "proposal", "artifact_ref"])
def test_prepared_graph_channel_cannot_bypass_input_binding(tamper):
    host = create_local_host(ROOT, clock=lambda: NOW)
    _, ref = build(host)
    factory = host.factory
    def change(request):
        session = factory(request)
        bindings = session.adapter._bindings
        frame = bindings.frame
        args = json.loads(frame.arguments_json)
        if tamper == "payload":
            args["payload"]["executed_at"] = NOW.isoformat()  # forbidden before approval
        elif tamper == "artifact_ref":
            args["artifact_ref"]["ref_id"] = "other"
        else:
            frame = GraphInput(**{**frame.model_dump(), "prepared_revision": None})
        bindings.frame = GraphInput(**{**frame.model_dump(), "arguments_json": json.dumps(args)})
        return session
    host.factory = change
    result = invoke(host, request("revision", {**CONTEXT, "plan_ref": ref.model_dump(mode="json")}))
    assert result["runtime"]["response"]["outcome"] == "FAILED"
    assert host.plan_registry.get_current(ref.plan_id).version == 1


def test_cloud_intent_once_per_initial_request_with_same_real_approval_chain():
    chat = Chat(proposals=[proposal("BUILD_PLAN", "build_plan"),
                          proposal("REQUEST_PLAN_REVISION", "revise_plan")])
    host = create_local_host(ROOT, clock=lambda: NOW, cloud_models=models(chat))
    _, ref = build(host)
    pending = invoke(host, request("revision", {**CONTEXT, "plan_ref": ref.model_dump(mode="json")}, "cloud-revision"))
    result = invoke(host, approval(pending, "APPROVE"))
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    assert count(chat, "IntentRoutingProposal") == 2


def test_real_local_agentarts_http_same_generated_plan_parity():
    # Existing harness's January clock precedes reviewed seed observation dates.
    # This scenario supplies explicit later test time; no production clock changes.
    with patch.dict(HARNESS["running"].__wrapped__.__globals__, {"NOW": NOW}):
        with HARNESS["running"]() as env:
            generated = pair(env, request("plan"))
            ref = generated["runtime"]["response"]["plan_refs"][0]
            for choice in ("REJECT", "APPROVE"):
                pending = pair(env, request("revision", {**CONTEXT, "plan_ref": ref}, "http-" + choice))
                assert pending["runtime"]["response"]["outcome"] == "WAITING_FOR_APPROVAL"
                result = pair(env, approval(pending, choice))
                assert result["runtime"]["response"]["outcome"] == "COMPLETED"
                assert len(artifacts(result, "PlanDiff")) == (1 if choice == "APPROVE" else 0)
