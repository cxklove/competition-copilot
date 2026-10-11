"""Synthetic P6.1 recommendation contracts; no scoring or ranking engine."""

import json

import pytest
from pydantic import ValidationError

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.decision import DecisionResult, Evidence
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
    RecommendationReasonCode,
    RecommendationScoreComponent,
    RecommendationStatus,
)
from competition_copilot.domain.student import StudentProfile


def evidence() -> Evidence:
    return Evidence(
        code="student-goal",
        message="Student stated an interest in this subject.",
        field="interests",
        value="mathematics",
    )


def candidate(*, track_id: str | None = None) -> RecommendationCandidate:
    return RecommendationCandidate(
        competition_id="competition-1", edition_id="edition-1", track_id=track_id
    )


def eligibility(
    status: EligibilityStatus, *, track_id: str | None = None
) -> EligibilityDecision:
    reason = {
        EligibilityStatus.ELIGIBLE: EligibilityReasonCode.RULE_SATISFIED,
        EligibilityStatus.INELIGIBLE: EligibilityReasonCode.RULE_VIOLATED,
        EligibilityStatus.UNKNOWN: EligibilityReasonCode.PROFILE_DATA_MISSING,
    }[status]
    rule = RuleEvaluation(
        rule_id="official-rule-v1",
        scope=EligibilityScope.EDITION,
        target_id="edition-1",
        status=status,
        reason_code=reason,
        message="Synthetic hard rule outcome.",
        evidence=[Evidence(code="hard-rule", message="Synthetic rule evidence.")],
    )
    return EligibilityDecision(
        status=status,
        reason_codes=[reason.value],
        evidence=rule.evidence,
        competition_id="competition-1",
        edition_id="edition-1",
        track_id=track_id,
        rule_evaluations=[rule],
    )


def component(score: float = 0.8) -> RecommendationScoreComponent:
    return RecommendationScoreComponent(
        component_id="goal-fit",
        score=score,
        reason_code="GOAL_SIGNAL_PRESENT",
        message="Synthetic goal-fit signal.",
        evidence=[evidence()],
    )


def evaluation(
    eligibility_status: EligibilityStatus,
    recommendation_status: RecommendationStatus,
    reason: RecommendationReasonCode,
    *,
    score: float | None = None,
    components: list[RecommendationScoreComponent] | None = None,
) -> RecommendationEvaluation:
    return RecommendationEvaluation(
        status=recommendation_status,
        candidate=candidate(),
        eligibility_decision=eligibility(eligibility_status),
        suitability_score=score,
        score_components=components if components is not None else [],
        reason_codes=[reason.value],
        evidence=[evidence()],
    )


def test_context_accepts_matching_competition_edition_and_optional_track() -> None:
    profile = StudentProfile(id="student-1", interests=["mathematics"])
    competition = Competition(id="competition-1", name="Synthetic competition")
    edition = CompetitionEdition(
        id="edition-1", competition_id="competition-1", year=2026, name="2026"
    )
    track = CompetitionTrack(id="track-1", edition_id="edition-1", name="Track")
    context = RecommendationContext(
        student_profile=profile,
        candidate=candidate(track_id="track-1"),
        competition=competition,
        edition=edition,
        track=track,
        eligibility_decision=eligibility(EligibilityStatus.ELIGIBLE, track_id="track-1"),
    )
    assert context.candidate.track_id == "track-1"
    assert RecommendationContext.model_validate_json(context.model_dump_json()) == context

    base = context.model_dump()
    invalid_snapshots = [
        {"edition": edition.model_copy(update={"competition_id": "other"})},
        {"track": track.model_copy(update={"edition_id": "other"})},
        {"candidate": candidate(track_id=None)},
        {"eligibility_decision": eligibility(EligibilityStatus.ELIGIBLE)},
    ]
    for invalid in invalid_snapshots:
        with pytest.raises(ValidationError):
            RecommendationContext.model_validate({**base, **invalid})


def test_candidate_ids_are_required_strict_and_nonblank() -> None:
    for invalid in ("", "  ", 123):
        with pytest.raises(ValidationError):
            RecommendationCandidate(competition_id=invalid, edition_id="edition-1")
    with pytest.raises(ValidationError):
        RecommendationCandidate(competition_id="competition-1", edition_id=" ")


