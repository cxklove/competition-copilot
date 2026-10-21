"""Full-plan storage/CAS and real Local Agent registration/approval boundaries."""

import asyncio
import json
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier

import pytest

from competition_copilot.domain.plan import CompetitionPlan
from competition_copilot.domain.plan_revision_service import PlanRevisionService
from competition_copilot.domain.replanning import PlanReference
from competition_copilot.domain.replanning_input import ReplanningInput
from competition_copilot.integrations.local_runtime.composition import create_local_host
from competition_copilot.integrations.local_runtime.plans import InMemoryPlanRegistry

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)
SOURCE = ReplanningInput.model_validate(json.loads(
    (ROOT / "data/local_runtime/controlled_revision.json").read_text(encoding="utf-8"))["proposal"])
CONTEXT = {"student_id": "local-recommendation-demo", "competition_id": "comap-mcm",
           "edition_id": "comap-mcm-2027"}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    original = socket.socket.connect
    def forbid(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original(sock, address)  # Windows asyncio's local self-pipe.
        pytest.fail("Plan registry tests must not access network")
    monkeypatch.setattr(socket.socket, "connect", forbid)


def invoke(host, message, context, identity="registry-request"):
    return asyncio.run(host.invoke({"request": {"request_id": identity,
        "user_message": message, "context": context}}))


def generated(host):
    result = invoke(host, "plan", CONTEXT)
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    plan = CompetitionPlan.model_validate(next(a["value"] for a in result["presentation"]["artifacts"]
                                              if a["model"] == "CompetitionPlan"))
    ref = PlanReference.model_validate(result["runtime"]["response"]["plan_refs"][0])
    assert ref == PlanReference.from_plan(plan)
    return plan, ref


def revision():
    return PlanRevisionService().revise(SOURCE.before, SOURCE, executed_at=NOW)


def test_registration_full_snapshot_idempotency_and_explicit_conflict():
    registry = InMemoryPlanRegistry()
    before = SOURCE.before
    ref = registry.register(before)
    assert registry.register(before) == ref
    resolved = registry.resolve(ref)
    assert resolved == before and resolved is not before
    assert resolved.model_dump() == before.model_dump()
    assert registry.history(before.id) == (before,)
    for changes in ({"version": before.version + 1}, {"status": "draft"}):
        conflict = CompetitionPlan(**{**before.model_dump(), **changes})
        with pytest.raises(ValueError, match="registration conflict"):
            registry.register(conflict)
    for changes in ({"content_digest": "0" * 64}, {"version": ref.version + 1},
                    {"student_id": "another-student"}):
        with pytest.raises(ValueError, match="Unknown exact"):
            registry.resolve(PlanReference(**{**ref.model_dump(), **changes}))


def test_atomic_replacement_retains_full_history_diff_and_all_aliases():
    registry = InMemoryPlanRegistry()
    ref = registry.register(SOURCE.before)
    receipt = revision()
    after_ref = registry.replace_current(ref, receipt.after, plan_diff=receipt.plan_diff)
    assert registry.resolve(ref) == SOURCE.before
    assert registry.resolve(after_ref) == receipt.after
    assert registry.get_current(ref.plan_id) == registry.get_current(after_ref.plan_id) == receipt.after
    assert registry.history(after_ref.plan_id) == (SOURCE.before, receipt.after)
    assert registry.revisions(ref.plan_id) == (receipt.plan_diff,)
    assert registry.register(SOURCE.before) == ref  # no rewind of current head
    assert registry.get_current(ref.plan_id) == receipt.after
    with pytest.raises(ValueError, match="Stale"):
        registry.replace_current(ref, receipt.after, plan_diff=receipt.plan_diff)


def test_concurrent_cas_has_one_winner():
    registry = InMemoryPlanRegistry()
    ref = registry.register(SOURCE.before)
    receipt = revision()
    barrier = Barrier(2)
    def attempt(_):
        barrier.wait(timeout=5)
        try:
            registry.replace_current(ref, receipt.after, plan_diff=receipt.plan_diff)
            return "replaced"
        except ValueError:
            return "stale"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == ["replaced", "stale"]
    assert len(registry.history(ref.plan_id)) == 2


def test_replacement_rejects_mismatched_diff_without_partial_storage():
    registry = InMemoryPlanRegistry()
    ref = registry.register(SOURCE.before)
    receipt = revision()
    with pytest.raises(ValueError, match="exact before/after"):
        registry.replace_current(ref, SOURCE.before, plan_diff=receipt.plan_diff)
    assert registry.get_current(ref.plan_id) == SOURCE.before
    assert registry.history(ref.plan_id) == (SOURCE.before,)
    assert registry.revisions(ref.plan_id) == ()


def test_generated_plan_registered_cross_request_but_no_proposal_and_restart_resets():
    host = create_local_host(ROOT, clock=lambda: NOW)
    registry = host.plan_registry
    controlled_ref = PlanReference.from_plan(SOURCE.before)
    assert registry.resolve(controlled_ref) == SOURCE.before
    plan, ref = generated(host)
    assert registry.resolve(ref) == registry.get_current(plan.id) == plan
    assert registry.history(plan.id) == (plan,)
    assert generated(host) == (plan, ref)
    result = invoke(host, "revision", {**CONTEXT, "plan_ref": ref.model_dump(mode="json")}, "next-request")
    assert result["runtime"]["error"] == {"code": "CORE_VALIDATION_ERROR",
        "message": "NO_TARGET_CONSISTENT_REPLANNING_INPUT"}
    assert result["presentation"] is None and registry.revisions(plan.id) == ()
    restarted = create_local_host(ROOT, clock=lambda: NOW)
    with pytest.raises(ValueError, match="Unknown exact"):
        restarted.plan_registry.resolve(ref)
    assert restarted.plan_registry.resolve(controlled_ref) == SOURCE.before


@pytest.mark.parametrize("decision", ["APPROVE", "REJECT"])
def test_controlled_registry_revision_replay_and_pending_stale_guard(decision):
    registry = InMemoryPlanRegistry()
    host = create_local_host(ROOT, clock=lambda: NOW, plan_registry=registry)
    ref = PlanReference.from_plan(SOURCE.before)
    context = {"plan_ref": ref.model_dump(mode="json")}
    pending = invoke(host, "revision", context)
    stale = invoke(host, "revision", context, "second-pending")
    def reply(result, choice):
        response = result["runtime"]["response"]
        assert response["outcome"] == "WAITING_FOR_APPROVAL"
        return {"continuation_ref": result["runtime"]["continuation_ref"], "approval": {
            "approval_request_id": response["approval_request"]["approval_request_id"],
            "source_request_id": response["request_id"], "decision": choice,
            "submitted_at": NOW.isoformat()}}
    body = reply(pending, decision)
    result = asyncio.run(host.invoke(body))
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    if decision == "APPROVE":
        current = registry.get_current(ref.plan_id)
        assert current.status == "cancelled" and current.version == ref.version + 1
        assert registry.history(ref.plan_id) == (SOURCE.before, current)
        assert registry.revisions(ref.plan_id)[0].after == current
        denied = asyncio.run(host.invoke(reply(stale, "APPROVE")))
        assert denied["runtime"]["response"]["outcome"] == "FAILED"
        assert len(registry.history(ref.plan_id)) == 2
    else:
        assert registry.get_current(ref.plan_id) == SOURCE.before
        assert registry.revisions(ref.plan_id) == ()
    assert asyncio.run(host.invoke(body))["runtime"]["error"]["code"] == "CORE_VALIDATION_ERROR"
