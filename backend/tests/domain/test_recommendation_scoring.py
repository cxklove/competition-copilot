"""P6.2 uses synthetic components, never inferred competition skill tags."""

import ast
import inspect
import json
from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from competition_copilot.domain import recommendation_scoring
from competition_copilot.domain.competition import Competition, CompetitionEdition
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
    RecommendationContext,
    RecommendationEvaluation,
    RecommendationScoreComponent,
    RecommendationStatus,
)
from competition_copilot.domain.recommendation_scoring import (
    RecommendationScoringEngine,
    RecommendationScoringError,
    WeightedSuitabilityScorer,
)
from competition_copilot.domain.student import StudentProfile


def context(status=EligibilityStatus.ELIGIBLE):
    reason = {
        EligibilityStatus.ELIGIBLE: EligibilityReasonCode.RULE_SATISFIED,
        EligibilityStatus.INELIGIBLE: EligibilityReasonCode.RULE_VIOLATED,
        EligibilityStatus.UNKNOWN: EligibilityReasonCode.PROFILE_DATA_MISSING,
    }[status]
    evidence = Evidence(code="SYNTHETIC_RULE", message="Synthetic hard-rule audit.")
    return RecommendationContext(
        student_profile=StudentProfile(id="s", interests=["math"]),
        candidate=RecommendationCandidate(competition_id="c", edition_id="e"),
        competition=Competition(id="c", name="Synthetic"),
        edition=CompetitionEdition(id="e", competition_id="c", year=2026, name="2026"),
        eligibility_decision=EligibilityDecision(
            status=status,
            competition_id="c",
            edition_id="e",
            reason_codes=[reason.value],
            evidence=[evidence],
            rule_evaluations=[
                RuleEvaluation(
                    rule_id="synthetic",
                    scope=EligibilityScope.EDITION,
                    target_id="e",
                    status=status,
                    reason_code=reason,
                    message="Synthetic outcome.",
                    evidence=[evidence],
                )
            ],
        ),
    )


@dataclass
class FakeScorer:
    component_id: str
    value: float | None
    calls: list[str]
    returned_id: str | None = None
    failure: Exception | None = None

    def evaluate(self, context):
        self.calls.append(self.component_id)
        if self.failure is not None:
            raise self.failure
        if self.value is None:
            return None
        return RecommendationScoreComponent(
            component_id=self.returned_id or self.component_id,
            score=self.value,
            reason_code="SYNTHETIC_SIGNAL_AVAILABLE",
            message="Synthetic soft score.",
            evidence=[
                Evidence(
                    code="PROFILE_INTEREST",
                    message="Actual synthetic profile fact.",
                    field="interests",
                    value=context.student_profile.interests[0],
                )
            ],
        )


def engine(values, weights=None, **kwargs):
    calls = []
    scorers = [
        FakeScorer(f"component-{i}", value, calls) for i, value in enumerate(values)
    ]
    weights = weights if weights is not None else [1.0] * len(values)
    return RecommendationScoringEngine(
        [
            WeightedSuitabilityScorer(scorer, weight)
            for scorer, weight in zip(scorers, weights, strict=True)
        ],
        **kwargs,
    ), calls


def test_ineligible_gate_never_executes_scorers():
    scorer = FakeScorer("a", 1.0, [], failure=RuntimeError("must not run"))
    result = RecommendationScoringEngine([WeightedSuitabilityScorer(scorer)]).evaluate(
        context(EligibilityStatus.INELIGIBLE)
    )
    assert result.status is RecommendationStatus.ELIGIBILITY_BLOCKED
    assert result.suitability_score is None and result.score_components == ()
    assert scorer.calls == []


@pytest.mark.parametrize("values, expected", [([0.99], 0.99), ([None], None)])
def test_unknown_eligibility_retained_with_or_without_score(values, expected):
    service, calls = engine(values)
    result = service.evaluate(context(EligibilityStatus.UNKNOWN))
    assert result.status is RecommendationStatus.ELIGIBILITY_UNCERTAIN
    assert result.eligibility_decision.status is EligibilityStatus.UNKNOWN
    assert result.suitability_score == expected
    assert calls == ["component-0"]


