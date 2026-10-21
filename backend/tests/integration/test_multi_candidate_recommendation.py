"""Real runtime/P5/P6 and narrowly bounded anchor identity admission."""

import json

import pytest
from test_local_cloud_llm import Chat, count, host, invoke, proposal, request

from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.agents.contracts import AgentRequest
from competition_copilot.agents.routing import ProposedTargets, context_conflicts


def test_real_cloud_prepared_once_distinct_p5_refs_and_one_complete_p6(monkeypatch):
    executed = []
    original = AgentCapabilityFacade.execute

    def observe(self, invocation, arguments, *, result_ref):
        receipt = original(self, invocation, arguments, result_ref=result_ref)
        executed.append((invocation, arguments, result_ref, receipt))
        return receipt

    monkeypatch.setattr(AgentCapabilityFacade, "execute", observe)
    chat = Chat(proposals=[proposal("GET_RECOMMENDATIONS", "get_recommendations")])
    result = invoke(host(chat), request("recommend", {"student_id": "local-graduate",
        "competition_id": "gcxl-engineering-practice-innovation",
        "edition_id": "gcxl-engineering-practice-innovation-2027"}))
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    assert count(chat, "IntentRoutingProposal") == 1
    p5 = [entry for entry in executed if entry[0].capability == "check_eligibility"]
    p6 = [entry for entry in executed if entry[0].capability == "get_recommendations"]
    assert len(p5) == 12 and len(p6) == 1
    assert len({entry[0].invocation_id for entry in p5}) == len(p5)
    assert len({entry[0].arguments_ref.ref_id for entry in p5}) == len(p5)
    assert len({entry[2].ref_id for entry in p5}) == len(p5)
    contexts = p6[0][1]["payload"]["contexts"]
    assert len(contexts) == len(p5)
    assert [c["eligibility_decision"] for c in contexts] == [
        entry[3].data.model_dump(mode="json") for entry in p5]
    ranking = p6[0][3].data
    assert any(item.candidate.competition_id == "gcxl-engineering-practice-innovation"
               for item in ranking.blocked)
    assert all(item.evaluation.suitability_score is None
               for item in (*ranking.confirmed, *ranking.uncertain))
    assert len(ranking.confirmed) + len(ranking.uncertain) + len(ranking.blocked) == 12


def batch():
    # Projection fixtures only: full P6 validation is exercised by the runtime test above.
    return {"contexts": [{"student_profile": {"id": "student"}, "candidate": {
        "competition_id": c, "edition_id": e}} for c, e in (("anchor", "edition"), ("other", "other-edition"))]}


def caller(**context):
    return AgentRequest(request_id="request", user_message="recommend", context={
        "student_id": "student", "competition_id": "anchor", "edition_id": "edition", **context})


def conflict(payload, *, actual=None, targets=None, capability="get_recommendations"):
    return context_conflicts(actual or caller(), payload, ProposedTargets(**(targets or {})), capability=capability)


def test_anchor_membership_not_global_target_but_only_for_p6():
    assert not conflict(batch(), targets={"competition_id": "anchor", "edition_id": "edition"})
    assert conflict(batch(), capability="check_eligibility")
    assert conflict(batch(), targets={"competition_id": "other"})
    assert conflict(batch(), targets={"student_id": "other"})
    assert conflict(batch(), actual=caller(track_id="explicit-track"))


@pytest.mark.parametrize("mutation", ["absent-anchor", "different-student", "internal-conflict", "plan", "top-level-conflict"])
def test_alternative_batch_never_weakens_identity_guards(mutation):
    payload = json.loads(json.dumps(batch()))
    if mutation == "absent-anchor":
        payload["contexts"][0]["candidate"]["edition_id"] = "wrong"
    elif mutation == "different-student":
        payload["contexts"][1]["student_profile"]["id"] = "other"
    elif mutation == "internal-conflict":
        payload["contexts"][1]["competition"] = {"id": "conflict"}
    elif mutation == "plan":
        payload["contexts"][1]["plan_id"] = "plan"
    else:
        payload["competition_id"] = "conflict"
    assert conflict(payload)


def test_failed_prerequisite_is_not_an_unknown_candidate_or_partial_p6_result():
    from types import SimpleNamespace

    from competition_copilot.domain.student import StudentProfile
    from competition_copilot.integrations.local_runtime.recommendation import (
        FacadeEligibilityEvaluator,
    )

    class FailingFacade:
        calls = 0

        def execute(self, *args, **kwargs):
            self.calls += 1
            return SimpleNamespace(status="FAILED", data=None)

    facade = FailingFacade()
    with pytest.raises(ValueError, match="P5 prerequisite unavailable"):
        FacadeEligibilityEvaluator(facade, request_id="request", namespace="test").evaluate(
            StudentProfile(id="student"), "competition", "edition")
    assert facade.calls == 1
