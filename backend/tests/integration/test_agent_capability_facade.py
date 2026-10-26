"""Offline P12.2 boundaries over real authorities; controlled test facts only."""

import ast
import inspect
import json
import runpy
import socket
from pathlib import Path

import pytest
from pydantic import ValidationError

from competition_copilot.agents import capabilities
from competition_copilot.agents.capabilities import (
    AgentCapabilityFacade,
    AgentCapabilityResult,
    CapabilityArguments,
    CapabilityMetadata,
    CapabilityStatus,
)
from competition_copilot.agents.contracts import (
    AgentIntent,
    CapabilityId,
    CapabilityInvocationRequest,
    ReferenceKind,
    ResultReference,
)
from competition_copilot.application.competition_snapshots import (
    CompetitionSnapshotBuilder,
)
from competition_copilot.application.eligibility import CompetitionEligibilityEvaluator
from competition_copilot.domain.baseline_plan_builder import (
    BaselineCompetitionPlanBuilder,
)
from competition_copilot.domain.digital_twin import CompetitionSnapshot
from competition_copilot.domain.event_aggregation import CompetitionEventAggregator
from competition_copilot.domain.event_engine import CompetitionEventEngine
from competition_copilot.domain.event_impact_analyzer import (
    CompetitionEventImpactAnalyzer,
)
from competition_copilot.domain.plan_revision_service import PlanRevisionService
from competition_copilot.domain.planning_inputs import PlanningInputDeriver
from competition_copilot.domain.recommendation_ranking import (
    RecommendationRankingEngine,
)
from competition_copilot.domain.replanning_decision_service import (
    ReplanningDecisionService,
)
from competition_copilot.domain.replanning_input import (
    ReplanningInput,
    RevisionAuthority,
    UpdateMilestoneInstruction,
    replanning_decision_fingerprint,
)
from competition_copilot.domain.skill import SkillLevel
from competition_copilot.domain.skill_gap import SkillRequirementType
from competition_copilot.domain.skill_gap_engine import SkillGapEngine
from competition_copilot.domain.snapshot_diff_engine import SnapshotDiffEngine
from competition_copilot.domain.student import StudentProfile
from competition_copilot.infrastructure.eligibility_policy_json import (
    JsonEligibilityPolicyProvider,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.tools.competition import (
    GetCompetitionEditionTool,
    GetCompetitionTool,
    GetCompetitionTrackTool,
    ListCompetitionEditionsTool,
    ListCompetitionsTool,
    ListEditionTracksTool,
)

ROOT = Path(__file__).resolve().parents[3]
TESTS = ROOT / "backend" / "tests"
# Reuse frozen fixture builders, never duplicate the P5/P6/P7/P8/P11 pipelines.
P5 = runpy.run_path(str(TESTS / "application" / "test_eligibility_evaluator.py"))
P6 = runpy.run_path(str(TESTS / "domain" / "test_recommendation_scoring.py"))
P7 = runpy.run_path(str(TESTS / "domain" / "test_skill_gap_engine.py"))
P11 = runpy.run_path(str(TESTS / "integration" / "test_real_adaptive_replanning.py"))
P8 = runpy.run_path(str(TESTS / "integration" / "test_p8_real_planning_integration.py"))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def reject(*args, **kwargs):
        pytest.fail("Capability facade must run offline")
    monkeypatch.setattr(socket, "create_connection", reject)
    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)


