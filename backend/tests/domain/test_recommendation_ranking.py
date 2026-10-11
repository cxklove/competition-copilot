"""Synthetic P6.3 acceptance tests; no scoring or target discovery."""

import ast
import inspect
import json
from itertools import permutations

import pytest
from pydantic import ValidationError

from competition_copilot.domain import recommendation_ranking
from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.eligibility import (
    EligibilityDecision,
    EligibilityReasonCode,
    EligibilityScope,
    EligibilityStatus,
    RuleEvaluation,
)
from competition_copilot.domain.recommendation import (
    RecommendationCandidate,
    RecommendationEvaluation,
    RecommendationReasonCode,
    RecommendationScoreComponent,
    RecommendationStatus,
)
from competition_copilot.domain.recommendation_ranking import (
    RankedRecommendation,
    RecommendationRankingEngine,
    RecommendationRankingError,
    RecommendationRankingResult,
)


def evaluation(
    competition_id="c",
    score=0.8,
    *,
    edition_id="e",
    track_id=None,
    eligibility=EligibilityStatus.ELIGIBLE,
    status=None,
):
    hard_reason = {
        EligibilityStatus.ELIGIBLE: EligibilityReasonCode.RULE_SATISFIED,
        EligibilityStatus.UNKNOWN: EligibilityReasonCode.PROFILE_DATA_MISSING,
        EligibilityStatus.INELIGIBLE: EligibilityReasonCode.RULE_VIOLATED,
    }[eligibility]
    if eligibility is EligibilityStatus.INELIGIBLE:
        status = status or RecommendationStatus.ELIGIBILITY_BLOCKED
        reason = RecommendationReasonCode.ELIGIBILITY_BLOCKED
    elif eligibility is EligibilityStatus.UNKNOWN:
        status = status or RecommendationStatus.ELIGIBILITY_UNCERTAIN
        reason = RecommendationReasonCode.ELIGIBILITY_UNKNOWN
    elif score is None:
        status = status or RecommendationStatus.SUITABILITY_UNDETERMINED
        reason = RecommendationReasonCode.SOFT_PROFILE_DATA_MISSING
    else:
        status = status or (
            RecommendationStatus.RECOMMENDED
            if score >= 0.5
            else RecommendationStatus.NOT_RECOMMENDED
        )
        reason = RecommendationReasonCode.SUITABILITY_ASSESSED
    evidence = Evidence(code="SYNTHETIC_FACT", message="Synthetic prepared evidence.")
    return RecommendationEvaluation(
        candidate=RecommendationCandidate(
            competition_id=competition_id,
            edition_id=edition_id,
            track_id=track_id,
        ),
        eligibility_decision=EligibilityDecision(
            competition_id=competition_id,
            edition_id=edition_id,
            track_id=track_id,
            status=eligibility,
            reason_codes=[hard_reason.value],
            evidence=[evidence],
            rule_evaluations=[
                RuleEvaluation(
                    rule_id="synthetic",
                    scope=EligibilityScope.EDITION,
                    target_id=edition_id,
                    status=eligibility,
                    reason_code=hard_reason,
                    message="Prepared synthetic hard result.",
                    evidence=[evidence],
                )
            ],
        ),
        status=status,
        suitability_score=score,
        reason_codes=[reason.value],
        evidence=[evidence],
        score_components=[]
        if score is None
        else [
            RecommendationScoreComponent(
                component_id="synthetic",
                score=score,
                reason_code="SYNTHETIC_SIGNAL",
                message="Prepared score, not computed by ranking.",
                evidence=[evidence],
            )
        ],
    )


def ids(entries):
    return [entry.evaluation.candidate.competition_id for entry in entries]


def test_eligible_scores_descend_and_ranks_are_continuous():
    result = RecommendationRankingEngine().rank(
        [
            evaluation("b", 0.7),
            evaluation("c", 0.5),
            evaluation("a", 0.9),
        ]
    )
    assert ids(result.confirmed) == ["a", "b", "c"]
    assert [entry.rank for entry in result.confirmed] == [1, 2, 3]
    assert not result.uncertain and not result.blocked


def test_not_recommended_and_undetermined_remain_confirmed_and_none_is_not_zero():
    values = [
        evaluation("a", None),
        evaluation("b", 0.0),
        evaluation("c", 0.3),
        evaluation("d", 0.8),
    ]
    result = RecommendationRankingEngine().rank(values)
    assert ids(result.confirmed) == ["d", "c", "b", "a"]
    assert result.confirmed[-1].evaluation.suitability_score is None
    assert result.confirmed[1].evaluation.status is RecommendationStatus.NOT_RECOMMENDED


