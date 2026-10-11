"""Pure rules constructed from reviewed structured eligibility facts."""

from dataclasses import dataclass

from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.eligibility import (
    EligibilityContext,
    EligibilityReasonCode,
    EligibilityScope,
    EligibilityStatus,
    RuleEvaluation,
)
from competition_copilot.domain.eligibility_policy import EducationLevelConstraint


@dataclass(frozen=True)
class EducationLevelRule:
    fact: EducationLevelConstraint

    @property
    def rule_id(self) -> str:
        return self.fact.rule_id

    @property
    def scope(self) -> EligibilityScope:
        return self.fact.scope

    def evaluate(self, context: EligibilityContext) -> RuleEvaluation:
        value = context.student_profile.education_level
        if value is None:
            status = EligibilityStatus.UNKNOWN
            reason = EligibilityReasonCode.PROFILE_DATA_MISSING
            message = "Student education level is missing."
        elif value in self.fact.allowed_levels:
            status = EligibilityStatus.ELIGIBLE
            reason = EligibilityReasonCode.RULE_SATISFIED
            message = "Student education level is allowed by the official rule."
        elif self.fact.alternative_profile_field is not None:
            status = EligibilityStatus.UNKNOWN
            reason = EligibilityReasonCode.PROFILE_DATA_MISSING
            message = (
                f"Student profile field {self.fact.alternative_profile_field} is missing; "
                "alternate eligibility cannot be determined."
            )
        else:
            status = EligibilityStatus.INELIGIBLE
            reason = EligibilityReasonCode.RULE_VIOLATED
            message = "Student education level is excluded by the official rule."
        target_id = {
            EligibilityScope.COMPETITION: context.competition_id,
            EligibilityScope.EDITION: context.edition_id,
            EligibilityScope.TRACK: context.track_id,
        }[self.scope]
        return RuleEvaluation(
            rule_id=self.rule_id,
            scope=self.scope,
            target_id=target_id,
            status=status,
            reason_code=reason,
            message=message,
            evidence=[
                Evidence(
                    code=f"{self.rule_id}:official-rule",
                    message=self.fact.evidence_text,
                    source=self.fact.source,
                ),
                Evidence(
                    code=f"{self.rule_id}:profile-fact",
                    message="Student profile value used for this rule.",
                    field="education_level",
                    value=value.value if value is not None else None,
                )
            ],
        )


@dataclass(frozen=True)
class IncompletePolicyRule:
    """A declared policy coverage gap; never treats a partial policy as complete."""

    scope: EligibilityScope
    target_id: str
    coverage_note: str
    rule_id: str = "policy-coverage-incomplete"

    def evaluate(self, context: EligibilityContext) -> RuleEvaluation:
        return RuleEvaluation(
            rule_id=self.rule_id,
            scope=self.scope,
            target_id=self.target_id,
            status=EligibilityStatus.UNKNOWN,
            reason_code=EligibilityReasonCode.RULE_DATA_MISSING,
            message=self.coverage_note,
            evidence=[
                Evidence(
                    code=self.rule_id,
                    message=self.coverage_note,
                    field="eligibility_policy.coverage",
                    value="partial",
                )
            ],
        )