@pytest.fixture
def facade():
    repository = JsonSeedCompetitionRepository(ROOT / "data" / "seed")
    read_tools = {
        CapabilityId.LIST_COMPETITIONS: ListCompetitionsTool(repository),
        CapabilityId.GET_COMPETITION: GetCompetitionTool(repository),
        CapabilityId.LIST_EDITIONS: ListCompetitionEditionsTool(repository),
        CapabilityId.GET_EDITION: GetCompetitionEditionTool(repository),
        CapabilityId.LIST_TRACKS: ListEditionTracksTool(repository),
        CapabilityId.GET_TRACK: GetCompetitionTrackTool(repository),
    }
    scoring, _ = P6["engine"]([0.8])
    return AgentCapabilityFacade(
        read_tools=read_tools,
        eligibility=CompetitionEligibilityEvaluator(
            repository, JsonEligibilityPolicyProvider(ROOT / "data" / "eligibility")),
        scoring=scoring, ranking=RecommendationRankingEngine(),
        skill_gap=SkillGapEngine(), planning_inputs=PlanningInputDeriver(),
        planner=BaselineCompetitionPlanBuilder(), snapshot_diff=SnapshotDiffEngine(),
        snapshot_builder=CompetitionSnapshotBuilder(repository),
        event_engine=CompetitionEventEngine(), event_aggregator=CompetitionEventAggregator(),
        impact=CompetitionEventImpactAnalyzer(), replanning=ReplanningDecisionService(),
        revision=PlanRevisionService(),
    )


def invocation(capability):
    return CapabilityInvocationRequest(
        invocation_id="controlled-invocation", source_request_id="controlled-request",
        intent=AgentIntent.EXPLAIN_REPLANNING, capability=capability,
        arguments_ref=ResultReference(kind=ReferenceKind.CAPABILITY_ARGUMENTS,
                                     ref_id="controlled-arguments"),
        requires_approval=capability == CapabilityId.REVISE_PLAN,
    )


def call(facade, capability, payload):
    request = invocation(capability)
    return facade.execute(request, {
        "artifact_ref": request.arguments_ref.model_dump(mode="json"),
        "payload": payload.model_dump() if hasattr(payload, "model_dump") else payload,
    }, result_ref=ResultReference(kind=ReferenceKind.TOOL_RESULT, ref_id="controlled-result"))


def roundtrip(result):
    standard = json.dumps(result.model_dump(mode="json"), allow_nan=False)
    restored = AgentCapabilityResult.model_validate_json(standard)
    assert restored == result
    assert restored.model_dump_json() == result.model_dump_json()
    document = result.model_dump(mode="json")
    for reference in result.audit.results:
        prefix = result.result_ref.ref_id + "#"
        if reference.ref_id.startswith(prefix):
            node = document
            for part in reference.ref_id.removeprefix(prefix).lstrip("/").split("/"):
                key = part.replace("~1", "/").replace("~0", "~")
                node = node[int(key)] if isinstance(node, list) else node[key]
            assert node is not None


def test_explicit_inventory_and_metadata(facade):
    expected = {
        "list_competitions", "get_competition", "list_competition_editions",
        "get_competition_edition", "list_edition_tracks", "get_competition_track",
        "check_eligibility", "get_recommendations", "analyze_skill_gap", "build_plan",
        "build_competition_snapshot", "diff_competition_snapshot", "derive_competition_events",
        "analyze_event_impact", "decide_replanning", "revise_plan",
        "get_competition_details", "get_profile", "update_profile", "get_profile_analyses",
        "get_skill_catalog", "add_profile_skill", "update_profile_skill", "remove_profile_skill",
    }
    metadata = facade.list_capabilities()
    assert {m.capability.value for m in metadata} == expected
    assert [m.capability.value for m in metadata] == sorted(expected)
    for item in metadata:
        assert CapabilityMetadata.model_validate_json(json.dumps(item.model_dump(mode="json"))) == item
        assert json.loads(item.input_schema_json)["properties"]["payload"]
        assert item.requires_explicit_approval == (item.capability == CapabilityId.REVISE_PLAN)
        # Profile self-edit is authorized by its Application actor binding;
        # plan revision alone retains the separate human approval workflow.
        assert (item.access == "MUTATING") == (item.capability in (
            CapabilityId.REVISE_PLAN, CapabilityId.UPDATE_PROFILE, CapabilityId.ADD_PROFILE_SKILL,
            CapabilityId.UPDATE_PROFILE_SKILL, CapabilityId.REMOVE_PROFILE_SKILL))
    assert facade.list_capabilities() == metadata