def test_eligible_allows_assessed_recommended_or_not_recommended() -> None:
    recommended = evaluation(
        EligibilityStatus.ELIGIBLE,
        RecommendationStatus.RECOMMENDED,
        RecommendationReasonCode.SUITABILITY_ASSESSED,
        score=0.8,
        components=[component()],
    )
    not_recommended = evaluation(
        EligibilityStatus.ELIGIBLE,
        RecommendationStatus.NOT_RECOMMENDED,
        RecommendationReasonCode.SUITABILITY_ASSESSED,
        score=0.2,
        components=[component(0.2)],
    )
    assert isinstance(recommended, DecisionResult)
    assert recommended.eligibility_decision.status is EligibilityStatus.ELIGIBLE
    assert recommended.status is RecommendationStatus.RECOMMENDED
    assert not_recommended.status is RecommendationStatus.NOT_RECOMMENDED
    assert recommended.score_components[0].evidence == (evidence(),)


def test_eligible_can_have_missing_soft_data_without_becoming_ineligible() -> None:
    result = evaluation(
        EligibilityStatus.ELIGIBLE,
        RecommendationStatus.SUITABILITY_UNDETERMINED,
        RecommendationReasonCode.SOFT_PROFILE_DATA_MISSING,
    )
    assert result.suitability_score is None
    assert result.eligibility_decision.status is EligibilityStatus.ELIGIBLE


def test_ineligible_can_only_be_blocked_without_soft_score() -> None:
    blocked = evaluation(
        EligibilityStatus.INELIGIBLE,
        RecommendationStatus.ELIGIBILITY_BLOCKED,
        RecommendationReasonCode.ELIGIBILITY_BLOCKED,
    )
    assert blocked.suitability_score is None
    assert blocked.eligibility_decision.status is EligibilityStatus.INELIGIBLE
    with pytest.raises(ValidationError):
        RecommendationEvaluation.model_validate(
            blocked.model_dump() | {
                "status": RecommendationStatus.RECOMMENDED,
                "suitability_score": 1.0,
                "score_components": [component()],
                "reason_codes": [RecommendationReasonCode.SUITABILITY_ASSESSED.value],
            }
        )
    with pytest.raises(ValidationError):
        RecommendationEvaluation.model_validate(
            blocked.model_dump() | {"suitability_score": 0.0}
        )


def test_unknown_eligibility_remains_explicit_even_with_high_soft_score() -> None:
    uncertain = evaluation(
        EligibilityStatus.UNKNOWN,
        RecommendationStatus.ELIGIBILITY_UNCERTAIN,
        RecommendationReasonCode.ELIGIBILITY_UNKNOWN,
        score=0.99,
        components=[component(0.99)],
    )
    assert uncertain.eligibility_decision.status is EligibilityStatus.UNKNOWN
    assert uncertain.status is RecommendationStatus.ELIGIBILITY_UNCERTAIN
    with pytest.raises(ValidationError):
        RecommendationEvaluation.model_validate(
            uncertain.model_dump() | {
                "status": RecommendationStatus.RECOMMENDED,
                "reason_codes": [RecommendationReasonCode.SUITABILITY_ASSESSED.value],
            }
        )


def test_evaluation_rejects_other_targets_and_conflicting_reasons() -> None:
    result = evaluation(
        EligibilityStatus.ELIGIBLE,
        RecommendationStatus.RECOMMENDED,
        RecommendationReasonCode.SUITABILITY_ASSESSED,
        score=0.8,
        components=[component()],
    )
    with pytest.raises(ValidationError):
        RecommendationEvaluation.model_validate(
            result.model_dump() | {"candidate": candidate(track_id="other")}
        )
    for reasons in (["ELIGIBILITY_BLOCKED"], ["SUITABILITY_ASSESSED", "ELIGIBILITY_UNKNOWN"], ["not machine readable"]):
        with pytest.raises(ValidationError):
            RecommendationEvaluation.model_validate(result.model_dump() | {"reason_codes": reasons})


@pytest.mark.parametrize("score", [-0.01, 1.01, float("nan"), float("inf"), -float("inf")])
def test_score_range_rejects_invalid_values(score: float) -> None:
    with pytest.raises(ValidationError):
        component(score)
    result = evaluation(
        EligibilityStatus.ELIGIBLE,
        RecommendationStatus.RECOMMENDED,
        RecommendationReasonCode.SUITABILITY_ASSESSED,
        score=0.8,
        components=[component()],
    )
    with pytest.raises(ValidationError):
        RecommendationEvaluation.model_validate(
            result.model_dump() | {"suitability_score": score}
        )


def test_assessed_result_needs_score_components_and_evidence() -> None:
    result = evaluation(
        EligibilityStatus.ELIGIBLE,
        RecommendationStatus.RECOMMENDED,
        RecommendationReasonCode.SUITABILITY_ASSESSED,
        score=0.8,
        components=[component()],
    )
    for invalid in (
        {"suitability_score": None},
        {"score_components": []},
        {"evidence": []},
    ):
        with pytest.raises(ValidationError):
            RecommendationEvaluation.model_validate(result.model_dump() | invalid)


