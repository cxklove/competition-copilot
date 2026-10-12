"""Deterministic comparison of prepared skill facts, without data access."""

from types import MappingProxyType

from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.skill import SkillLevel
from competition_copilot.domain.skill_gap import (
    SkillFactRole,
    SkillGapContext,
    SkillGapDecision,
    SkillGapItem,
    SkillGapItemStatus,
    SkillGapReasonCode,
    SkillGapStatus,
    SkillRequirementCoverage,
    skill_fact_field,
)

# UNKNOWN has no ordinal rank. A new enum member requires an explicit decision.
LEVEL_ORDER = MappingProxyType({
    SkillLevel.UNKNOWN: None,
    SkillLevel.BEGINNER: 0,
    SkillLevel.INTERMEDIATE: 1,
    SkillLevel.ADVANCED: 2,
})
if set(LEVEL_ORDER) != set(SkillLevel):
    raise RuntimeError("SkillLevel ordering is incomplete")


class SkillGapEngine:
    """Evaluate every requirement in supplied order; preserve all matching evidence.

    Any required or desired known gap proves GAP_IDENTIFIED. NO_GAP requires
    COMPLETE coverage, specified thresholds and every declared requirement satisfied.
    Contract errors propagate; no partial result or fallback uncertainty is returned.
    """

    def evaluate(self, context: SkillGapContext) -> SkillGapDecision:
        if not isinstance(context, SkillGapContext):
            raise TypeError("evaluate requires a SkillGapContext snapshot")
        context = SkillGapContext.model_validate(context)
        skills = {skill.skill_id: skill for skill in context.student_profile.skills}
        evidence_by_field: dict[str, list[Evidence]] = {}
        for fact in context.student_skill_evidence:
            evidence_by_field.setdefault(fact.field, []).append(fact)

        items = []
        for requirement in context.requirements.requirements:
            student = skills.get(requirement.skill_id)
            level = student.level if student is not None else None
            missing_student = level in (None, SkillLevel.UNKNOWN)
            unspecified = requirement.required_level is None
            student_evidence = () if missing_student else tuple(evidence_by_field[
                skill_fact_field(SkillFactRole.STUDENT_SKILL, requirement.skill_id)
            ])
            if missing_student or unspecified:
                status = SkillGapItemStatus.UNKNOWN
                reasons = (
                    (SkillGapReasonCode.REQUIREMENT_PROFICIENCY_UNSPECIFIED,) if unspecified else ()
                ) + ((SkillGapReasonCode.STUDENT_SKILL_DATA_MISSING,) if missing_student else ())
            else:
                satisfied = LEVEL_ORDER[level] >= LEVEL_ORDER[requirement.required_level]
                status = SkillGapItemStatus.SATISFIED if satisfied else SkillGapItemStatus.GAP
                reasons = (
                    SkillGapReasonCode.REQUIREMENT_SATISFIED if satisfied
                    else SkillGapReasonCode.SKILL_BELOW_REQUIREMENT,
                )
            items.append(SkillGapItem(
                requirement=requirement,
                student_level=level,
                status=status,
                reason_codes=reasons,
                student_evidence=student_evidence,
            ))

        coverage = context.requirements.coverage
        if any(item.status is SkillGapItemStatus.GAP for item in items):
            gap_status = SkillGapStatus.GAP_IDENTIFIED
        elif (
            coverage is SkillRequirementCoverage.COMPLETE
            and items
            and all(item.requirement.required_level is not None for item in items)
            and all(item.status is SkillGapItemStatus.SATISFIED for item in items)
        ):
            gap_status = SkillGapStatus.NO_GAP
        else:
            gap_status = SkillGapStatus.UNDETERMINED

        reasons = list(dict.fromkeys(reason for item in items for reason in item.reason_codes))
        if coverage is SkillRequirementCoverage.PARTIAL:
            reasons.append(SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE)
        elif coverage is SkillRequirementCoverage.MISSING:
            reasons.append(SkillGapReasonCode.REQUIREMENT_DATA_MISSING)
        return SkillGapDecision(
            target=context.requirements.target,
            requirements=context.requirements,
            gap_status=gap_status,
            items=tuple(items),
            reason_codes=tuple(reasons),
            audit_evidence=(Evidence(
                code="SKILL_GAP_ANALYSIS_V2",
                message="Known gap takes precedence; no gap requires COMPLETE, specified thresholds and known satisfaction.",
                field="gap_status",
                value=gap_status.value,
            ),),
        )