@pytest.mark.parametrize("capability,payload", [
    (CapabilityId.LIST_COMPETITIONS, {}),
    (CapabilityId.GET_COMPETITION, {"competition_id": "huawei-ict"}),
    (CapabilityId.LIST_EDITIONS, {"competition_id": "huawei-ict"}),
    (CapabilityId.GET_EDITION, {"edition_id": "huawei-ict-2026"}),
    (CapabilityId.LIST_TRACKS, {"edition_id": "huawei-ict-2026"}),
    (CapabilityId.GET_TRACK, {"track_id": "huawei-ict-2026-innovation"}),
])
def test_real_repository_read_tools_and_deterministic_dispatch(facade, capability, payload):
    result = call(facade, capability, payload)
    assert result.status == CapabilityStatus.SUCCESS and result.error is None
    assert result.source_request_id == "controlled-request"
    assert result.model_dump_json() == call(facade, capability, payload).model_dump_json()
    roundtrip(result)


def test_real_eligibility_application_preserves_sources(facade):
    payload = {"student": StudentProfile(id="controlled-graduate", education_level="graduate"),
               "competition_id": "gcxl-engineering-practice-innovation",
               "edition_id": "gcxl-engineering-practice-innovation-2027"}
    result = call(facade, CapabilityId.CHECK_ELIGIBILITY, payload)
    expected = facade._eligibility.evaluate(**{
        "student_profile": payload["student"], "competition_id": payload["competition_id"],
        "edition_id": payload["edition_id"],
    })
    assert result.status == "SUCCESS" and result.data == expected
    assert result.data.status.value == "ineligible"
    assert result.data.evidence[0].source is not None
    assert any(r.kind == ReferenceKind.SOURCE for r in result.audit.results)
    assert result.audit.reasons and any(r.kind == ReferenceKind.EVIDENCE for r in result.audit.results)
    roundtrip(result)


@pytest.mark.parametrize("level,status", [("graduate", "eligible"),
                                          ("undergraduate", "ineligible"), (None, "unknown")])
def test_eligibility_business_outcomes_all_success(level, status):
    boundary = CompetitionEligibilityEvaluator(P5["FakeRepository"](), P5["FakeProvider"](P5["policy"]()))
    facade = AgentCapabilityFacade(eligibility=boundary)
    result = call(facade, CapabilityId.CHECK_ELIGIBILITY, {
        "student": StudentProfile(id="s", education_level=level),
        "competition_id": "competition-a", "edition_id": "edition-a",
    })
    assert result.status == "SUCCESS" and result.data.status == status
    assert result.error is None
    roundtrip(result)


def test_recommendation_preserves_buckets_without_hidden_eligibility(facade):
    from competition_copilot.domain.eligibility import EligibilityStatus
    contexts = []
    for index, status in enumerate(EligibilityStatus):
        context = P6["context"](status)
        # Distinct controlled targets, all through normal P6 constructors.
        payload = context.model_dump()
        payload["candidate"]["competition_id"] = "c" + str(index)
        payload["competition"]["id"] = "c" + str(index)
        payload["edition"]["competition_id"] = "c" + str(index)
        payload["eligibility_decision"]["competition_id"] = "c" + str(index)
        contexts.append(type(context).model_validate(payload))
    result = call(facade, CapabilityId.GET_RECOMMENDATIONS, {"contexts": tuple(contexts)})
    assert result.status == "SUCCESS"
    assert len(result.data.confirmed) == len(result.data.uncertain) == len(result.data.blocked) == 1
    expected = facade._ranking.rank(tuple(facade._scoring.evaluate(c) for c in contexts))
    assert result.data == expected
    reordered = call(facade, CapabilityId.GET_RECOMMENDATIONS,
                     {"contexts": tuple(reversed(contexts))})
    assert result.model_dump_json() == reordered.model_dump_json()
    assert result.audit.reasons
    roundtrip(result)


@pytest.mark.parametrize("level,expected", [(SkillLevel.BEGINNER, "gap_identified"),
                                           (SkillLevel.ADVANCED, "no_gap"), (None, "undetermined")])
