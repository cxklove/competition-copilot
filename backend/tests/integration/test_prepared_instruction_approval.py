"""Authority-free proposal -> existing P12 bridge -> unchanged P11 executor.

Not a Local same-plan feature: the production Local composition is untouched.
Old Local host tests continue to prove single-use transport continuation guards.
"""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from competition_copilot.agents import human_interactions as bridge
from competition_copilot.agents.contracts import (
    AgentContext,
    AgentRequest,
    ApprovalResponse,
    CapabilityInvocationRequest,
    ResultReference,
)
from competition_copilot.application.instruction_preparation import (
    PlanRevisionProposal,
    TargetTrackRemovedCancellationPolicy,
)
from competition_copilot.domain.plan_revision_service import PlanRevisionService
from competition_copilot.domain.replanning import PlanReference
from competition_copilot.integrations.local_runtime.plans import InMemoryPlanRegistry
from tests.application.test_instruction_preparation import NOW, PREPARED, scenario

CREATED = NOW + timedelta(minutes=5)
SUBMITTED = NOW + timedelta(minutes=6)
EXECUTED = NOW + timedelta(minutes=7)


def preparation():
    plan, decision = scenario()
    source = TargetTrackRemovedCancellationPolicy().prepare(plan, decision, prepared_at=PREPARED).proposal
    request = AgentRequest(request_id="policy-review", user_message="Review proposed operation",
        context=AgentContext(plan_ref=PlanReference.from_plan(plan)))
    invocation = CapabilityInvocationRequest(invocation_id="policy-review/invoke",
        source_request_id=request.request_id, intent="REQUEST_PLAN_REVISION", capability="revise_plan",
        arguments_ref=ResultReference(kind="CAPABILITY_ARGUMENTS", ref_id="policy-review/args"),
        requires_approval=True)
    pending = bridge.prepare_approval(source, request, invocation,
        approval_request_id="policy-review/approval", created_at=CREATED)
    return source, request, invocation, pending


def reply(pending, decision="APPROVE", **changes):
    return ApprovalResponse(**{"approval_request_id": pending.approval_request_id,
        "source_request_id": pending.source_request_id, "decision": decision,
        "submitted_at": SUBMITTED, **changes})


def authorize(source, request, invocation, pending, response, registry, **changes):
    # Actor is server-owned. Neither the proposal nor ApprovalResponse provides it.
    trusted = {"current_plan": PlanReference.from_plan(registry.get_current(source.before.id)),
               "approved_by_ref": "trusted-test-operator", "executed_at": EXECUTED, **changes}
    return bridge.build_approved_replanning_input(pending, response, source, request, invocation, **trusted)


def test_preparation_and_pending_approval_create_no_authorized_instruction(monkeypatch):
    def forbid(*args, **kwargs):
        pytest.fail("Approval preparation must not manufacture authority or executable instructions")
    monkeypatch.setattr(bridge, "RevisionAuthority", forbid)
    monkeypatch.setattr(bridge, "UpdatePlanStatusInstruction", forbid)
    monkeypatch.setattr(bridge, "ReplanningInput", forbid)
    source, request, invocation, pending = preparation()
    assert pending.before_plan == source.operation.expected_plan
    assert pending.proposed_input_ref.ref_id == source.id
    assert pending.instruction_refs[0].ref_id == source.operation.id
    assert pending.resolution_ref is None  # No AuthorizedScopeResolution yet.
    assert source.policy_id in pending.summary and "draft -> cancelled" in pending.summary
    registry = InMemoryPlanRegistry()
    registry.register(source.before)
    rejected = reply(pending, "REJECT")
    bridge.validate_explicit_approval(pending, rejected, source, request, invocation,
        PlanReference.from_plan(source.before))
    with pytest.raises(ValueError, match="Explicit APPROVE"):
        authorize(source, request, invocation, pending, rejected, registry)
    assert registry.get_current(source.before.id) == source.before


