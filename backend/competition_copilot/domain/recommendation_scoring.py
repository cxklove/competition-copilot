"""Deterministic single-candidate scoring of prepared soft components.

There is no real competition skill mapping yet. Callers supply pure scorers;
missing signals are explicit None results, never implicit zero scores.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.eligibility import EligibilityStatus
from competition_copilot.domain.recommendation import (
    RecommendationContext,
    RecommendationEvaluation,
    RecommendationReasonCode,
    RecommendationScoreComponent,
    RecommendationStatus,
)

DEFAULT_RECOMMENDATION_THRESHOLD = 0.5
SCORING_VERSION = "weighted-average-v1"


class RecommendationScoringError(ValueError):
    """Invalid configuration or scorer failure, distinct from missing data."""


class SuitabilityScorer(Protocol):
    """Pure scorer with stable identity; None means its signal is unavailable.

    Implementations use only prepared Domain facts, do not mutate context, and
    must not use IO, clocks, random values, or hard eligibility rule logic.
    """

    @property
    def component_id(self) -> str: ...

    def evaluate(
        self, context: RecommendationContext
    ) -> RecommendationScoreComponent | None: ...


@dataclass(frozen=True)
class WeightedSuitabilityScorer:
    scorer: SuitabilityScorer
    weight: float = 1.0


class RecommendationScoringEngine:
    """Ordered full audit, active-weight average, and an explicit eligibility gate.

    Threshold 0.5 is a deterministic MVP heuristic, not a learned parameter.
    Zero-weight components are audited but do not contribute to the average.
    """

    def __init__(
        self,
        scorers: Sequence[WeightedSuitabilityScorer],
        *,
        threshold: float = DEFAULT_RECOMMENDATION_THRESHOLD,
    ) -> None:
        if type(threshold) not in (int, float) or not math.isfinite(threshold):
            raise RecommendationScoringError("threshold must be finite")
        if not 0 <= threshold <= 1:
            raise RecommendationScoringError("threshold must be in [0, 1]")
        prepared = []
        seen = set()
        for item in scorers:
            try:
                component_id = item.scorer.component_id
                weight = item.weight
            except Exception as exc:
                raise RecommendationScoringError(
                    "cannot read scorer configuration"
                ) from exc
            if not isinstance(component_id, str) or not re.fullmatch(
                r"[a-z][a-z0-9_.-]*", component_id
            ):
                raise RecommendationScoringError("invalid component_id")
            if component_id in seen:
                raise RecommendationScoringError(
                    f"duplicate component_id: {component_id}"
                )
            if (
                type(weight) not in (int, float)
                or not math.isfinite(weight)
                or weight < 0
            ):
                raise RecommendationScoringError(
                    "weight must be finite and nonnegative"
                )
            seen.add(component_id)
            prepared.append((item.scorer, component_id, float(weight)))
        if not any(weight > 0 for _, _, weight in prepared):
            raise RecommendationScoringError("at least one weight must be positive")
        self._scorers = tuple(prepared)
        self._threshold = float(threshold)

    def evaluate(self, context: RecommendationContext) -> RecommendationEvaluation:
        eligibility = context.eligibility_decision.status
        if eligibility is EligibilityStatus.INELIGIBLE:
            return RecommendationEvaluation(
                candidate=context.candidate,
                eligibility_decision=context.eligibility_decision,
                status=RecommendationStatus.ELIGIBILITY_BLOCKED,
                reason_codes=(RecommendationReasonCode.ELIGIBILITY_BLOCKED.value,),
                evidence=context.eligibility_decision.evidence,
            )

        components = []
        active = []
        audit = []
        missing = False
        for scorer, component_id, weight in self._scorers:
            try:
                if scorer.component_id != component_id:
                    raise RecommendationScoringError("scorer identity changed")
                returned = scorer.evaluate(context)
                if returned is not None:
                    if not isinstance(returned, RecommendationScoreComponent):
                        raise RecommendationScoringError("invalid scorer result type")
                    result = RecommendationScoreComponent.model_validate(
                        returned.model_dump()
                    )
                    if result.component_id != component_id:
                        raise RecommendationScoringError(
                            "returned component_id does not match"
                        )
            except Exception as exc:
                raise RecommendationScoringError(
                    f"{component_id}: scorer failed"
                ) from exc
            audit.append(
                Evidence(
                    code="COMPONENT_WEIGHT",
                    message=f"{SCORING_VERSION}: configured weight.",
                    field=f"scoring.weights.{component_id}",
                    value=weight,
                )
            )
            if returned is None:
                missing = True
                audit.append(
                    Evidence(
                        code="SOFT_SIGNAL_UNAVAILABLE",
                        message=f"Soft signal unavailable for component {component_id}.",
                        field="scoring.unavailable_component_id",
                        value=component_id,
                    )
                )
                continue
            components.append(result)
            audit.extend(result.evidence)
            if weight > 0:
                active.append((result.score, weight))

        score = None
        if active:
            # Scaling weights avoids overflow without clamping the resulting score.
            scale = max(weight for _, weight in active)
            denominator = math.fsum(weight / scale for _, weight in active)
            score = (
                math.fsum(value * (weight / scale) for value, weight in active)
                / denominator
            )
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise RecommendationScoringError("aggregated score outside [0, 1]")

        if eligibility is EligibilityStatus.UNKNOWN:
            status = RecommendationStatus.ELIGIBILITY_UNCERTAIN
            reason = RecommendationReasonCode.ELIGIBILITY_UNKNOWN
        elif score is None:
            status = RecommendationStatus.SUITABILITY_UNDETERMINED
            reason = RecommendationReasonCode.SOFT_PROFILE_DATA_MISSING
        else:
            status = (
                RecommendationStatus.RECOMMENDED
                if score >= self._threshold
                else RecommendationStatus.NOT_RECOMMENDED
            )
            reason = RecommendationReasonCode.SUITABILITY_ASSESSED
        reasons = [reason.value]
        if missing:
            reasons.append("SOFT_SIGNAL_UNAVAILABLE")
        if score is None:
            reasons.append("NO_ACTIVE_SOFT_SIGNALS")
        audit.append(
            Evidence(
                code="SCORING_CONFIGURATION",
                message=f"{SCORING_VERSION}: heuristic threshold.",
                field="scoring.recommendation_threshold",
                value=self._threshold,
            )
        )
        return RecommendationEvaluation(
            candidate=context.candidate,
            eligibility_decision=context.eligibility_decision,
            status=status,
            reason_codes=reasons,
            evidence=audit,
            suitability_score=score,
            score_components=components,
        )