def test_skill_gap_and_real_p8_chain_preserve_uncertainty(facade, level, expected):
    context = P7["make_context"]([("math", SkillLevel.ADVANCED, level, SkillRequirementType.REQUIRED)])
    original = context.model_dump_json()
    result = call(facade, CapabilityId.ANALYZE_SKILL_GAP, {"context": context})
    assert result.status == "SUCCESS" and result.data.gap_status == expected
    assert context.model_dump_json() == original
    roundtrip(result)
    plan = call(facade, CapabilityId.BUILD_PLAN, {
        "source_decision": result.data, "student_id": context.student_profile.id,
        "created_at": P11["T0"],
    })
    assert plan.status == "SUCCESS"
    assert plan.data.skill_gap_audit.gap_status == result.data.gap_status
    assert len(plan.data.milestones) == len(plan.data.planning_needs)
    if expected == "no_gap":
        assert plan.data.planning_needs == () and plan.data.milestones == ()
    else:
        assert plan.data.planning_needs[0].source_item == result.data.items[0]
    roundtrip(plan)


@pytest.mark.parametrize("mode,outcome,decision", [
    ("keep", "no_plan_impact", "keep_current_plan"),
    ("undetermined", "undetermined", "undetermined"),
    ("replan", "affects_plan", "replan"),
])
def test_real_p10_p11_chain_unchanged(facade, mode, outcome, decision):
    context = P11["real_context"].__wrapped__()
    before, student, _ = context
    original = before.model_dump_json()
    event = P11["controlled_event"](context, mode)
    event_result = call(facade, CapabilityId.DERIVE_COMPETITION_EVENTS, {
        "source_diff": event.source_diff, "detected_at": event.observed_at,
    })
    assert event_result.status == "SUCCESS" and event_result.data.events == (event,)
    impact_result = call(facade, CapabilityId.ANALYZE_EVENT_IMPACT, {
        "event": event_result.data.events[0], "student": student, "plan": before,
        "evaluated_at": P11["EVALUATED"],
    })
    assert impact_result.status == "SUCCESS" and impact_result.data.outcome == outcome
    decided = call(facade, CapabilityId.DECIDE_REPLANNING, {
        "impacts": (impact_result.data,), "plan": before, "evaluated_at": P11["DECIDED"],
    })
    assert decided.status == "SUCCESS" and decided.data.outcome == decision
    assert before.model_dump_json() == original
    for result in (event_result, impact_result, decided):
        roundtrip(result)
    if mode == "replan":
        assert decided.data.scope.whole_plan
        source = P11["authorized_cancellation"](before, decided.data)
        revised = call(facade, CapabilityId.REVISE_PLAN, {
            "before": before, "replanning_input": source, "executed_at": P11["EXECUTED"],
        })
        assert revised.status == "SUCCESS" and revised.data.after.status == "cancelled"
        assert revised.data.plan_diff.status_change is not None
        assert revised.data.after.track_id == before.track_id
        assert revised.data.after.milestones == before.milestones
        assert before.model_dump_json() == original
        roundtrip(revised)


def test_revision_partial_missing_authority_and_stale_version_rejected(facade):
    context = P11["real_context"].__wrapped__()
    before, _, _ = context
    impact = P11["impact_for"](context, "replan")
    decision = facade._replanning.decide((impact,), before, evaluated_at=P11["DECIDED"])
    valid = P11["authorized_cancellation"](before, decision)
    no_authority = valid.model_dump()
    no_authority["plan_status_instruction"].pop("authority")
    result = call(facade, CapabilityId.REVISE_PLAN, {
        "before": before, "replanning_input": no_authority, "executed_at": P11["EXECUTED"],
    })
    assert result.status == "ERROR" and result.error.code == "INVALID_INPUT"
    original = before.milestones[0]
    after = type(original)(**{**original.model_dump(), "due_at": P11["T0"]})
    instruction = UpdateMilestoneInstruction(
        operation="update_milestone", expected_plan=valid.plan_status_instruction.expected_plan,
        expected_before=original, after=after,
        source_decision_fingerprint=replanning_decision_fingerprint(decision),
        authority=RevisionAuthority(**valid.plan_status_instruction.authority.model_dump()),
    )
    partial = ReplanningInput(before=before, decision=decision, supplied_at=P11["APPROVED"],
                              status="partially_executable", instructions=(instruction,))
    result = call(facade, CapabilityId.REVISE_PLAN, {
        "before": before, "replanning_input": partial, "executed_at": P11["EXECUTED"],
    })
    assert result.status == "ERROR" and result.error.code == "EXECUTION_REJECTED"
    wrong_version = type(before)(**{**before.model_dump(), "version": before.version + 1})
    result = call(facade, CapabilityId.REVISE_PLAN, {
        "before": wrong_version, "replanning_input": valid, "executed_at": P11["EXECUTED"],
    })
    assert result.status == "ERROR" and result.data is None
    roundtrip(result)


