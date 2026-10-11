"""Pure, synthetic tests for deterministic eligibility aggregation."""

from dataclasses import dataclass, field

import pytest

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
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
from competition_copilot.domain.eligibility_engine import (
    EligibilityEvaluationError,
    EligibilityRuleEngine,
)
from competition_copilot.domain.student import StudentProfile


def context(*, track: bool = False) -> EligibilityContext:
    return EligibilityContext(
        student_profile=StudentProfile(id="student-1"),
        competition=Competition(id="competition-1", name="Competition"),
        edition=CompetitionEdition(
            id="edition-1", competition_id="competition-1", year=2026, name="2026"
        ),
        track=(
            CompetitionTrack(id="track-1", edition_id="edition-1", name="Track")
            if track
            else None
        ),
    )


def reason_for(status: EligibilityStatus) -> EligibilityReasonCode:
    return {
        EligibilityStatus.ELIGIBLE: EligibilityReasonCode.RULE_SATISFIED,
        EligibilityStatus.INELIGIBLE: EligibilityReasonCode.RULE_VIOLATED,
        EligibilityStatus.UNKNOWN: EligibilityReasonCode.PROFILE_DATA_MISSING,
    }[status]


@dataclass
class FakeRule:
    rule_id: str
    status: EligibilityStatus
    scope: EligibilityScope = EligibilityScope.EDITION
    reason_code: EligibilityReasonCode | None = None
    returned_rule_id: str | None = None
    returned_scope: EligibilityScope | None = None
    returned_target_id: str | None = None
    pieces: list[Evidence] = field(default_factory=list)
    calls: int = 0

    def evaluate(self, target: EligibilityContext) -> RuleEvaluation:
        self.calls += 1
        target_id = {
            EligibilityScope.COMPETITION: target.competition_id,
            EligibilityScope.EDITION: target.edition_id,
            EligibilityScope.TRACK: target.track_id,
        }[self.scope]
        return RuleEvaluation(
            rule_id=self.returned_rule_id or self.rule_id,
            scope=self.returned_scope or self.scope,
            target_id=self.returned_target_id or target_id,
            status=self.status,
            reason_code=self.reason_code or reason_for(self.status),
            message="Synthetic rule result.",
            evidence=self.pieces or [Evidence(code=self.rule_id, message="Checked rule.")],
        )


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((EligibilityStatus.ELIGIBLE,), EligibilityStatus.ELIGIBLE),
        ((EligibilityStatus.ELIGIBLE, EligibilityStatus.ELIGIBLE), EligibilityStatus.ELIGIBLE),
        ((EligibilityStatus.UNKNOWN,), EligibilityStatus.UNKNOWN),
        ((EligibilityStatus.ELIGIBLE, EligibilityStatus.UNKNOWN), EligibilityStatus.UNKNOWN),
        ((EligibilityStatus.UNKNOWN, EligibilityStatus.ELIGIBLE), EligibilityStatus.UNKNOWN),
        ((EligibilityStatus.INELIGIBLE,), EligibilityStatus.INELIGIBLE),
        ((EligibilityStatus.ELIGIBLE, EligibilityStatus.INELIGIBLE), EligibilityStatus.INELIGIBLE),
        ((EligibilityStatus.UNKNOWN, EligibilityStatus.INELIGIBLE), EligibilityStatus.INELIGIBLE),
        ((EligibilityStatus.INELIGIBLE, EligibilityStatus.UNKNOWN), EligibilityStatus.INELIGIBLE),
        (
            (EligibilityStatus.ELIGIBLE, EligibilityStatus.UNKNOWN, EligibilityStatus.INELIGIBLE),
            EligibilityStatus.INELIGIBLE,
        ),
    ],
)
def test_decision_matrix(
    statuses: tuple[EligibilityStatus, ...], expected: EligibilityStatus
) -> None:
    rules: list[EligibilityRule] = [
        FakeRule(rule_id=f"rule-{index}", status=status)
        for index, status in enumerate(statuses)
    ]
    result = EligibilityRuleEngine().evaluate(context(), rules)

    assert isinstance(result, EligibilityDecision)
    assert result.status is expected
    assert [item.status for item in result.rule_evaluations] == list(statuses)
    assert [item.rule_id for item in result.rule_evaluations] == [
        f"rule-{index}" for index in range(len(statuses))
    ]
    assert result.competition_id == "competition-1"
    assert result.edition_id == "edition-1"
    assert EligibilityDecision.model_validate_json(result.model_dump_json()) == result
    assert result.model_dump(mode="json")["status"] == expected.value


def test_empty_rules_are_business_unknown_with_auditable_missing_rule_reason() -> None:
    result = EligibilityRuleEngine().evaluate(context(), [])

    assert result.status is EligibilityStatus.UNKNOWN
    assert result.reason_codes == [EligibilityReasonCode.RULE_DATA_MISSING.value]
    assert result.rule_evaluations == []
    assert result.evidence[0].code == EligibilityReasonCode.RULE_DATA_MISSING.value
    assert EligibilityDecision.model_validate_json(result.model_dump_json()) == result


def test_no_short_circuit_and_evidence_order_with_repeated_evidence() -> None:
    shared = Evidence(code="shared", message="Same source fact.")
    rules = [
        FakeRule("a", EligibilityStatus.INELIGIBLE, pieces=[shared]),
        FakeRule("b", EligibilityStatus.ELIGIBLE, pieces=[shared]),
        FakeRule("c", EligibilityStatus.UNKNOWN, pieces=[Evidence(code="c", message="Missing")]),
    ]

    result = EligibilityRuleEngine().evaluate(context(), rules)

    assert result.status is EligibilityStatus.INELIGIBLE
    assert [rule.calls for rule in rules] == [1, 1, 1]
    assert [item.rule_id for item in result.rule_evaluations] == ["a", "b", "c"]
    assert [item.code for item in result.evidence] == ["shared", "shared", "c"]
    assert result.reason_codes == [
        EligibilityReasonCode.RULE_VIOLATED.value,
        EligibilityReasonCode.RULE_SATISFIED.value,
        EligibilityReasonCode.PROFILE_DATA_MISSING.value,
    ]


