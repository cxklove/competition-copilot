"""Real Runtime actions, trusted result retention and exact read-side composition."""

import asyncio
import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.integrations.local_runtime.composition import create_local_host
from competition_copilot.integrations.mcp.registry import build_mcp_tool_registry

ROOT = Path(__file__).resolve().parents[3]
STUDENT = "local-recommendation-demo"
TARGET = {"competition_id": "comap-mcm", "edition_id": "comap-mcm-2027", "track_id": None}


@pytest.fixture(scope="module")
def reviewed_root(tmp_path_factory):
    """Replay reviewed fixture bytes in OS temp; do not repair checkout/CI here.

    The separately recorded CI_PIPELINE_STABILITY_GAP includes raw checkout byte
    drift. This fixture preserves the provider's exact digest admission and leaves
    the original checkout untouched; full checkout regression is reported separately.
    """
    root = tmp_path_factory.mktemp("my-competitions-reviewed")
    shutil.copytree(ROOT / "data", root / "data")
    manifest = json.loads((root / "data/review/p2-batch-01.json").read_text(encoding="utf-8"))
    entries = next(v for v in manifest.values() if isinstance(v, list))
    for entry in entries:
        path = root / entry["raw_fixture_path"]
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["raw_sha256"]:
            replay = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            assert hashlib.sha256(replay).hexdigest() == entry["raw_sha256"]
            path.write_bytes(replay)
    return root


@pytest.fixture
def host(reviewed_root):
    return create_local_host(reviewed_root)


def invoke(host, intent, *, target=TARGET, student=STUDENT, command=None, **extra):
    request = {"request_id": "test-" + intent, "user_message": intent, "intent": intent,
        "context": {"student_id": student, **({k: v for k, v in target.items() if v is not None} if target else {})}, **extra}
    if command is not None:
        request["my_competition_command"] = {"student_id": student, "target": target, **command}
    return asyncio.run(host.invoke({"request": request}))


def artifact(result, model):
    assert result["runtime"].get("response", {}).get("outcome") == "COMPLETED", result
    return next(a["value"] for a in result["presentation"]["artifacts"] if a["model"] == model)


def add(host, **kwargs):
    return artifact(invoke(host, "ADD_MY_COMPETITION", command={"operation": "add"}, **kwargs), "MyCompetitionMutationResult")


def listing(host):
    return artifact(invoke(host, "GET_MY_COMPETITIONS", target=None), "MyCompetitionsProjection")["competitions"]


@pytest.mark.parametrize("edition", [None, "", " "])
def test_add_rejects_incomplete_edition_and_persists_nothing(host, edition):
    target = {"competition_id": "china-graduate-math-modeling"}
    if edition is not None:
        target["edition_id"] = edition
    response = invoke(host, "ADD_MY_COMPETITION", target=target, command={"operation": "add"})
    assert response["runtime"]["error"]["message"] == "TARGET_INCOMPLETE: EDITION_REQUIRED"
    assert listing(host) == []


@pytest.mark.parametrize("edition", ["china-graduate-math-modeling-2026", "comap-mcm-2027", "invented"])
def test_structured_edition_choice_resumes_exact_p7_or_rejects_foreign_choice(host, edition):
    from datetime import datetime, timezone

    target = {"competition_id": "china-graduate-math-modeling"}
    first = invoke(host, "ANALYZE_SKILL_GAP", target=target)
    question = first["runtime"]["response"]["clarification"]
    assert question["fields"] == ["EDITION"]
    assert [(o["value"], o["label"]) for o in question["options"]] == [(
        "china-graduate-math-modeling-2026", "2026年“华为杯”第二十三届中国研究生数学建模竞赛")]
    result = asyncio.run(host.invoke({"continuation_ref": first["runtime"]["continuation_ref"],
        "clarification": {"clarification_id": question["clarification_id"],
            "source_request_id": question["source_request_id"],
            "values": {"edition_id": edition}, "submitted_at": datetime.now(timezone.utc).isoformat()}}))
    if edition != "china-graduate-math-modeling-2026":
        assert result["runtime"]["response"]["outcome"] == "FAILED"
        return
    decision = artifact(result, "SkillGapDecision")
    assert decision["target"] == {**target, "edition_id": edition, "track_id": None, "scope": "edition"}
    # UNKNOWN is allowed Domain truth; successful execution is not unresolved input.
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"