def test_replanning_precedence_uncertainty_and_order_preserved(facade):
    context = P11["real_context"].__wrapped__()
    before = context[0]
    impacts = tuple(P11["impact_for"](context, mode) for mode in ("keep", "undetermined", "replan"))
    negative_unknown = call(facade, CapabilityId.DECIDE_REPLANNING, {
        "impacts": impacts[:2], "plan": before, "evaluated_at": P11["DECIDED"],
    })
    assert negative_unknown.status == "SUCCESS" and negative_unknown.data.outcome == "undetermined"
    first = call(facade, CapabilityId.DECIDE_REPLANNING, {
        "impacts": impacts, "plan": before, "evaluated_at": P11["DECIDED"],
    })
    second = call(facade, CapabilityId.DECIDE_REPLANNING, {
        "impacts": tuple(reversed(impacts)), "plan": before, "evaluated_at": P11["DECIDED"],
    })
    assert first.status == "SUCCESS" and first.data.outcome == "replan"
    assert first.data.scope.state == "partially_resolved"
    assert first.model_dump_json() == second.model_dump_json()
    roundtrip(first)


def test_approval_response_cannot_replace_structured_revision_input(facade):
    result = call(facade, CapabilityId.REVISE_PLAN, {
        "approval_request_id": "controlled-approval", "decision": "APPROVE",
        "submitted_at": P11["APPROVED"],
    })
    assert result.status == "ERROR" and result.error.code == "INVALID_INPUT"


def test_naive_time_and_arbitrary_handle_fail_before_delegation(facade):
    context = P11["real_context"].__wrapped__()
    before, student, _ = context
    event = P11["controlled_event"](context, "keep")
    result = call(facade, CapabilityId.ANALYZE_EVENT_IMPACT, {
        "event": event, "student": student, "plan": before,
        "evaluated_at": P11["EVALUATED"].replace(tzinfo=None),
    })
    assert result.status == "ERROR" and result.error.code == "INVALID_INPUT"
    request = invocation(CapabilityId.LIST_COMPETITIONS)
    result = facade.execute(request, object(), result_ref=ResultReference(
        kind=ReferenceKind.TOOL_RESULT, ref_id="r"))
    assert result.error.code == "INVALID_INPUT"


def test_snapshot_diff_does_not_turn_unknown_into_removal(facade):
    context = P11["real_context"].__wrapped__()
    event = P11["controlled_event"](context, "replan")
    reference = event.source_diff.before
    source = event.source
    dynamic = {
        "registration_window": {"state": "unknown"},
        "competition_window": {"state": "unknown"},
        "track_membership": {"state": "known_value", "value": context[2], "sources": (source,)},
    }
    before = CompetitionSnapshot(snapshot_id="controlled-before", target=reference.target,
                                 observed_at=P11["OBSERVED"], dynamic_state=dynamic)
    after = CompetitionSnapshot(snapshot_id="controlled-after", target=reference.target,
                                observed_at=P11["EVALUATED"], dynamic_state={
                                    **dynamic, "track_membership": {"state": "unknown"}})
    result = call(facade, CapabilityId.DIFF_COMPETITION_SNAPSHOT, {"before": before, "after": after})
    assert result.status == "SUCCESS"
    assert result.data.changes[0].kind == "observation_state_changed"
    roundtrip(result)


def test_real_repository_backed_snapshot_application(facade):
    result = call(facade, CapabilityId.BUILD_COMPETITION_SNAPSHOT, {
        "target": {"competition_id": "huawei-ict", "edition_id": "huawei-ict-2026"},
        "observed_at": P11["OBSERVED"],
    })
    assert result.status == "SUCCESS"
    assert result.data.target.competition_id == "huawei-ict"
    assert result.data.dynamic_state.track_membership.state == "known_value"
    roundtrip(result)