def test_weighted_average_full_ordered_audit_and_no_short_circuit():
    service, calls = engine([0.8, 0.4], [0.75, 0.25])
    result = service.evaluate(context())
    assert result.suitability_score == pytest.approx(0.7)
    assert calls == ["component-0", "component-1"]
    assert [c.component_id for c in result.score_components] == calls
    assert [c.score for c in result.score_components] == [0.8, 0.4]
    assert all(c.evidence[0].field == "interests" for c in result.score_components)
    assert all(c.evidence[0].value == "math" for c in result.score_components)
    assert [e.value for e in result.evidence if e.code == "COMPONENT_WEIGHT"] == [
        0.75,
        0.25,
    ]
    low_service, low_calls = engine([0.0, 1.0])
    assert len(low_service.evaluate(context()).score_components) == 2
    assert low_calls == ["component-0", "component-1"]


def test_missing_signal_excluded_and_audited_not_zero():
    service, calls = engine([0.8, None], [0.5, 0.5])
    result = service.evaluate(context())
    assert result.suitability_score == pytest.approx(0.8)
    assert len(result.score_components) == 1
    assert calls == ["component-0", "component-1"]
    assert "SOFT_SIGNAL_UNAVAILABLE" in result.reason_codes
    assert any(
        e.code == "SOFT_SIGNAL_UNAVAILABLE" and e.value == "component-1"
        for e in result.evidence
    )


def test_all_missing_is_undetermined_not_low_suitability():
    service, calls = engine([None, None])
    result = service.evaluate(context())
    assert result.status is RecommendationStatus.SUITABILITY_UNDETERMINED
    assert result.suitability_score is None and not result.score_components
    assert "SOFT_PROFILE_DATA_MISSING" in result.reason_codes
    assert calls == ["component-0", "component-1"]
    assert result.eligibility_decision.status is EligibilityStatus.ELIGIBLE


def test_zero_weight_components_audited_but_not_aggregated():
    service, _ = engine([0.0, 0.8], [0.0, 1.0])
    result = service.evaluate(context())
    assert result.suitability_score == 0.8
    assert len(result.score_components) == 2
    service, _ = engine([0.9, None], [0.0, 1.0])
    assert (
        service.evaluate(context()).status
        is RecommendationStatus.SUITABILITY_UNDETERMINED
    )


@pytest.mark.parametrize(
    "weight", [-1.0, float("nan"), float("inf"), -float("inf"), True]
)
def test_invalid_weights_rejected(weight):
    with pytest.raises(RecommendationScoringError):
        engine([0.8], [weight])


def test_empty_or_all_zero_weights_rejected():
    for values, weights in [([], []), ([0.8, 0.4], [0.0, 0.0])]:
        with pytest.raises(RecommendationScoringError):
            engine(values, weights)


@pytest.mark.parametrize(
    "score, status",
    [
        (0.0, RecommendationStatus.NOT_RECOMMENDED),
        (0.49, RecommendationStatus.NOT_RECOMMENDED),
        (0.5, RecommendationStatus.RECOMMENDED),
        (0.51, RecommendationStatus.RECOMMENDED),
        (1.0, RecommendationStatus.RECOMMENDED),
    ],
)
def test_score_endpoints_and_threshold(score, status):
    service, _ = engine([score])
    result = service.evaluate(context())
    assert result.status is status
    assert result.suitability_score == score


@pytest.mark.parametrize(
    "score", [-0.01, 1.01, float("nan"), float("inf"), -float("inf")]
)
def test_invalid_scorer_scores_are_errors_not_missing(score):
    service, _ = engine([score])
    with pytest.raises(RecommendationScoringError) as error:
        service.evaluate(context())
    assert isinstance(error.value.__cause__, ValidationError)


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan"), float("inf")])
def test_invalid_thresholds(threshold):
    with pytest.raises(RecommendationScoringError):
        engine([0.8], threshold=threshold)