@pytest.mark.parametrize(
    ("eligibility_status", "recommendation_status", "reason", "score"),
    [
        (EligibilityStatus.ELIGIBLE, RecommendationStatus.RECOMMENDED, RecommendationReasonCode.SUITABILITY_ASSESSED, 0.8),
        (EligibilityStatus.ELIGIBLE, RecommendationStatus.NOT_RECOMMENDED, RecommendationReasonCode.SUITABILITY_ASSESSED, 0.2),
        (EligibilityStatus.ELIGIBLE, RecommendationStatus.SUITABILITY_UNDETERMINED, RecommendationReasonCode.SOFT_PROFILE_DATA_MISSING, None),
        (EligibilityStatus.INELIGIBLE, RecommendationStatus.ELIGIBILITY_BLOCKED, RecommendationReasonCode.ELIGIBILITY_BLOCKED, None),
        (EligibilityStatus.UNKNOWN, RecommendationStatus.ELIGIBILITY_UNCERTAIN, RecommendationReasonCode.ELIGIBILITY_UNKNOWN, 0.8),
    ],
)
def test_json_round_trip_and_repeatability(
    eligibility_status: EligibilityStatus,
    recommendation_status: RecommendationStatus,
    reason: RecommendationReasonCode,
    score: float | None,
) -> None:
    kwargs = {
        "score": score,
        "components": [component(score)] if score is not None else [],
    }
    first = evaluation(eligibility_status, recommendation_status, reason, **kwargs)
    second = evaluation(eligibility_status, recommendation_status, reason, **kwargs)
    dumped = first.model_dump(mode="json")
    assert dumped == second.model_dump(mode="json")
    assert first.model_dump_json() == second.model_dump_json()
    assert json.loads(first.model_dump_json()) == dumped
    assert RecommendationEvaluation.model_validate_json(first.model_dump_json()) == first


@pytest.mark.parametrize("score", [0.0, 1.0])
def test_score_endpoints_are_valid_snapshots(score: float) -> None:
    result = evaluation(
        EligibilityStatus.ELIGIBLE,
        RecommendationStatus.RECOMMENDED,
        RecommendationReasonCode.SUITABILITY_ASSESSED,
        score=score,
        components=[component(score)],
    )
    assert result.suitability_score == score
    assert result.score_components[0].score == score
    assert RecommendationEvaluation.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize(
    ("hard_status", "soft_status", "reason", "score"),
    [
        (EligibilityStatus.INELIGIBLE, RecommendationStatus.ELIGIBILITY_BLOCKED,
         RecommendationReasonCode.ELIGIBILITY_BLOCKED, None),
        (EligibilityStatus.UNKNOWN, RecommendationStatus.ELIGIBILITY_UNCERTAIN,
         RecommendationReasonCode.ELIGIBILITY_UNKNOWN, 0.9),
        (EligibilityStatus.ELIGIBLE, RecommendationStatus.RECOMMENDED,
         RecommendationReasonCode.SUITABILITY_ASSESSED, 0.8),
    ],
)
def test_evaluation_assignment_cannot_break_a_validated_snapshot(
    hard_status, soft_status, reason, score
) -> None:
    result = evaluation(
        hard_status, soft_status, reason, score=score,
        components=[component(score)] if score is not None else [],
    )
    before = result.model_dump_json()
    attempts = {
        "status": RecommendationStatus.RECOMMENDED,
        "suitability_score": 1.0 if score is None else 2.0,
        "score_components": [component()],
        "eligibility_decision": eligibility(EligibilityStatus.INELIGIBLE),
        "candidate": candidate(track_id="other"),
    }
    for field, value in attempts.items():
        with pytest.raises(ValidationError, match="frozen"):
            setattr(result, field, value)
        assert result.model_dump_json() == before
    with pytest.raises(ValidationError, match="frozen"):
        result.eligibility_decision = eligibility(
            EligibilityStatus.ELIGIBLE, track_id="other"
        )


def test_owned_collections_and_component_cannot_be_mutated() -> None:
    pieces = [component()]
    reasons = [RecommendationReasonCode.SUITABILITY_ASSESSED.value]
    facts = [evidence()]
    result = RecommendationEvaluation(
        status=RecommendationStatus.RECOMMENDED,
        candidate=candidate(),
        eligibility_decision=eligibility(EligibilityStatus.ELIGIBLE),
        suitability_score=0.8,
        score_components=pieces,
        reason_codes=reasons,
        evidence=facts,
    )
    before = result.model_dump_json()
    pieces.clear()
    reasons.clear()
    facts.clear()
    for collection in (result.score_components, result.reason_codes, result.evidence):
        assert isinstance(collection, tuple)
        with pytest.raises(AttributeError):
            collection.append(None)
        with pytest.raises(TypeError):
            collection[0] = None
    with pytest.raises(ValidationError, match="frozen"):
        result.score_components[0].score = 2.0
    with pytest.raises(ValidationError, match="frozen"):
        result.candidate.edition_id = "other"
    assert result.model_dump_json() == before