def test_relationship_exact_target_reused_by_skill_gap_without_clarification(host):
    saved = add(host, target={"competition_id": "china-graduate-math-modeling",
        "edition_id": "china-graduate-math-modeling-2026", "track_id": None})
    exact = saved["snapshot"]["relationship_ref"]["target"]
    response = invoke(host, "ANALYZE_SKILL_GAP", target=exact)
    assert response["runtime"]["response"]["clarification"] is None
    assert artifact(response, "SkillGapDecision")["target"] == {**exact, "scope": "edition"}


def test_read_and_crud_are_only_own_capabilities_no_business_side_effects(host, monkeypatch):
    calls = []
    execute = AgentCapabilityFacade.execute
    def observe(self, invocation, *args, **kwargs):
        calls.append(invocation.capability.value)
        return execute(self, invocation, *args, **kwargs)
    monkeypatch.setattr(AgentCapabilityFacade, "execute", observe)
    assert listing(host) == []
    saved = add(host)
    row = listing(host)[0]
    assert row["display_identity"]["competition_name"] == "COMAP Mathematical Contest in Modeling"
    assert row["display_identity"]["edition_name"]
    assert row["relationship_state"] == "SAVED"
    assert row["eligibility_summary"]["availability"] == "NOT_ANALYZED"
    assert row["skill_gap_summary"]["availability"] == "NOT_ANALYZED"
    assert row["plan_summary"]["availability"] == "NOT_SELECTED"
    assert row["planning_summary"]["has_advisory"] is True
    assert row["next_action"]["kind"] == "ELIGIBILITY"
    updated = artifact(invoke(host, "UPDATE_MY_COMPETITION", command={"operation": "update", "state": "PREPARING",
        "expected_reference": saved["snapshot"]["relationship_ref"]}), "MyCompetitionMutationResult")
    assert updated["snapshot"]["relationship"]["version"] == 2
    artifact(invoke(host, "REMOVE_MY_COMPETITION", command={"operation": "remove",
        "expected_reference": updated["snapshot"]["relationship_ref"]}), "MyCompetitionMutationResult")
    assert listing(host) == []
    assert calls == ["get_my_competitions", "add_my_competition", "get_my_competitions",
        "update_my_competition", "remove_my_competition", "get_my_competitions"]


def test_explicit_results_retained_prerequisites_not_selected_remove_and_readd_preserve_truth(host):
    saved = add(host)
    plan_result = invoke(host, "BUILD_PLAN")
    plan = artifact(plan_result, "CompetitionPlan")
    plan_ref = plan_result["runtime"]["response"]["plan_refs"][0]
    first = listing(host)[0]
    assert first["skill_gap_summary"]["availability"] == "NOT_ANALYZED"  # P8 prerequisite is not a selection.
    assert first["plan_summary"]["plan_ref"] == plan_ref
    assert first["plan_summary"]["profile_freshness"]["status"] == "CURRENT"
    artifact(invoke(host, "CHECK_ELIGIBILITY"), "EligibilityDecision")
    artifact(invoke(host, "ANALYZE_SKILL_GAP"), "SkillGapDecision")
    before = listing(host)[0]
    for kind in ("eligibility_summary", "skill_gap_summary", "plan_summary"):
        assert before[kind]["availability"] == "AVAILABLE"
        assert before[kind]["profile_freshness"]["input_profile_ref"]["student_id"] == STUDENT
    profile = host.profile_repository.get(STUDENT)
    invoke(host, "UPDATE_PROFILE", target=None, profile_update={"expected_profile_ref": profile.profile_ref.model_dump(mode="json"),
        "patch": {"weekly_available_hours": 12}})
    after = listing(host)[0]
    for kind in ("eligibility_summary", "skill_gap_summary", "plan_summary"):
        assert after[kind]["profile_freshness"]["status"] == "STALE"
        assert after[kind]["audit_json"] == before[kind]["audit_json"]
    original = host.plan_registry.resolve(plan_ref)
    assert original.model_dump(mode="json") == plan
    artifact(invoke(host, "REMOVE_MY_COMPETITION", command={"operation": "remove",
        "expected_reference": saved["snapshot"]["relationship_ref"]}), "MyCompetitionMutationResult")
    assert listing(host) == []
    add(host)
    assert listing(host)[0]["plan_summary"]["plan_ref"] == plan_ref
    assert host.plan_registry.resolve(plan_ref).model_dump(mode="json") == plan


