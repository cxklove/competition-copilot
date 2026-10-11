"""Eligibility-separated ranking of already evaluated candidates, without rescoring."""

from collections.abc import Sequence
from typing import Literal

from pydantic import Field, model_validator

from competition_copilot.domain.eligibility import EligibilityStatus
from competition_copilot.domain.recommendation import (
    RecommendationEvaluation,
    _RecommendationSnapshot,
)


def _target_key(evaluation: RecommendationEvaluation) -> tuple[str, str, str]:
    candidate = evaluation.candidate
    return candidate.competition_id, candidate.edition_id, candidate.track_id or ""


def _score_key(evaluation: RecommendationEvaluation) -> tuple:
    score = evaluation.suitability_score
    # The leading flag distinguishes known zero suitability from unavailable data.
    return score is None, -score if score is not None else 0.0, _target_key(evaluation)


class RecommendationRankingError(ValueError):
    """Invalid ranking input or duplicate target; no partial result is returned."""


class RankedRecommendation(_RecommendationSnapshot):
    """Bucket-local position composed with the original evaluation snapshot."""

    rank: int = Field(strict=True, ge=1)
    evaluation: RecommendationEvaluation

    @model_validator(mode="after")
    def reject_blocked_rank(self) -> "RankedRecommendation":
        if self.evaluation.eligibility_decision.status is EligibilityStatus.INELIGIBLE:
            raise ValueError("blocked candidate has no recommendation rank")
        return self


class RecommendationRankingResult(_RecommendationSnapshot):
    """Full immutable rankings with no shared global rank space.

    Numeric scores descend within each ranked bucket, followed by unavailable
    scores. Exact score ties use ascending target IDs, with None track as "".
    Blocked candidates have only target-ID reporting order. Empty input is valid.
    """

    ranking_policy: Literal["eligibility_buckets_score_desc_target_id_v1"] = (
        "eligibility_buckets_score_desc_target_id_v1"
    )
    confirmed: tuple[RankedRecommendation, ...] = ()
    uncertain: tuple[RankedRecommendation, ...] = ()
    blocked: tuple[RecommendationEvaluation, ...] = ()

    @model_validator(mode="after")
    def check_ranking(self) -> "RecommendationRankingResult":
        seen = set()
        for entries, eligibility in (
            (self.confirmed, EligibilityStatus.ELIGIBLE),
            (self.uncertain, EligibilityStatus.UNKNOWN),
        ):
            evaluations = []
            for position, entry in enumerate(entries, start=1):
                if entry.rank != position:
                    raise ValueError("rank must match continuous bucket position")
                if entry.evaluation.eligibility_decision.status is not eligibility:
                    raise ValueError(
                        "evaluation belongs to a different eligibility bucket"
                    )
                evaluations.append(entry.evaluation)
            if evaluations != sorted(evaluations, key=_score_key):
                raise ValueError("bucket must follow score and target-ID order")
            for evaluation in evaluations:
                key = _target_key(evaluation)
                if key in seen:
                    raise ValueError("duplicate candidate target")
                seen.add(key)
        if list(self.blocked) != sorted(self.blocked, key=_target_key):
            raise ValueError("blocked candidates must follow target-ID order")
        for evaluation in self.blocked:
            if (
                evaluation.eligibility_decision.status
                is not EligibilityStatus.INELIGIBLE
            ):
                raise ValueError("blocked bucket requires ineligible evaluation")
            key = _target_key(evaluation)
            if key in seen:
                raise ValueError("duplicate candidate target")
            seen.add(key)
        return self


class RecommendationRankingEngine:
    """Rank prepared evaluations without target discovery or business recomputation."""

    def rank(
        self, evaluations: Sequence[RecommendationEvaluation]
    ) -> RecommendationRankingResult:
        buckets: dict[EligibilityStatus, list[RecommendationEvaluation]] = {
            status: [] for status in EligibilityStatus
        }
        seen = set()
        # Validate all inputs and duplicates before sorting or producing entries.
        for evaluation in evaluations:
            if not isinstance(evaluation, RecommendationEvaluation):
                raise RecommendationRankingError("expected RecommendationEvaluation")
            try:
                snapshot = RecommendationEvaluation.model_validate(
                    evaluation.model_dump()
                )
            except Exception as exc:
                raise RecommendationRankingError(
                    "invalid recommendation evaluation"
                ) from exc
            key = _target_key(snapshot)
            if key in seen:
                raise RecommendationRankingError(f"duplicate candidate target: {key}")
            seen.add(key)
            buckets[snapshot.eligibility_decision.status].append(snapshot)

        def ranked(status: EligibilityStatus) -> tuple[RankedRecommendation, ...]:
            return tuple(
                RankedRecommendation(rank=position, evaluation=evaluation)
                for position, evaluation in enumerate(
                    sorted(buckets[status], key=_score_key), start=1
                )
            )

        return RecommendationRankingResult(
            confirmed=ranked(EligibilityStatus.ELIGIBLE),
            uncertain=ranked(EligibilityStatus.UNKNOWN),
            blocked=tuple(
                sorted(buckets[EligibilityStatus.INELIGIBLE], key=_target_key)
            ),
        )
