"""Real HTTP/runtime/Agent/P7/P8, with identical Local/AgentArts semantics."""

import socket

import pytest
from test_agentarts_transport import HARNESS, pair

from competition_copilot.agents.capabilities import AgentCapabilityFacade


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    original = socket.socket.connect
    def connect(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original(sock, address)
        pytest.fail("Student evidence tests must stay offline")
    monkeypatch.setattr(socket.socket, "connect", connect)


def request(student="local-recommendation-demo", competition="comap-mcm", edition="comap-mcm-2027", message="skill"):
    return {"request": {"request_id": "student-evidence", "user_message": message,
        "context": {"student_id": student, "competition_id": competition, "edition_id": edition}}}


def artifact(result, name):
    assert result["runtime"]["error"] is None
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    return next(a["value"] for a in result["presentation"]["artifacts"] if a["model"] == name)


@pytest.mark.parametrize("student", ["local-recommendation-demo", "local-graduate", "local-unknown"])
def test_comap_real_p7_preserves_unknown_threshold_and_partial_coverage(student):
    with HARNESS["running"]() as env:
        decision = artifact(pair(env, request(student)), "SkillGapDecision")
    assert decision["gap_status"] == "undetermined"
    assert "PARTIAL_REQUIREMENT_COVERAGE" in decision["reason_codes"]
    item = decision["items"][0]
    assert item["requirement"]["required_level"] is None and item["status"] == "unknown"
    if student == "local-recommendation-demo":
        assert item["student_level"] == "intermediate"
        assert item["student_evidence"]
        assert all(e["source"] is None and "self_assessed=true;" in e["message"] for e in item["student_evidence"])
    else:
        assert item["student_level"] is None and item["student_evidence"] == []


def test_c4_missing_skill_has_no_invented_evidence_or_deficit():
    with HARNESS["running"]() as env:
        result = pair(env, request(competition="c4-big-data-challenge", edition="c4-big-data-challenge-2026"))
    decision = artifact(result, "SkillGapDecision")
    assert decision["gap_status"] == "undetermined"
    assert "STUDENT_SKILL_DATA_MISSING" in decision["reason_codes"]
    item = decision["items"][0]
    assert item["status"] == "unknown" and item["student_level"] is None
    assert item["student_evidence"] == []


def test_p8_real_prerequisite_receives_declared_evidence(monkeypatch):
    observed = []
    original = AgentCapabilityFacade.execute
    def execute(self, invocation, arguments, *, result_ref):
        receipt = original(self, invocation, arguments, result_ref=result_ref)
        if invocation.capability == "analyze_skill_gap":
            observed.append(receipt)
        return receipt
    monkeypatch.setattr(AgentCapabilityFacade, "execute", execute)
    with HARNESS["running"]() as env:
        plan = artifact(pair(env, request(message="plan")), "CompetitionPlan")
    assert plan["status"] == "draft"
    assert len(observed) == 2  # one real P7 prerequisite for each transport
    assert all(r.status == "SUCCESS" and r.data.items[0].student_evidence for r in observed)
