"""Profile-driven P6 uses backend candidates, independent of current target selection."""

import pytest
from test_generated_huawei_replanning import artifacts
from test_local_cloud_llm import ROOT, Chat, count, host, invoke, proposal, request
from test_profile_runtime import STUDENT
from test_profile_skill_runtime import call

from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("selection", [
    {},
    {"competition_id": "huawei-ict"},
    {"competition_id": "huawei-ict", "edition_id": "huawei-ict-2026"},
])
def test_profile_only_or_partial_target_ranks_formal_pool(monkeypatch, explicit, selection):
    chat = Chat(proposals=[proposal("GET_RECOMMENDATIONS", "get_recommendations")],
                intent_failure=explicit)
    target = host(chat)
    expected_ref = target.profile_repository.get(STUDENT).profile_ref
    prepared = []
    original = AgentCapabilityFacade.execute

    def observe(self, invocation, arguments, *, result_ref):
        if invocation.capability == "get_recommendations":
            prepared.append(arguments["payload"]["contexts"])
        return original(self, invocation, arguments, result_ref=result_ref)

    monkeypatch.setattr(AgentCapabilityFacade, "execute", observe)
    body = request("查看适合我的赛事推荐", {"student_id": STUDENT, **selection})
    if explicit:
        body["request"]["intent"] = "GET_RECOMMENDATIONS"
    result = invoke(target, body)
    assert result["runtime"]["response"]["outcome"] == "COMPLETED", result
    assert count(chat, "IntentRoutingProposal") == (0 if explicit else 1)
    assert len(prepared) == 1
    contexts = prepared[0]
    assert len(contexts) == 12
    # Enumerate all formal editions, not the current competition or latest edition.
    pairs = {(c["competition"]["id"], c["edition"]["id"]) for c in contexts}
    repository = JsonSeedCompetitionRepository(ROOT / "data/seed")
    assert pairs == {(competition.id, edition.id)
                     for competition in repository.list_competitions()
                     for edition in repository.list_editions_by_competition(competition.id)}
    assert len(pairs) == 12
    assert ("comap-mcm", "comap-mcm-2027") in pairs
    assert ("huawei-ict", "huawei-ict-2026") in pairs
    assert all(c["candidate"]["track_id"] is None for c in contexts)
    assert all(c["student_profile"]["id"] == STUDENT for c in contexts)
    ranking = artifacts(result, "RecommendationRankingResult")[0]
    assert sum(len(ranking[bucket]) for bucket in ("confirmed", "uncertain", "blocked")) == 12
    identity = next(a["ref"]["ref_id"] for a in result["presentation"]["artifacts"]
                    if a["model"] == "RecommendationRankingResult")
    assert target.profile_input_bindings[identity].input_profile_ref == expected_ref
    assert body["request"]["context"] == {"student_id": STUDENT, **selection}


@pytest.mark.parametrize("intent", ["CHECK_ELIGIBILITY", "ANALYZE_SKILL_GAP", "BUILD_PLAN"])
def test_exact_target_capabilities_still_require_target(intent):
    body = request("Explicit target analysis", {"student_id": STUDENT})
    body["request"]["intent"] = intent
    result = invoke(host(Chat(intent_failure=True)), body)
    assert result["runtime"]["response"]["outcome"] != "COMPLETED"
    assert not artifacts(result, "RecommendationRankingResult")


def test_explicit_rerun_reads_updated_repository_skill_and_changes_overlap_not_old_ranking():
    from copy import deepcopy

    from test_profile_freshness_runtime import freshness

    target = host(Chat(intent_failure=True))

    def set_level(level):
        current = target.profile_repository.get(STUDENT)
        result = call(target, "UPDATE_PROFILE_SKILL", {
            "operation": "update", "skill_id": "mathematical-modeling", "level": level,
            "expected_profile_ref": current.profile_ref.model_dump(mode="json"),
        })
        assert result["runtime"]["response"]["outcome"] == "COMPLETED"

    def recommend():
        body = request("Recommend from current profile", {"student_id": STUDENT})
        body["request"]["intent"] = "GET_RECOMMENDATIONS"
        result = invoke(target, body)
        assert result["runtime"]["response"]["outcome"] == "COMPLETED"
        entry = next(a for a in result["presentation"]["artifacts"]
                     if a["model"] == "RecommendationRankingResult")
        return entry["ref"]["ref_id"], entry["value"]

    def modeling_evaluations(ranking):
        return {item["evaluation"]["candidate"]["competition_id"]: item["evaluation"]
                for bucket in ("confirmed", "uncertain", "blocked") for item in ranking[bucket]
                if item["evaluation"]["candidate"]["competition_id"]
                in ("comap-mcm", "china-graduate-math-modeling")}

    set_level("intermediate")
    first_ref = target.profile_repository.get(STUDENT).profile_ref
    identity_a, ranking_a = recommend()
    original = deepcopy(ranking_a)
    assert target.profile_input_bindings[identity_a].input_profile_ref == first_ref
    assert freshness(target, [identity_a])[0]["profile_freshness"]["status"] == "CURRENT"
    assert set(modeling_evaluations(ranking_a)) == {"comap-mcm", "china-graduate-math-modeling"}
    for evaluation in modeling_evaluations(ranking_a).values():
        assert evaluation["suitability_score"] == 1.0
        assert any(c["component_id"] == "verified-skill-overlap-v1"
                   for c in evaluation["score_components"])
    set_level("unknown")
    current_ref = target.profile_repository.get(STUDENT).profile_ref
    assert current_ref != first_ref
    assert freshness(target, [identity_a])[0]["profile_freshness"]["status"] == "STALE"
    assert ranking_a == original
    identity_b, ranking_b = recommend()
    assert target.profile_input_bindings[identity_b].input_profile_ref == current_ref
    assert freshness(target, [identity_b])[0]["profile_freshness"]["status"] == "CURRENT"
    assert set(modeling_evaluations(ranking_b)) == {"comap-mcm", "china-graduate-math-modeling"}
    for evaluation in modeling_evaluations(ranking_b).values():
        assert evaluation["suitability_score"] is None
        assert not any(c["component_id"] == "verified-skill-overlap-v1"
                       for c in evaluation["score_components"])
    assert ranking_a == original  # No ranking-change requirement, and no mutation of A.


