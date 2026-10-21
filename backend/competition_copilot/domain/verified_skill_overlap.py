"""One pure presence-only soft signal over explicitly prepared verified facts.

No proficiency comparison, inference, IO, eligibility calculation or ranking.
Unavailable is None, never zero. Aggregation stays in the existing P6 engine.
"""

from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.recommendation import (
    RecommendationContext,
    RecommendationScoreComponent,
)
from competition_copilot.domain.skill import SkillLevel
from competition_copilot.domain.skill_gap import SkillRequirementType
from competition_copilot.domain.source_metadata import SourceType, VerificationStatus

POLICY_VERSION = "verified-skill-overlap-v1"


class VerifiedSkillOverlapScorer:
    component_id = POLICY_VERSION
    policy_version = POLICY_VERSION

    def unavailability_reason(self, context: RecommendationContext) -> str | None:
        """Stateless policy diagnostic; engine's None audit remains unchanged.

        The existing scorer protocol carries only Component | None, so callers
        inspecting this policy can distinguish unsupported levels without
        pretending an unavailable signal is a numeric component or a failure.
        """
        snapshot = context.skill_requirements
        if snapshot is None:
            return "SOFT_SIGNAL_UNAVAILABLE"
        required = [r for r in snapshot.requirement_set.requirements
                    if r.requirement_type is SkillRequirementType.REQUIRED]
        if not required or any(not all(
            fact.source is not None and fact.source.source_type is SourceType.OFFICIAL
            and fact.source.verification_status is VerificationStatus.VERIFIED
            for fact in r.presence_evidence) for r in required):
            return "SOFT_SIGNAL_UNAVAILABLE"
        if any(r.required_level is not None for r in required):
            return "SKILL_LEVEL_POLICY_UNSUPPORTED"
        skills = {s.skill_id: s for s in context.student_profile.skills}
        if any(r.skill_id not in skills or skills[r.skill_id].level is SkillLevel.UNKNOWN
               for r in required):
            return "SOFT_PROFILE_DATA_MISSING"
        return None

    def evaluate(self, context: RecommendationContext) -> RecommendationScoreComponent | None:
        if self.unavailability_reason(context) is not None:
            return None
        snapshot = context.skill_requirements
        facts = snapshot.requirement_set
        coverage = facts.coverage.value
        message = (
            f"All currently verified REQUIRED skill IDs have explicit non-UNKNOWN profile records; "
            f"requirement coverage={coverage}. This presence-only signal does not establish "
            "proficiency sufficiency, satisfaction of all competition requirements, overall fit, "
            "eligibility or winning probability. Self-assessed records remain self-assessed."
        )
        evidence = [
            Evidence(code="SCORING_CONFIGURATION", message="Presence-only component policy version.",
                     field="scoring.policy_version", value=POLICY_VERSION),
            Evidence(code="REQUIREMENT_VERSION", message="Prepared reviewed requirement version.",
                     field="skill_requirements.requirement_version", value=snapshot.requirement_version),
            Evidence(code="REQUIREMENT_COVERAGE", message=message,
                     field="skill_requirements.coverage", value=coverage),
            Evidence(code="PROFILE_SKILL_FACT", message="Actual profile identity; no external verification inferred.",
                     field="student_profile.id", value=context.student_profile.id),
        ]
        for name in ("competition_id", "edition_id", "track_id"):
            evidence.append(Evidence(code="RECOMMENDATION_TARGET", message="Exact prepared candidate identity.",
                                     field="candidate." + name, value=getattr(context.candidate, name)))
        skills = {s.skill_id: s for s in context.student_profile.skills}
        for requirement in sorted(facts.requirements, key=lambda r: r.skill_id):
            if requirement.requirement_type is not SkillRequirementType.REQUIRED:
                continue
            skill = skills[requirement.skill_id]
            evidence.extend(Evidence.model_validate(e.model_dump()) for e in requirement.presence_evidence)
            evidence.append(Evidence(code="VERIFIED_SKILL_OVERLAP", message="Exact skill ID has an explicit profile record.",
                field="scoring.matched_skill_id", value=skill.skill_id))
            for name in ("level", "self_assessed", "note"):
                value = getattr(skill, name)
                if name == "level":
                    value = value.value
                if value is not None:
                    evidence.append(Evidence(code="PROFILE_SKILL_FACT",
                        message="Actual supplied profile fact; self-assessment is not external verification.",
                        field=f"skills.{skill.skill_id}.{name}", value=value))
        return RecommendationScoreComponent(component_id=self.component_id, score=1.0,
            reason_code="VERIFIED_SKILL_OVERLAP", message=message, evidence=evidence)