def test_body_missing_is_unavailable_not_not_analyzed_and_reader_does_not_select(host, monkeypatch):
    add(host)
    invoke(host, "CHECK_ELIGIBILITY")
    before = listing(host)[0]
    def no_body(_): return None
    monkeypatch.setattr(host.derived_result_store, "resolve", no_body)
    after = listing(host)[0]
    assert after["eligibility_summary"]["availability"] == "UNAVAILABLE"
    assert after["eligibility_summary"]["result_ref"] == before["eligibility_summary"]["result_ref"]


def test_exact_get_duplicate_conflict_and_parent_validation(host):
    saved = add(host)
    exact = artifact(invoke(host, "GET_MY_COMPETITION"), "MyCompetitionProjection")
    assert exact["relationship_ref"] == saved["snapshot"]["relationship_ref"]
    duplicate = invoke(host, "ADD_MY_COMPETITION", command={"operation": "add"})
    assert duplicate["runtime"]["response"]["outcome"] == "FAILED"
    bad_ref = deepcopy(exact["relationship_ref"])
    bad_ref["version"] += 1
    rejected = invoke(host, "REMOVE_MY_COMPETITION", command={"operation": "remove", "expected_reference": bad_ref})
    assert rejected["runtime"]["response"]["outcome"] == "FAILED"
    assert len(listing(host)) == 1
    for target in ({"competition_id": "huawei-ict", "edition_id": "comap-mcm-2027"},
                   {"competition_id": "comap-mcm", "edition_id": "comap-mcm-2027", "track_id": "not-a-track"},
                   {"competition_id": "comap-mcm", "edition_id": "comap-mcm-2027", "track_id": "huawei-ict-2026-practice"}):
        result = invoke(host, "ADD_MY_COMPETITION", target=target, command={"operation": "add"})
        assert result["runtime"]["response"]["outcome"] == "FAILED"
    for track in (None, "huawei-ict-2026-practice"):
        created = add(host, target={"competition_id": "huawei-ict", "edition_id": "huawei-ict-2026", "track_id": track})
        assert created["snapshot"]["relationship"]["track_id"] == track


def test_authorization_and_restart_empty(reviewed_root):
    limited = create_local_host(reviewed_root, permitted_profile_ids=(STUDENT,))
    for intent, command in [("GET_MY_COMPETITIONS", None), ("ADD_MY_COMPETITION", {"operation": "add"})]:
        result = invoke(limited, intent, student="local-graduate", command=command)
        assert result["runtime"]["response"]["outcome"] == "FAILED"
    add(limited)
    assert listing(create_local_host(reviewed_root)) == []


def test_explicit_plan_selection_resolves_exact_and_keeps_original_lineage(host):
    add(host)
    generated = invoke(host, "BUILD_PLAN")
    ref = generated["runtime"]["response"]["plan_refs"][0]
    original = listing(host)[0]["plan_summary"]["profile_freshness"]["input_profile_ref"]
    profile = host.profile_repository.get(STUDENT)
    invoke(host, "UPDATE_PROFILE", target=None, profile_update={"expected_profile_ref": profile.profile_ref.model_dump(mode="json"),
        "patch": {"weekly_available_hours": 0}})
    request = {"request_id": "select-plan", "user_message": "Select exact plan", "intent": "SELECT_MY_COMPETITION_PLAN",
        "context": {"student_id": STUDENT, **TARGET, "plan_ref": ref}}
    selected = asyncio.run(host.invoke({"request": request}))
    artifact(selected, "MyPlanSelectionResult")
    summary = listing(host)[0]["plan_summary"]
    assert summary["profile_freshness"]["input_profile_ref"] == original
    assert summary["profile_freshness"]["status"] == "STALE"
    ref["content_digest"] = "f" * 64
    assert asyncio.run(host.invoke({"request": request}))["runtime"]["response"]["outcome"] == "FAILED"


def test_exposure_and_capability_classification():
    definitions = {m.capability.value: m for m in AgentCapabilityFacade().list_capabilities()}
    exposed = {m.capability_id.value for m in build_mcp_tool_registry().tools}
    for name in ("get_my_competitions", "get_my_competition", "add_my_competition",
                 "update_my_competition", "remove_my_competition", "select_my_competition_plan"):
        assert name not in exposed
        assert definitions[name].access == ("READ" if name.startswith("get_") else "MUTATING")
        assert not definitions[name].requires_explicit_approval


