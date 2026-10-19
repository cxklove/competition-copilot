"""Full real composition, restricted surface and adversarial entry isolation."""

import asyncio
from contextlib import asynccontextmanager

import pytest

pytest.importorskip("mcp", reason="Install optional MCP overlay")
pytest.importorskip("langgraph", reason="Install optional Agent overlay")

from agent_e2e_support import ROOT, TIME, Harness, frame
from mcp import Client, MCPError
from mcp_execution_support import COMPETITION, EDITION, arguments, eligibility_payload
from mcp_gateway_support import GatewayHarness
from mcp_real_support import run as run
from test_mcp_authority_parity import canonical
from test_p6_recommendation_integration import prepare_context

from competition_copilot.application.eligibility import CompetitionEligibilityEvaluator
from competition_copilot.domain.skill_gap import SkillGapContext
from competition_copilot.domain.student import StudentProfile
from competition_copilot.infrastructure.eligibility_policy_json import (
    JsonEligibilityPolicyProvider,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.infrastructure.skill_requirement_json import (
    JsonSkillRequirementProvider,
)
from competition_copilot.integrations.mcp.contracts import McpToolResult


@asynccontextmanager
async def entry(gateway, path):
    async with gateway.connect() as client:
        if path == "gateway":
            yield client
        elif path == "local":
            async with Client(gateway.target.server, cache=None) as local:
                yield local
        else:
            async with gateway.target.client(path) as http:
                yield http


@pytest.mark.parametrize("path", ["local", "legacy", "auto", "gateway"])
def test_full_composition_invalid_calls_never_reach_any_authority(path, run):
    agent = Harness(frame({}, "Discovery"), "DISCOVER_COMPETITIONS", "list_competitions")
    gateway = GatewayHarness(agent.facade)

    async def scenario():
        async with entry(gateway, path) as client:
            before = await client.list_tools(cache_mode="bypass")
            for name in ("unknown", "revise_plan", "apply_revision", "approve_plan", "reject_plan",
                         "get_recommendations", "analyze_skill_gap", "build_plan",
                         "derive_competition_events", "monitor_competition_source", "../../revision"):
                with pytest.raises(MCPError) as caught:
                    await client.call_tool(name, arguments(), meta={"approved": True, "role": "owner"})
                assert caught.value.error.message == "UNKNOWN_TOOL"
                assert not agent.calls
            for field in ("capability_id", "approved", "human_approved", "admin_override", "approval_request_id"):
                result = await client.call_tool("competition_list", {**arguments(), field: "revise_plan"})
                assert result.is_error
                assert McpToolResult.model_validate(result.structured_content).error.code == "INVALID_ARGUMENTS"
                assert not agent.calls
            result = await client.call_tool("eligibility_check", arguments())
            assert result.is_error and not agent.calls
            after = await client.list_tools(cache_mode="bypass")
            assert before.model_dump(mode="json") == after.model_dump(mode="json")
        assert not agent.routing.calls and not agent.explanation.contexts
    run(scenario)


@pytest.mark.parametrize("path", ["local", "legacy", "auto", "gateway"])
def test_full_composition_internal_exception_safe_once_without_retry(path, run, monkeypatch):
    agent = Harness(frame({}, "Discovery"), "DISCOVER_COMPETITIONS", "list_competitions")
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("Traceback C:/private/repo SECRET=private-key <Python repr>")

    monkeypatch.setattr(agent.facade, "execute", fail)
    gateway = GatewayHarness(agent.facade)

    async def scenario():
        async with entry(gateway, path) as client:
            result = await client.call_tool("competition_list", arguments())
            assert result.is_error
            assert McpToolResult.model_validate(result.structured_content).error.code == "EXECUTION_FAILURE"
            assert not any(token in result.model_dump_json() for token in (
                "Traceback", "C:/", "private", "SECRET", "<Python"))
        assert calls == [1]
    run(scenario)


def test_full_composition_gateway_concurrency_and_session_context_isolation(run):
    agent = Harness(frame({}, "Discovery"), "DISCOVER_COMPETITIONS", "list_competitions")
    gateway = GatewayHarness(agent.facade)

    async def scenario():
        async with gateway.connect(headers={"mcp-session-id": "fake-approval",
                "authorization": "Bearer test-placeholder", "x-student-id": "wrong-student"}) as client:
            async def call(student, level):
                raw = arguments(eligibility_payload(level))
                raw["payload"]["student"]["id"] = student
                raw["source_request_id"] = student
                return canonical(await client.call_tool("eligibility_check", raw, meta={
                    "admin": True, "approved": True, "role": "owner", "user_id": "wrong-user"}))

            a, b = await asyncio.gather(call("student-A", "graduate"), call("student-B", "undergraduate"))
            assert (a["source_request_id"], a["data"]["status"]) == ("student-A", "ineligible")
            assert (b["source_request_id"], b["data"]["status"]) == ("student-B", "unknown")
            assert len(agent.calls) == 2
            missing = arguments(eligibility_payload())
            del missing["payload"]["student"]
            assert (await client.call_tool("eligibility_check", missing)).is_error
            assert len(agent.calls) == 2  # No previous student/session can fill missing input.
            for competition in (COMPETITION, "comap-mcm"):
                result = canonical(await client.call_tool("competition_get", arguments({
                    "competition_id": competition})))
                assert result["data"]["competition"]["id"] == competition
            assert len(agent.calls) == 4
        assert not agent.routing.calls and not agent.explanation.contexts
    run(scenario)


def test_real_p6_p7_p8_authorities_remain_agent_only_and_not_mcp_exposed(run):
    repository = JsonSeedCompetitionRepository(ROOT / "data/seed")
    evaluator = CompetitionEligibilityEvaluator(repository, JsonEligibilityPolicyProvider(ROOT / "data/eligibility"))
    student = StudentProfile(id="integration-student", education_level="graduate", interests=["math"])
    contexts = [prepare_context(repository, student, evaluator.evaluate(student, competition, edition))
                for competition, edition in (("comap-mcm", "comap-mcm-2027"), (COMPETITION, EDITION))]
    recommend = Harness(frame({"contexts": contexts}, "Recommend"),
                        "GET_RECOMMENDATIONS", "get_recommendations")
    requirements = JsonSkillRequirementProvider(ROOT / "data/skill_requirements").get_requirements(
        "comap-mcm", "comap-mcm-2027")
    skill_context = SkillGapContext(student_profile=student, competition=repository.get_competition("comap-mcm"),
        edition=repository.get_edition("comap-mcm-2027"), requirements=requirements)
    skill = Harness(frame({"context": skill_context}, "Skill gap"), "ANALYZE_SKILL_GAP", "analyze_skill_gap")

    async def scenario():
        assert recommend.agent.invoke(recommend.prepared.state.request).outcome == "COMPLETED"
        ranked = recommend.receipts[-1].data
        assert ranked.uncertain and ranked.blocked and not ranked.confirmed
        assert skill.agent.invoke(skill.prepared.state.request).outcome == "COMPLETED"
        decision = skill.receipts[-1].data
        assert decision.gap_status == "undetermined" and decision.reason_codes
        planning = Harness(frame({"source_decision": decision, "student_id": student.id,
            "created_at": TIME.isoformat()}, "Plan"), "BUILD_PLAN", "build_plan")
        assert planning.agent.invoke(planning.prepared.state.request).outcome == "COMPLETED"
        plan = planning.receipts[-1].data
        assert plan.planning_needs and plan.milestones and plan.skill_gap_audit
        for harness, name in ((recommend, "get_recommendations"), (skill, "analyze_skill_gap"),
                              (planning, "build_plan")):
            gateway = GatewayHarness(harness.facade)
            before = list(harness.calls)
            async with gateway.connect() as client:
                assert name not in {t.name for t in (await client.list_tools(cache_mode="bypass")).tools}
                with pytest.raises(MCPError):
                    await client.call_tool(name, arguments())
            assert harness.calls == before
    run(scenario)
