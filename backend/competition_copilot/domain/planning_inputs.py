"""Pure P8.2 derivation of needs from validated P7 conclusions, not planning."""

import json

from competition_copilot.domain.plan import (
    PlanningNeed,
    PlanningNeedType,
    SkillGapPlanningAudit,
)
from competition_copilot.domain.skill_gap import (
    SkillGapDecision,
    SkillGapItemStatus,
    SkillGapReasonCode,
    SkillRequirementCoverage,
)


def _validated_decision(decision: SkillGapDecision) -> SkillGapDecision:
    if not isinstance(decision, SkillGapDecision):
        raise TypeError("planning inputs require a SkillGapDecision snapshot")
    return SkillGapDecision.model_validate(decision)


def _need_id(
    decision: SkillGapDecision, kind: PlanningNeedType, skill_id: str | None
) -> str:
    """Unambiguous canonical ID tuple: stable IDs only, never labels or hash()."""
    target = decision.target
    identity = (
        target.competition_id, target.edition_id, target.track_id,
        "skill" if skill_id is not None else "requirement_set", skill_id, kind.value,
    )
    return "planning-need:" + json.dumps(identity, ensure_ascii=True, separators=(",", ":"))


class PlanningInputDeriver:
    """Map all items in supplied order, then append target coverage uncertainty.

    source_item=None identifies a requirement-set need in the existing P8.1
    contract. No skill ID is invented. Caller retains the source decision and
    can obtain its small audit via source_audit; no Plan/Milestone is constructed.
    """

    def derive(self, decision: SkillGapDecision) -> tuple[PlanningNeed, ...]:
        decision = _validated_decision(decision)
        needs = []
        for item in decision.items:
            if item.status is SkillGapItemStatus.SATISFIED:
                continue
            kind = (
                PlanningNeedType.SKILL_IMPROVEMENT if item.status is SkillGapItemStatus.GAP
                else PlanningNeedType.UNCERTAINTY_RESOLUTION
            )
            needs.append(PlanningNeed(
                id=_need_id(decision, kind, item.requirement.skill_id),
                kind=kind,
                reason_codes=item.reason_codes,
                source_item=item,
            ))

        coverage_reason = {
            SkillRequirementCoverage.PARTIAL: SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE,
            SkillRequirementCoverage.MISSING: SkillGapReasonCode.REQUIREMENT_DATA_MISSING,
        }.get(decision.requirements.coverage)
        if coverage_reason is not None:
            kind = PlanningNeedType.UNCERTAINTY_RESOLUTION
            needs.append(PlanningNeed(
                id=_need_id(decision, kind, None),
                kind=kind,
                reason_codes=(coverage_reason,),
                source_item=None,
            ))
        return tuple(needs)

    def source_audit(self, decision: SkillGapDecision) -> SkillGapPlanningAudit:
        """Copy the exact P7 target/coverage/status/reasons, without reevaluation."""
        decision = _validated_decision(decision)
        return SkillGapPlanningAudit(
            target=decision.target,
            coverage=decision.requirements.coverage,
            gap_status=decision.gap_status,
            reason_codes=decision.reason_codes,
        )