def test_real_sourced_comap_planning_results_are_not_simplified(facade):
    real_inputs = P8["real_inputs"].__wrapped__()
    context, expected_decision, _, expected_plan = P8["run_pipeline"](
        real_inputs, True, (SkillGapEngine(), PlanningInputDeriver(), BaselineCompetitionPlanBuilder()),
    )
    result = call(facade, CapabilityId.ANALYZE_SKILL_GAP, {"context": context})
    assert result.data == expected_decision
    plan = call(facade, CapabilityId.BUILD_PLAN, {
        "source_decision": result.data, "student_id": context.student_profile.id,
        "created_at": P8["CREATED_AT"],
    })
    assert plan.status == "SUCCESS" and plan.data == expected_plan
    assert any(need.source_item is not None for need in plan.data.planning_needs)
    assert any(ref.kind == ReferenceKind.SOURCE for ref in plan.audit.results)
    roundtrip(plan)


@pytest.mark.parametrize("payload", [{}, {"competition_id": lambda: None},
                                     {"competition_id": object()}, {"competition_id": "x", "extra": "x"}])
def test_invalid_typed_payload_rejected(facade, payload):
    result = call(facade, CapabilityId.GET_COMPETITION, payload)
    assert result.status == "ERROR" and result.error.code == "INVALID_INPUT"


def test_unsupported_missing_dependency_not_found_and_ref_mismatch(facade):
    deferred = call(facade, CapabilityId.EXPLAIN_REPLANNING, {})
    assert deferred.error.code == "UNSUPPORTED_CAPABILITY"
    request = invocation(CapabilityId.GET_COMPETITION).model_dump()
    request["capability"] = "not_an_approved_capability"
    result = facade.execute(request, {}, result_ref=ResultReference(
        kind=ReferenceKind.TOOL_RESULT, ref_id="r"))
    assert result.error.code == "UNSUPPORTED_CAPABILITY" and result.capability is None
    missing = call(AgentCapabilityFacade(), CapabilityId.LIST_COMPETITIONS, {})
    assert missing.error.code == "DEPENDENCY_UNAVAILABLE"
    absent = call(facade, CapabilityId.GET_COMPETITION, {"competition_id": "absent"})
    assert absent.error.code == "NOT_FOUND"
    result = facade.execute(invocation(CapabilityId.LIST_COMPETITIONS), {
        "artifact_ref": ResultReference(kind=ReferenceKind.CAPABILITY_ARGUMENTS, ref_id="wrong"),
        "payload": {},
    }, result_ref=ResultReference(kind=ReferenceKind.TOOL_RESULT, ref_id="r"))
    assert result.error.code == "INVALID_INPUT"
    for result in (deferred, missing, absent, result):
        roundtrip(result)


def test_success_error_exclusive_and_arguments_json(facade):
    result = call(facade, CapabilityId.GET_COMPETITION, {"competition_id": "huawei-ict"})
    for change in ({"data": None}, {"error": {"code": "INVALID_INPUT", "message": "Invalid"}},
                   {"status": "ERROR"}):
        with pytest.raises(ValidationError):
            AgentCapabilityResult.model_validate({**result.model_dump(), **change})
    for cap, (input_type, _) in capabilities._SPECS.items():
        metadata = next(m for m in facade.list_capabilities() if m.capability == cap)
        assert json.loads(metadata.input_schema_json) == CapabilityArguments[input_type].model_json_schema()


def test_no_business_platform_or_automatic_exposure_code():
    tree = ast.parse(inspect.getsource(capabilities))
    imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any("infrastructure" in name or "agentarts" in name for name in imports)
    text = inspect.getsource(capabilities)
    for forbidden in ("StateGraph", "ChatOpenAI", "RequestContext", "subprocess", "getattr(",
                      "LEVEL_ORDER", "DEFAULT_RECOMMENDATION_THRESHOLD", "_FACT_TYPES"):
        assert forbidden not in text
