"""Canonical decisions from supplied ImpactAnalysis; no Event re-analysis."""

from datetime import datetime, timezone
from typing import Any

from pydantic import AwareDatetime, TypeAdapter

from competition_copilot.domain.plan import CompetitionPlan
from competition_copilot.domain.replanning import (
    AffectedPlanScope,
    EventImpactAnalysis,
    ImpactOutcome,
    PlanReference,
    ReplanningDecision,
    ReplanningOutcome,
    ReplanningReasonCode,
    ScopeState,
)


def _utc(value: Any) -> Any:
    """Canonical representation of supplied aware instants, not new facts."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, dict):
        return {key: _utc(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return tuple(_utc(item) for item in value)
    return value


class ReplanningDecisionService:
    """Confirmed > unresolved > negative; retain all unique supplied analyses.

    P11.1 has no analysis/decision ID. Its unique trigger Event ID is the batch
    lineage key: exact duplicates normalize; conflicting analyses for that same
    key reject. Event ID is read only as a reference, never as impact authority.
    The returned frozen Decision already contains the canonical Scope.
    """

    def decide(
        self, impacts: tuple[EventImpactAnalysis, ...], plan: CompetitionPlan,
        *, evaluated_at: datetime,
    ) -> ReplanningDecision:
        if not isinstance(impacts, tuple):
            raise TypeError("impacts must be an immutable tuple")
        if not impacts:
            raise ValueError("Empty analyses do not prove no impact")
        if not isinstance(plan, CompetitionPlan):
            raise TypeError("plan must be a validated CompetitionPlan")
        reference = PlanReference.from_plan(plan)
        if not isinstance(evaluated_at, datetime):
            raise TypeError("evaluated_at must be an explicit aware datetime")
        evaluated_at = TypeAdapter(AwareDatetime).validate_python(evaluated_at).astimezone(timezone.utc)
        unique: dict[str, EventImpactAnalysis] = {}
        for impact in impacts:
            if not isinstance(impact, EventImpactAnalysis):
                raise TypeError("impacts must contain validated EventImpactAnalysis")
            impact = EventImpactAnalysis.model_validate(_utc(impact.model_dump()))
            if impact.plan != reference:
                raise ValueError("Every analysis must bind the exact supplied Plan context")
            key = impact.event.id
            if key in unique and impact != unique[key]:
                raise ValueError("Same trigger identity cannot identify conflicting analyses")
            unique[key] = impact
        canonical = tuple(unique[key] for key in sorted(unique))
        confirmed = tuple(item for item in canonical if item.outcome == ImpactOutcome.AFFECTS_PLAN)
        uncertain = any(item.outcome == ImpactOutcome.UNDETERMINED for item in canonical)
        milestones: tuple[str, ...] = ()
        whole_plan = False
        state = ScopeState.KNOWN
        outcome = ReplanningOutcome.KEEP_CURRENT_PLAN
        reason = ReplanningReasonCode.NO_PLAN_IMPACT
        if confirmed:
            milestones = tuple(sorted({mid for item in confirmed for mid in item.scope.milestone_ids}))
            whole_plan = any(item.scope.whole_plan for item in confirmed)
            remainder = uncertain or any(item.scope.has_unresolved_remainder for item in confirmed)
            state = ScopeState.PARTIALLY_RESOLVED if remainder else ScopeState.KNOWN
            outcome = ReplanningOutcome.REPLAN
            reason = (ReplanningReasonCode.CONFIRMED_IMPACT_WITH_UNRESOLVED_REMAINDER
                      if remainder else ReplanningReasonCode.CONFIRMED_PLAN_IMPACT)
        elif uncertain:
            state = ScopeState.UNRESOLVED
            outcome = ReplanningOutcome.UNDETERMINED
            reason = ReplanningReasonCode.IMPACT_UNDETERMINED
        return ReplanningDecision(
            impacts=canonical, evaluated_at=evaluated_at, outcome=outcome,
            scope=AffectedPlanScope(
                plan_id=plan.id, state=state, whole_plan=whole_plan, milestone_ids=milestones,
            ),
            reason_codes=(reason,),
        )