def test_unknown_high_score_cannot_promote_and_unknown_no_score_stays_uncertain():
    result = RecommendationRankingEngine().rank(
        [
            evaluation("eligible", 0.1),
            evaluation("unknown-high", 1.0, eligibility=EligibilityStatus.UNKNOWN),
            evaluation("unknown-low", 0.5, eligibility=EligibilityStatus.UNKNOWN),
            evaluation("unknown-none", None, eligibility=EligibilityStatus.UNKNOWN),
        ]
    )
    assert ids(result.confirmed) == ["eligible"]
    assert ids(result.uncertain) == ["unknown-high", "unknown-low", "unknown-none"]
    assert [entry.rank for entry in result.uncertain] == [1, 2, 3]
    assert all(
        entry.evaluation.status is RecommendationStatus.ELIGIBILITY_UNCERTAIN
        for entry in result.uncertain
    )


def test_blocked_has_only_target_order_and_no_rank():
    values = [
        evaluation(name, None, eligibility=EligibilityStatus.INELIGIBLE)
        for name in ("b", "a")
    ]
    result = RecommendationRankingEngine().rank(values)
    assert not result.confirmed and not result.uncertain
    assert [entry.candidate.competition_id for entry in result.blocked] == ["a", "b"]
    assert all(not hasattr(entry, "rank") for entry in result.blocked)
    with pytest.raises(ValidationError):
        RankedRecommendation(rank=1, evaluation=values[0])


def test_all_unknown_and_empty_are_valid():
    result = RecommendationRankingEngine().rank(
        [
            evaluation("b", None, eligibility=EligibilityStatus.UNKNOWN),
            evaluation("a", 0.9, eligibility=EligibilityStatus.UNKNOWN),
        ]
    )
    assert not result.confirmed and not result.blocked
    assert ids(result.uncertain) == ["a", "b"]
    empty = RecommendationRankingEngine().rank([])
    assert empty.confirmed == empty.uncertain == empty.blocked == ()
    assert (
        RecommendationRankingResult.model_validate_json(empty.model_dump_json())
        == empty
    )


@pytest.mark.parametrize(
    "eligibility", [EligibilityStatus.ELIGIBLE, EligibilityStatus.UNKNOWN]
)
@pytest.mark.parametrize("score", [0.8, None])
def test_ties_use_full_target_identity_independent_of_input(eligibility, score):
    targets = [
        ("b", "a", None),
        ("a", "b", None),
        ("a", "a", "b"),
        ("a", "a", None),
        ("a", "a", "a"),
    ]
    values = [
        evaluation(c, score, edition_id=e, track_id=t, eligibility=eligibility)
        for c, e, t in targets
    ]
    service = RecommendationRankingEngine()
    result = service.rank(values)
    entries = (
        result.confirmed
        if eligibility is EligibilityStatus.ELIGIBLE
        else result.uncertain
    )
    assert [
        (
            r.evaluation.candidate.competition_id,
            r.evaluation.candidate.edition_id,
            r.evaluation.candidate.track_id,
        )
        for r in entries
    ] == [
        ("a", "a", None),
        ("a", "a", "a"),
        ("a", "a", "b"),
        ("a", "b", None),
        ("b", "a", None),
    ]
    assert service.rank(values[::-1]).model_dump_json() == result.model_dump_json()


def test_close_scores_are_not_rounded_and_status_is_not_recomputed():
    values = [
        evaluation("a", 0.5000000000000001),
        evaluation("b", 0.5000000000000002),
        evaluation("custom-threshold", 0.1, status=RecommendationStatus.RECOMMENDED),
    ]
    result = RecommendationRankingEngine().rank(values)
    assert ids(result.confirmed) == ["b", "a", "custom-threshold"]
    assert result.confirmed[-1].evaluation == values[-1]


def test_mixed_set_all_permutations_same_json_and_inputs_preserved():
    values = [
        evaluation("e-b", 0.7),
        evaluation("e-a", 0.9),
        evaluation("u-b", None, eligibility=EligibilityStatus.UNKNOWN),
        evaluation("u-a", 1.0, eligibility=EligibilityStatus.UNKNOWN),
        evaluation("i-b", None, eligibility=EligibilityStatus.INELIGIBLE),
        evaluation("i-a", None, eligibility=EligibilityStatus.INELIGIBLE),
    ]
    before = [value.model_dump_json() for value in values]
    service = RecommendationRankingEngine()
    expected = service.rank(values)
    assert ids(expected.confirmed) == ["e-a", "e-b"]
    assert ids(expected.uncertain) == ["u-a", "u-b"]
    assert [v.candidate.competition_id for v in expected.blocked] == ["i-a", "i-b"]
    assert [v.rank for v in expected.confirmed] == [1, 2]
    assert [v.rank for v in expected.uncertain] == [1, 2]
    for ordering in permutations(values):
        assert service.rank(ordering).model_dump_json() == expected.model_dump_json()
    assert [value.model_dump_json() for value in values] == before
    assert expected.model_dump(mode="json") == json.loads(expected.model_dump_json())
    assert (
        RecommendationRankingResult.model_validate_json(expected.model_dump_json())
        == expected
    )