def test_real_approve_bridge_creates_authority_then_p11_executes_and_stale_replay_fails():
    source, request, invocation, pending = preparation()
    registry = InMemoryPlanRegistry()
    reference = registry.register(source.before)
    approved = authorize(source, request, invocation, pending,
        reply(pending, comment="approved_by_ref=untrusted-browser-claim"), registry)
    instruction = approved.plan_status_instruction
    assert approved.before == source.before and approved.decision == source.decision
    assert approved.status == "executable" and approved.scope_resolution.status == "complete"
    assert instruction.authority.approval_ref == pending.approval_request_id
    assert instruction.authority.approved_by_ref == "trusted-test-operator"
    assert instruction.authority.approved_at == SUBMITTED
    assert approved.scope_resolution.instruction_ids == (instruction.id,)
    result = PlanRevisionService().revise(source.before, approved, executed_at=EXECUTED)
    assert result.after.status == "cancelled" and result.after.version == source.before.version + 1
    registry.replace_current(reference, result.after, plan_diff=result.plan_diff)
    with pytest.raises(ValueError, match="stale"):
        authorize(source, request, invocation, pending, reply(pending), registry)
    assert len(registry.history(source.before.id)) == 2
    assert PlanRevisionProposal.model_validate_json(source.model_dump_json()) == source
    assert "human_approved" not in source.model_dump_json()  # Never mutated into authorized input.


@pytest.mark.parametrize("change", [
    {"approval_request_id": "another-approval"}, {"source_request_id": "another-request"},
    {"submitted_at": PREPARED},
])
def test_wrong_or_old_response_cannot_authorize(change):
    source, request, invocation, pending = preparation()
    registry = InMemoryPlanRegistry()
    registry.register(source.before)
    with pytest.raises(ValueError):
        authorize(source, request, invocation, pending, reply(pending, **change), registry)


@pytest.mark.parametrize("changes", [{"approved_by_ref": None}, {"approved_by_ref": " "},
                                    {"executed_at": None}, {"executed_at": CREATED}])
def test_trusted_actor_and_execution_time_required(changes):
    source, request, invocation, pending = preparation()
    registry = InMemoryPlanRegistry()
    registry.register(source.before)
    with pytest.raises(ValueError):
        authorize(source, request, invocation, pending, reply(pending), registry, **changes)


def test_frontend_or_proposal_cannot_supply_actor_and_text_does_not_grant_approval():
    source, _, _, pending = preparation()
    with pytest.raises(ValidationError):
        ApprovalResponse.model_validate({**reply(pending).model_dump(), "approved_by_ref": "browser-actor"})
    with pytest.raises(ValidationError):
        PlanRevisionProposal.model_validate({**source.model_dump(), "approved_by_ref": "proposal-actor"})
    with pytest.raises(ValidationError):
        reply(pending, "yes, go ahead")


@pytest.mark.parametrize("field", ["source_request_id", "invocation_id", "summary", "affected_scope_ref"])
def test_pending_identity_scope_or_content_tampering_rejected(field):
    source, request, invocation, pending = preparation()
    data = pending.model_dump()
    if field == "affected_scope_ref":
        data[field]["ref_id"] = "different-scope"
    else:
        data[field] = "changed"
    changed = type(pending).model_validate(data)
    registry = InMemoryPlanRegistry()
    registry.register(source.before)
    with pytest.raises(ValueError):
        authorize(source, request, invocation, changed, reply(changed), registry)


def test_pending_preparation_refuses_cross_request_invocation_and_foreign_context():
    source, request, invocation, _ = preparation()
    other = CapabilityInvocationRequest(**{**invocation.model_dump(), "source_request_id": "other"})
    with pytest.raises(ValueError):
        bridge.prepare_approval(source, request, other, approval_request_id="q", created_at=CREATED)
    with pytest.raises(ValueError):
        foreign = AgentRequest(**{**request.model_dump(), "context": {
            **request.context.model_dump(), "student_id": "other-student"}})
        bridge.prepare_approval(source, foreign, invocation, approval_request_id="q", created_at=CREATED)
