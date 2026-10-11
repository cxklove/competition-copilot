"""Deterministic aggregation of prepared hard eligibility rules."""

from collections.abc import Sequence

from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.eligibility import (
    EligibilityContext,
    EligibilityDecision,
    EligibilityReasonCode,
    EligibilityRule,
    EligibilityScope,
    EligibilityStatus,
    RuleEvaluation,
)


class EligibilityEvaluationError(ValueError):
    """Invalid rule configuration or failure while evaluating a rule."""

    def __init__(self, rule_id: str | None, reason: str) -> None:
        self.rule_id = rule_id
        self.reason = reason
        super().__init__(f"{rule_id or 'eligibility'}: {reason}")


class EligibilityRuleEngine:
    """Evaluate every supplied rule once, then aggregate its hard-rule results.

    Rule order determines audit order, never the final status. The caller must
    supply the complete applicable rule set; this engine does not discover rules.
    """

    def evaluate(
        self, context: EligibilityContext, rules: Sequence[EligibilityRule]
    ) -> EligibilityDecision:
        targets = {
            EligibilityScope.COMPETITION: context.competition_id,
            EligibilityScope.EDITION: context.edition_id,
            EligibilityScope.TRACK: context.track_id,
        }
        prepared: list[tuple[EligibilityRule, str, EligibilityScope]] = []
        seen_ids: set[str] = set()

        # Validate the whole configuration before running any rule.
        for rule in rules:
            try:
                rule_id = rule.rule_id
                scope = rule.scope
            except Exception as exc:
                raise EligibilityEvaluationError(None, "cannot read rule identity") from exc
            if not isinstance(rule_id, str) or not rule_id or rule_id != rule_id.strip():
                raise EligibilityEvaluationError(None, "rule_id must be a nonblank stable ID")
            if rule_id in seen_ids:
                raise EligibilityEvaluationError(rule_id, "duplicate rule_id")
            if not isinstance(scope, EligibilityScope):
                raise EligibilityEvaluationError(rule_id, "invalid rule scope")
            if targets[scope] is None:
                raise EligibilityEvaluationError(rule_id, "rule scope has no target in context")
            seen_ids.add(rule_id)
            prepared.append((rule, rule_id, scope))

        if not prepared:
            return EligibilityDecision(
                status=EligibilityStatus.UNKNOWN,
                reason_codes=[EligibilityReasonCode.RULE_DATA_MISSING.value],
                evidence=[
                    Evidence(
                        code=EligibilityReasonCode.RULE_DATA_MISSING.value,
                        message="No eligibility rules were supplied for this target.",
                        field="eligibility_rules",
                    )
                ],
                competition_id=context.competition_id,
                edition_id=context.edition_id,
                track_id=context.track_id,
            )

        evaluations: list[RuleEvaluation] = []
        for rule, rule_id, scope in prepared:
            try:
                returned = rule.evaluate(context)
            except Exception as exc:
                raise EligibilityEvaluationError(rule_id, "rule execution failed") from exc
            if not isinstance(returned, RuleEvaluation):
                raise EligibilityEvaluationError(rule_id, "rule returned invalid evaluation")
            try:
                result = RuleEvaluation.model_validate(returned.model_dump())
            except Exception as exc:
                raise EligibilityEvaluationError(rule_id, "rule returned invalid evaluation") from exc
            if result.rule_id != rule_id:
                raise EligibilityEvaluationError(rule_id, "returned rule_id does not match")
            if result.scope is not scope:
                raise EligibilityEvaluationError(rule_id, "returned scope does not match")
            if result.target_id != targets[scope]:
                raise EligibilityEvaluationError(rule_id, "returned target_id does not match")
            evaluations.append(result)

        statuses = {item.status for item in evaluations}
        if EligibilityStatus.INELIGIBLE in statuses:
            status = EligibilityStatus.INELIGIBLE
        elif EligibilityStatus.UNKNOWN in statuses:
            status = EligibilityStatus.UNKNOWN
        else:
            status = EligibilityStatus.ELIGIBLE

        # DecisionResult normalizes repeated reason codes. Individual evaluations
        # retain the complete ordered audit trail, including repeated evidence.
        return EligibilityDecision(
            status=status,
            reason_codes=[item.reason_code.value for item in evaluations],
            evidence=[piece for item in evaluations for piece in item.evidence],
            competition_id=context.competition_id,
            edition_id=context.edition_id,
            track_id=context.track_id,
            rule_evaluations=evaluations,
        )