@pytest.mark.parametrize("intent,kind", [("CHECK_ELIGIBILITY", "eligibility_summary"),
    ("ANALYZE_SKILL_GAP", "skill_gap_summary"), ("BUILD_PLAN", "plan_summary")])
def test_invocation_profile_binding_survives_profile_change_before_result_retention(host, monkeypatch, intent, kind):
    from competition_copilot.repositories.student import StudentProfileSnapshot
    add(host)
    before = host.profile_repository.get(STUDENT)
    execute = AgentCapabilityFacade.execute
    capability = {"CHECK_ELIGIBILITY": "check_eligibility", "ANALYZE_SKILL_GAP": "analyze_skill_gap", "BUILD_PLAN": "build_plan"}[intent]
    def racing(self, invocation, *args, **kwargs):
        result = execute(self, invocation, *args, **kwargs)
        if result.status == "SUCCESS" and invocation.capability == capability:
            host.profile_repository.replace(StudentProfileSnapshot(**{
                **before.domain_profile().model_dump(), "weekly_available_hours": 12}),
                expected=before.profile_ref, actor="test-race", updated_at=before.updated_at)
        return result
    monkeypatch.setattr(AgentCapabilityFacade, "execute", racing)
    invoke(host, intent)
    summary = listing(host)[0][kind]
    assert summary["availability"] == "AVAILABLE"
    assert summary["profile_freshness"]["input_profile_ref"] == before.profile_ref.model_dump(mode="json")
    assert summary["profile_freshness"]["status"] == "STALE"


def test_corrupt_selected_reference_never_falls_back_to_other_result(host, monkeypatch):
    from competition_copilot.repositories.student_competition import (
        DerivedResultReference,
    )
    add(host)
    invoke(host, "CHECK_ELIGIBILITY")
    selected = host.derived_result_store.selected
    def invalid(student, target, kind):
        ref = selected(student, target, kind)
        return DerivedResultReference(**{**ref.model_dump(), "content_digest": "f" * 64}) if ref else None
    monkeypatch.setattr(host.derived_result_store, "selected", invalid)
    row = listing(host)[0]
    assert row["eligibility_summary"]["availability"] == "INVALID_REFERENCE"
    assert row["eligibility_summary"]["status"] is None


def test_time_candidate_and_scope_are_references_only(host):
    target = {"competition_id": "robomaster", "edition_id": "robomaster-rmuc-2026"}
    # Resolve the actual reviewed competition parent instead of guessing from its name.
    from competition_copilot.infrastructure.repositories.json_seed import (
        JsonSeedCompetitionRepository,
    )
    repository = JsonSeedCompetitionRepository(ROOT / "data/seed")
    target["competition_id"] = repository.get_edition(target["edition_id"]).competition_id
    add(host, target=target)
    row = artifact(invoke(host, "GET_MY_COMPETITION", target=target), "MyCompetitionProjection")
    candidates = [r for r in row["time_summary"]["references"] if r["kind"] == "OFFICIAL_CANDIDATE"]
    assert candidates
    assert all(r["value"] is None and r["verification"] == "pending" and r["scope"] == "edition" for r in candidates)
    assert row["plan_summary"]["availability"] == "NOT_SELECTED"


def test_provider_failure_is_not_not_analyzed_or_pending(host, monkeypatch):
    from competition_copilot.application.competition_detail import (
        CompetitionDetailReader,
    )
    add(host)
    def fail(*args, **kwargs):
        raise RuntimeError("provider unavailable")
    monkeypatch.setattr(CompetitionDetailReader, "read", fail)
    row = listing(host)[0]
    assert "PROVIDER_UNAVAILABLE" in row["section_availability"]
    assert row["time_summary"]["availability"] == "PROVIDER_UNAVAILABLE"
    assert row["planning_summary"]["availability"] == "PROVIDER_UNAVAILABLE"
    assert row["next_action"]["reason_code"] == "TARGET_UNAVAILABLE"