def test_final_status_is_order_independent_but_audit_order_is_not() -> None:
    first = FakeRule("first", EligibilityStatus.UNKNOWN)
    second = FakeRule("second", EligibilityStatus.INELIGIBLE)
    engine = EligibilityRuleEngine()

    forward = engine.evaluate(context(), [first, second])
    reverse = engine.evaluate(context(), [second, first])

    assert forward.status is reverse.status is EligibilityStatus.INELIGIBLE
    assert [item.rule_id for item in forward.rule_evaluations] == ["first", "second"]
    assert [item.rule_id for item in reverse.rule_evaluations] == ["second", "first"]


def test_repeated_evaluation_is_deterministic() -> None:
    target = context(track=True)
    rules = [
        FakeRule("competition-rule", EligibilityStatus.ELIGIBLE, EligibilityScope.COMPETITION),
        FakeRule("track-rule", EligibilityStatus.UNKNOWN, EligibilityScope.TRACK),
    ]
    engine = EligibilityRuleEngine()
    before = target.model_dump(mode="json")

    first = engine.evaluate(target, rules)
    second = engine.evaluate(target, rules)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert target.model_dump(mode="json") == before
    assert [item.target_id for item in first.rule_evaluations] == [
        "competition-1", "track-1"
    ]


def test_duplicate_ids_fail_before_any_rule_executes() -> None:
    first = FakeRule("duplicate", EligibilityStatus.ELIGIBLE)
    second = FakeRule("duplicate", EligibilityStatus.INELIGIBLE)

    with pytest.raises(EligibilityEvaluationError, match="duplicate rule_id") as caught:
        EligibilityRuleEngine().evaluate(context(), [first, second])

    assert caught.value.rule_id == "duplicate"
    assert [first.calls, second.calls] == [0, 0]


@pytest.mark.parametrize("rule_id", ["", " ", " bad "])
def test_invalid_public_rule_id_is_configuration_error(rule_id: str) -> None:
    with pytest.raises(EligibilityEvaluationError, match="rule_id"):
        EligibilityRuleEngine().evaluate(context(), [FakeRule(rule_id, EligibilityStatus.ELIGIBLE)])


def test_rule_id_scope_and_target_mismatch_fail_fast() -> None:
    cases = [
        (FakeRule("a", EligibilityStatus.ELIGIBLE, returned_rule_id="b"), "rule_id"),
        (
            FakeRule("a", EligibilityStatus.ELIGIBLE, returned_scope=EligibilityScope.COMPETITION),
            "scope",
        ),
        (FakeRule("a", EligibilityStatus.ELIGIBLE, returned_target_id="other"), "target_id"),
    ]
    for rule, reason in cases:
        with pytest.raises(EligibilityEvaluationError, match=reason):
            EligibilityRuleEngine().evaluate(context(), [rule])


def test_track_rule_without_track_is_configuration_error() -> None:
    rule = FakeRule("track-rule", EligibilityStatus.UNKNOWN, scope=EligibilityScope.TRACK)
    with pytest.raises(EligibilityEvaluationError, match="no target"):
        EligibilityRuleEngine().evaluate(context(), [rule])
    assert rule.calls == 0


@pytest.mark.parametrize("exception", [RuntimeError("bug"), ValueError("bad"), AssertionError("bad")])
def test_rule_exception_is_engine_error_not_unknown(exception: Exception) -> None:
    class RaisingRule(FakeRule):
        def evaluate(self, target: EligibilityContext) -> RuleEvaluation:
            raise exception

    with pytest.raises(EligibilityEvaluationError, match="rule execution failed") as caught:
        EligibilityRuleEngine().evaluate(
            context(), [RaisingRule("broken", EligibilityStatus.ELIGIBLE)]
        )
    assert caught.value.rule_id == "broken"
    assert caught.value.__cause__ is exception


def test_invalid_return_is_engine_error_not_unknown() -> None:
    class InvalidRule(FakeRule):
        def evaluate(self, target: EligibilityContext) -> RuleEvaluation:
            return RuleEvaluation.model_construct(
                rule_id=self.rule_id,
                scope=self.scope,
                target_id=target.edition_id,
                status=EligibilityStatus.ELIGIBLE,
                reason_code=EligibilityReasonCode.RULE_VIOLATED,
                message="invalid",
                evidence=[Evidence(code="bad", message="Invalid")],
            )

    with pytest.raises(EligibilityEvaluationError, match="invalid evaluation"):
        EligibilityRuleEngine().evaluate(context(), [InvalidRule("bad", EligibilityStatus.ELIGIBLE)])


@pytest.mark.parametrize(
    "reason_code",
    [EligibilityReasonCode.PROFILE_DATA_MISSING, EligibilityReasonCode.RULE_DATA_MISSING],
)
def test_business_unknown_is_not_an_engine_error(reason_code: EligibilityReasonCode) -> None:
    result = EligibilityRuleEngine().evaluate(
        context(), [FakeRule("unknown", EligibilityStatus.UNKNOWN, reason_code=reason_code)]
    )
    assert result.status is EligibilityStatus.UNKNOWN
    assert result.reason_codes == [reason_code.value]