def test_p5_decision_is_detached_and_frozen_without_changing_p5() -> None:
    original = eligibility(EligibilityStatus.ELIGIBLE)
    result = RecommendationEvaluation(
        status=RecommendationStatus.RECOMMENDED,
        candidate=candidate(),
        eligibility_decision=original,
        suitability_score=0.8,
        score_components=[component()],
        reason_codes=[RecommendationReasonCode.SUITABILITY_ASSESSED.value],
        evidence=[evidence()],
    )
    before = result.model_dump_json()
    # P5 remains mutable; only the P6-owned view must be isolated.
    original.status = EligibilityStatus.INELIGIBLE
    original.edition_id = "other"
    original.reason_codes.clear()
    original.rule_evaluations[0].status = EligibilityStatus.INELIGIBLE
    original.rule_evaluations.clear()
    assert result.eligibility_decision is not original
    assert result.eligibility_decision.status is EligibilityStatus.ELIGIBLE
    assert result.model_dump_json() == before
    with pytest.raises(ValidationError, match="frozen"):
        result.eligibility_decision.status = EligibilityStatus.INELIGIBLE
    with pytest.raises(ValidationError, match="frozen"):
        result.eligibility_decision.rule_evaluations[0].status = EligibilityStatus.INELIGIBLE
    for collection in (
        result.eligibility_decision.reason_codes,
        result.eligibility_decision.rule_evaluations,
        result.eligibility_decision.evidence,
        result.eligibility_decision.rule_evaluations[0].evidence,
    ):
        assert isinstance(collection, tuple)
        with pytest.raises(AttributeError):
            collection.clear()


def test_context_target_and_profile_snapshots_are_detached_and_frozen() -> None:
    competition = Competition(id="competition-1", name="Competition")
    edition = CompetitionEdition(
        id="edition-1", competition_id="competition-1", year=2026, name="Edition"
    )
    track = CompetitionTrack(id="track-1", edition_id="edition-1", name="Track")
    profile = StudentProfile(id="student-1", interests=["mathematics"])
    decision = eligibility(EligibilityStatus.ELIGIBLE, track_id="track-1")
    context = RecommendationContext(
        student_profile=profile,
        candidate=candidate(track_id="track-1"),
        competition=competition,
        edition=edition,
        track=track,
        eligibility_decision=decision,
    )
    before = context.model_dump_json()
    competition.id = "other"
    edition.competition_id = "other"
    track.edition_id = "other"
    profile.interests.append("other")
    decision.status = EligibilityStatus.INELIGIBLE
    assert context.model_dump_json() == before
    attempts = [
        (context, "edition", edition),
        (context, "track", track),
        (context, "eligibility_decision", decision),
        (context.edition, "competition_id", "other"),
        (context.track, "edition_id", "other"),
        (context.competition, "id", "other"),
        (context.candidate, "track_id", "other"),
        (context.student_profile, "id", "other"),
    ]
    for model, field, value in attempts:
        with pytest.raises(ValidationError, match="frozen"):
            setattr(model, field, value)
    assert isinstance(context.student_profile.interests, tuple)
    assert context.model_dump_json() == before


def test_shared_p5_invariants_are_reused_when_snapshotting_invalid_input() -> None:
    invalid = eligibility(EligibilityStatus.ELIGIBLE)
    invalid.status = EligibilityStatus.INELIGIBLE
    with pytest.raises(ValidationError, match="violated rule"):
        RecommendationEvaluation(
            status=RecommendationStatus.ELIGIBILITY_BLOCKED,
            candidate=candidate(),
            eligibility_decision=invalid,
            reason_codes=[RecommendationReasonCode.ELIGIBILITY_BLOCKED.value],
            evidence=[evidence()],
        )


def test_unvalidated_copy_updates_are_rejected() -> None:
    result = evaluation(
        EligibilityStatus.INELIGIBLE,
        RecommendationStatus.ELIGIBILITY_BLOCKED,
        RecommendationReasonCode.ELIGIBILITY_BLOCKED,
    )
    with pytest.raises(TypeError, match="new validated snapshot"):
        result.model_copy(update={"status": RecommendationStatus.RECOMMENDED})
    with pytest.raises(TypeError, match="new validated snapshot"):
        component().model_copy(update={"score": 2.0})
    assert result.model_copy() == result