def test_explicit_relationship_actions_do_not_call_any_model(reviewed_root):
    from types import SimpleNamespace
    calls = []
    class NeverModel:
        def propose(self, *args, **kwargs):
            calls.append("model")
            raise AssertionError("No LLM for relationship actions")
        explain = propose
    models = SimpleNamespace(intent=NeverModel(), explanation=NeverModel(), human_interpreter=NeverModel())
    target = create_local_host(reviewed_root, cloud_models=models)
    saved = add(target)
    assert len(listing(target)) == 1
    artifact(invoke(target, "REMOVE_MY_COMPETITION", command={"operation": "remove",
        "expected_reference": saved["snapshot"]["relationship_ref"]}), "MyCompetitionMutationResult")
    assert calls == []


def test_storage_failure_is_explicit_and_does_not_impersonate_empty_collection(host, monkeypatch):
    def fail(*args):
        raise OSError("private storage path must not escape")
    monkeypatch.setattr(host.relationship_repository, "list_for_student", fail)
    result = invoke(host, "GET_MY_COMPETITIONS", target=None)
    assert result["runtime"]["response"]["outcome"] == "FAILED"
    assert "MY_COMPETITION_REPOSITORY_UNAVAILABLE" in json.dumps(result)
    assert "private storage path" not in json.dumps(result)


def test_natural_language_read_uses_model_only_for_routing(reviewed_root):
    from types import SimpleNamespace

    from competition_copilot.agents.routing import IntentRoutingProposal
    calls = []
    class RoutingModel:
        def propose(self, value):
            calls.append("route")
            return IntentRoutingProposal(intent="GET_MY_COMPETITIONS", candidate_capability="get_my_competitions",
                ambiguity="NONE", missing_context=())
    class NoExplanation:
        def explain(self, value):
            calls.append("explain")
            raise AssertionError("Read projection needs no LLM explanation")
    target = create_local_host(reviewed_root, cloud_models=SimpleNamespace(
        intent=RoutingModel(), explanation=NoExplanation(), human_interpreter=None))
    result = asyncio.run(target.invoke({"request": {"request_id": "natural-my-competitions",
        "user_message": "Which competitions am I preparing for?", "context": {"student_id": STUDENT}}}))
    assert artifact(result, "MyCompetitionsProjection")["competitions"] == []
    assert calls == ["route"]


@pytest.mark.parametrize("intent", ["CHECK_ELIGIBILITY", "GET_RECOMMENDATIONS", "ANALYZE_SKILL_GAP", "BUILD_PLAN"])
def test_derived_result_generation_never_creates_relationship(host, intent):
    assert listing(host) == []
    result = invoke(host, intent)
    assert result["runtime"]["response"]["outcome"] == "COMPLETED"
    assert listing(host) == []


def test_recommendation_prerequisites_do_not_replace_explicit_eligibility_selection(host):
    from competition_copilot.repositories.student_competition import MyCompetitionTarget
    invoke(host, "CHECK_ELIGIBILITY")
    target = MyCompetitionTarget(**TARGET)
    before = host.derived_result_store.selected(STUDENT, target, "ELIGIBILITY")
    assert before is not None
    invoke(host, "GET_RECOMMENDATIONS")
    assert host.derived_result_store.selected(STUDENT, target, "ELIGIBILITY") == before


def test_existing_exact_legacy_plan_selection_keeps_unknown_profile_lineage(host):
    from competition_copilot.domain.plan import CompetitionPlan
    from competition_copilot.domain.replanning import PlanReference
    raw = json.loads((ROOT / "data/local_runtime/controlled_revision.json").read_text(encoding="utf-8"))["proposal"]["before"]
    plan = CompetitionPlan.model_validate({**raw, "id": "legacy-my-competition", "student_id": STUDENT})
    reference = PlanReference.from_plan(plan)
    target = reference.target.model_dump(mode="json")
    host.plan_registry.register(plan)
    add(host, target=target)
    response = asyncio.run(host.invoke({"request": {"request_id": "legacy-selection", "intent": "SELECT_MY_COMPETITION_PLAN",
        "user_message": "Select existing historical plan", "context": {"student_id": STUDENT, **target,
            "plan_ref": reference.model_dump(mode="json")}}}))
    artifact(response, "MyPlanSelectionResult")
    row = artifact(invoke(host, "GET_MY_COMPETITION", target=target), "MyCompetitionProjection")
    assert row["plan_summary"]["plan_ref"] == reference.model_dump(mode="json")
    assert row["plan_summary"]["profile_freshness"]["status"] == "UNKNOWN"
    assert row["plan_summary"]["profile_freshness"]["input_profile_ref"] is None