def test_duplicate_targets_rejected_before_sorting(monkeypatch):
    def forbidden_sort(*args, **kwargs):
        pytest.fail("duplicate detection must precede sorting")

    monkeypatch.setattr(recommendation_ranking, "sorted", forbidden_sort, raising=False)
    with pytest.raises(RecommendationRankingError, match="duplicate"):
        RecommendationRankingEngine().rank([evaluation("a", 0.8), evaluation("a", 0.9)])


def test_invalid_input_is_error_not_partial_result():
    with pytest.raises(RecommendationRankingError):
        RecommendationRankingEngine().rank([evaluation(), None])


def test_result_contract_rejects_wrong_rank_bucket_order_and_duplicates():
    service = RecommendationRankingEngine()
    data = service.rank([evaluation("a", 0.9), evaluation("b", 0.7)]).model_dump()
    wrong_rank = {
        **data,
        "confirmed": [{**data["confirmed"][0], "rank": 3}, data["confirmed"][1]],
    }
    wrong_order = {
        **data,
        "confirmed": [
            {**data["confirmed"][1], "rank": 1},
            {**data["confirmed"][0], "rank": 2},
        ],
    }
    for invalid in (
        wrong_rank,
        wrong_order,
        {**data, "uncertain": data["confirmed"]},
        {**data, "blocked": [evaluation().model_dump()]},
        {
            **data,
            "confirmed": [data["confirmed"][0], {**data["confirmed"][0], "rank": 2}],
        },
        {**data, "ranking_policy": "other"},
    ):
        with pytest.raises(ValidationError):
            RecommendationRankingResult.model_validate(invalid)
    blocked = service.rank(
        [
            evaluation("b", None, eligibility=EligibilityStatus.INELIGIBLE),
            evaluation("a", None, eligibility=EligibilityStatus.INELIGIBLE),
        ]
    )
    with pytest.raises(ValidationError):
        RecommendationRankingResult(blocked=blocked.blocked[::-1])
    for rank in (0, -1, True, 1.5):
        with pytest.raises(ValidationError):
            RankedRecommendation(rank=rank, evaluation=evaluation())


def test_result_and_nested_entries_are_immutable_detached_snapshots():
    values = [
        evaluation("e"),
        evaluation("u", None, eligibility=EligibilityStatus.UNKNOWN),
        evaluation("i", None, eligibility=EligibilityStatus.INELIGIBLE),
    ]
    result = RecommendationRankingEngine().rank(values)
    before = result.model_dump_json()
    for collection in (result.confirmed, result.uncertain, result.blocked):
        with pytest.raises(AttributeError):
            collection.append(None)
        with pytest.raises(TypeError):
            collection[0] = None
    for model, field, value in (
        (result, "confirmed", ()),
        (result.confirmed[0], "rank", 999),
        (result.confirmed[0], "evaluation", values[1]),
        (result.confirmed[0].evaluation, "suitability_score", 2.0),
        (result.confirmed[0].evaluation.candidate, "competition_id", "other"),
        (result.blocked[0].eligibility_decision, "status", EligibilityStatus.ELIGIBLE),
    ):
        with pytest.raises(ValidationError, match="frozen"):
            setattr(model, field, value)
    with pytest.raises(TypeError):
        result.model_copy(update={"confirmed": ()})
    # Shared Evidence is mutable in P6.1; composition must still detach input audit.
    values[0].evidence[0].message = "External change"
    values.clear()
    assert result.model_dump_json() == before


def test_no_discovery_scoring_or_infrastructure_dependency():
    tree = ast.parse(inspect.getsource(recommendation_ranking))
    imports = [
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    assert all(
        not any(
            part in name
            for part in (
                "scoring",
                "eligibility_engine",
                "repositories",
                "infrastructure",
                "tools",
                "ingestion",
            )
        )
        for name in imports
        if name
    )
    assert not any(isinstance(node, ast.Import) for node in ast.walk(tree))
    assert not any(
        isinstance(node, ast.Attribute)
        and node.attr
        in (
            "model_construct",
            "evaluate",
            "__setattr__",
        )
        for node in ast.walk(tree)
    )