@pytest.mark.parametrize("explicit", [True, False])
def test_selected_plan_does_not_change_profile_discovery_or_candidate_add(explicit):
    from copy import deepcopy

    from competition_copilot.integrations.local_runtime.composition import (
        create_local_host,
    )

    target = create_local_host(ROOT)
    scope = {"student_id": STUDENT, "competition_id": "comap-mcm",
             "edition_id": "comap-mcm-2027"}

    def execute(intent, context, **extra):
        body = request("给我推荐几个比赛" if intent is None else intent, context)
        if intent is not None:
            body["request"]["intent"] = intent
        body["request"].update(extra)
        return invoke(target, body)

    generated = execute("BUILD_PLAN", scope)
    selected = generated["runtime"]["response"]["plan_refs"][0]
    original = deepcopy(selected)
    without = execute("GET_RECOMMENDATIONS", scope)
    context = {**scope, "plan_ref": selected}
    with_plan = execute("GET_RECOMMENDATIONS" if explicit else None, context)
    ranking = artifacts(with_plan, "RecommendationRankingResult")[0]
    assert ranking == artifacts(without, "RecommendationRankingResult")[0]
    candidates = [x["evaluation"]["candidate"] for bucket in ("confirmed", "uncertain", "blocked")
                  for x in ranking[bucket]]
    assert len(candidates) == 12
    other = next(c for c in candidates if c["competition_id"] == "huawei-ict")
    added = execute("ADD_MY_COMPETITION", {"student_id": STUDENT},
        my_competition_command={"operation": "add", "student_id": STUDENT,
            "target": other, "state": "SAVED"})
    relation = artifacts(added, "MyCompetitionMutationResult")[0]["snapshot"]["relationship"]
    assert relation["competition_id"] == other["competition_id"]
    assert relation["edition_id"] == other["edition_id"]
    assert relation["track_id"] == other.get("track_id")
    workspace = execute("GET_PLANNING_WORKSPACE", context)
    assert artifacts(workspace, "PlanningWorkspaceProjection")[0]["plan_ref"] == original
    assert context["plan_ref"] == original
    result_ref = next(a["ref"]["ref_id"] for a in with_plan["presentation"]["artifacts"]
                      if a["model"] == "RecommendationRankingResult")
    assert target.profile_input_bindings[result_ref].input_profile_ref == target.profile_repository.get(STUDENT).profile_ref


@pytest.mark.parametrize("mutation", ["digest", "version"])
def test_plan_bound_workspace_still_rejects_invalid_exact_reference(mutation):
    from copy import deepcopy

    from competition_copilot.integrations.local_runtime.composition import (
        create_local_host,
    )

    target = create_local_host(ROOT)
    context = {"student_id": STUDENT, "competition_id": "comap-mcm",
               "edition_id": "comap-mcm-2027"}
    body = request("BUILD_PLAN", context)
    body["request"]["intent"] = "BUILD_PLAN"
    selected = deepcopy(invoke(target, body)["runtime"]["response"]["plan_refs"][0])
    if mutation == "digest":
        selected["content_digest"] = "f" * 64
    else:
        selected["version"] += 1
    body = request("Read exact plan", {**context, "plan_ref": selected})
    body["request"]["intent"] = "GET_PLANNING_WORKSPACE"
    assert invoke(target, body)["runtime"]["response"]["outcome"] == "FAILED"
