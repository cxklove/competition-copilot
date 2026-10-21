"""Real P5/P6/runtime with deterministic model and transport; no cloud calls."""

import socket

import pytest
from test_agentarts_transport import HARNESS, pair
from test_local_cloud_llm import Chat, count, host, invoke, proposal, request

from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.domain.verified_skill_overlap import VerifiedSkillOverlapScorer

CONTEXT = {"student_id": "local-recommendation-demo",
    "competition_id": "gcxl-engineering-practice-innovation",
    "edition_id": "gcxl-engineering-practice-innovation-2027"}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    original = socket.socket.connect
    def connect(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original(sock, address)
        pytest.fail("Scorer regression must not access external network")
    monkeypatch.setattr(socket.socket, "connect", connect)


def ranking(result):
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    return next(a["value"] for a in result["presentation"]["artifacts"] if a["model"] == "RecommendationRankingResult")


def assert_demo(result):
    data = ranking(result)
    assert not data["confirmed"] and not data["blocked"] and len(data["uncertain"]) == 12
    by_id = {r["evaluation"]["candidate"]["competition_id"]: r for r in data["uncertain"]}
    assert [r["evaluation"]["candidate"]["competition_id"] for r in data["uncertain"][:2]] == [
        "china-graduate-math-modeling", "comap-mcm"]
    for identity in ("china-graduate-math-modeling", "comap-mcm"):
        evaluation = by_id[identity]["evaluation"]
        assert evaluation["suitability_score"] == 1.0 and evaluation["status"] == "eligibility_uncertain"
        assert len(evaluation["score_components"]) == 1
        component = evaluation["score_components"][0]
        assert component["component_id"] == VerifiedSkillOverlapScorer.component_id
        assert "coverage=partial" in component["message"]
        assert any(e["source"] and e["source"]["verification_status"] == "verified" for e in component["evidence"])
        assert any(e["field"] == "skills.mathematical-modeling.self_assessed" and e["value"] is True for e in component["evidence"])
    for identity, entry in by_id.items():
        if identity not in ("china-graduate-math-modeling", "comap-mcm"):
            assert entry["evaluation"]["suitability_score"] is None
            assert entry["evaluation"]["score_components"] == []
    assert data["ranking_policy"] == "eligibility_buckets_score_desc_target_id_v1"
    return data


def test_cloud_prepared_once_one_p6_and_no_fallback_or_retry(monkeypatch):
    calls, scoring = [], []
    original = AgentCapabilityFacade.execute
    def execute(self, invocation, arguments, *, result_ref):
        calls.append(invocation.capability)
        if invocation.capability == "get_recommendations":
            scoring.extend(self._scoring._scorers)
            snapshots = [c["skill_requirements"] for c in arguments["payload"]["contexts"]]
            assert sum(s is not None for s in snapshots) == 3
        return original(self, invocation, arguments, result_ref=result_ref)
    def forbid(*args, **kwargs):
        pytest.fail("Cloud must not construct an offline fallback")
    monkeypatch.setattr(AgentCapabilityFacade, "execute", execute)
    monkeypatch.setattr("competition_copilot.integrations.local_runtime.composition.OfflineIntentModel", forbid)
    chat = Chat(proposals=[proposal("GET_RECOMMENDATIONS", "get_recommendations")])
    result = invoke(host(chat), request("recommend", CONTEXT))
    assert_demo(result)
    assert count(chat, "IntentRoutingProposal") == 1
    assert calls == ["check_eligibility"] * 12 + ["get_recommendations"]
    assert len(scoring) == 1 and isinstance(scoring[0][0], VerifiedSkillOverlapScorer) and scoring[0][2] == 1.0


def test_real_http_local_agentarts_parity_and_repeatable_result():
    with HARNESS["running"]() as environment:
        # Existing helper asserts complete Local/AgentArts HTTP response equality.
        first = assert_demo(pair(environment, request("recommend", CONTEXT)))
        repeated = pair(environment, request("recommend", CONTEXT, identity="next-request"))
        assert assert_demo(repeated) == first