def test_large_finite_weights_do_not_overflow_and_custom_threshold():
    service, _ = engine([0.8, 0.4], [1e308, 1e308], threshold=0.7)
    result = service.evaluate(context())
    assert result.suitability_score == pytest.approx(0.6)
    assert result.status is RecommendationStatus.NOT_RECOMMENDED


def test_duplicate_ids_rejected_before_execution():
    calls = []
    with pytest.raises(RecommendationScoringError, match="duplicate"):
        RecommendationScoringEngine(
            [
                WeightedSuitabilityScorer(FakeScorer("same", 0.8, calls)),
                WeightedSuitabilityScorer(FakeScorer("same", 0.4, calls)),
            ]
        )
    assert calls == []


def test_mismatch_identity_change_and_exception_fail_whole_evaluation():
    scorer = FakeScorer("a", 0.8, [], returned_id="b")
    service = RecommendationScoringEngine([WeightedSuitabilityScorer(scorer)])
    with pytest.raises(RecommendationScoringError):
        service.evaluate(context())
    scorer.component_id = "changed"
    with pytest.raises(RecommendationScoringError):
        service.evaluate(context())
    calls = []
    service = RecommendationScoringEngine(
        [
            WeightedSuitabilityScorer(FakeScorer("a", 0.8, calls)),
            WeightedSuitabilityScorer(
                FakeScorer("b", 0.4, calls, failure=RuntimeError("bug"))
            ),
        ]
    )
    with pytest.raises(RecommendationScoringError) as error:
        service.evaluate(context())
    assert isinstance(error.value.__cause__, RuntimeError)
    assert calls == ["a", "b"]


def test_wrong_result_type_rejected():
    class BadScorer:
        component_id = "a"

        def evaluate(self, context):
            return 0.8

    with pytest.raises(RecommendationScoringError):
        RecommendationScoringEngine([WeightedSuitabilityScorer(BadScorer())]).evaluate(
            context()
        )


@pytest.mark.parametrize(
    "eligibility, value",
    [
        (EligibilityStatus.INELIGIBLE, 0.8),
        (EligibilityStatus.UNKNOWN, 0.99),
        (EligibilityStatus.UNKNOWN, None),
        (EligibilityStatus.ELIGIBLE, 0.8),
        (EligibilityStatus.ELIGIBLE, 0.2),
        (EligibilityStatus.ELIGIBLE, None),
    ],
)
def test_determinism_serialization_readonly_and_mutation_safety(eligibility, value):
    service, _ = engine([value])
    prepared = context(eligibility)
    before = prepared.model_dump_json()
    first, second = service.evaluate(prepared), service.evaluate(prepared)
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert first.model_dump(mode="json") == json.loads(first.model_dump_json())
    assert (
        RecommendationEvaluation.model_validate_json(first.model_dump_json()) == first
    )
    assert prepared.model_dump_json() == before
    with pytest.raises(ValidationError):
        first.suitability_score = 2.0
    with pytest.raises(ValidationError):
        first.status = RecommendationStatus.RECOMMENDED
    with pytest.raises(ValidationError):
        first.eligibility_decision.status = EligibilityStatus.INELIGIBLE
    assert isinstance(first.score_components, tuple)
    if first.score_components:
        with pytest.raises(ValidationError):
            first.score_components[0].score = 2.0


def test_engine_dependency_boundary_and_no_validation_bypass():
    tree = ast.parse(inspect.getsource(recommendation_scoring))
    imports = [
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    assert all(
        not any(
            part in name
            for part in ("repositories", "infrastructure", "tools", "ingestion")
        )
        for name in imports
        if name
    )
    assert {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } == {"math", "re"}
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "model_construct"
        for node in ast.walk(tree)
    )
