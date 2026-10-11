import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.decision import DecisionResult, Evidence
from competition_copilot.domain.eligibility import (
    EligibilityContext,
    EligibilityDecision,
    EligibilityReasonCode,
    EligibilityRule,
    EligibilityScope,
    EligibilityStatus,
    RuleEvaluation,
)
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    SourceType,
    VerificationStatus,
)
from competition_copilot.domain.student import StudentProfile


def context(*, with_track: bool = False) -> EligibilityContext:
    return EligibilityContext(
        student_profile=StudentProfile(id="student-1"),
        competition=Competition(id="competition-1", name="Competition"),
        edition=CompetitionEdition(
            id="edition-1", competition_id="competition-1", year=2026, name="2026"
        ),
        track=(
            CompetitionTrack(id="track-1", edition_id="edition-1", name="Track")
            if with_track
            else None
        ),
    )


def evidence(field: str = "education_level") -> Evidence:
    return Evidence(code="profile-fact", message="Profile field inspected.", field=field)


def evaluation(
    status: EligibilityStatus,
    reason_code: EligibilityReasonCode,
    *,
    scope: EligibilityScope = EligibilityScope.EDITION,
    target_id: str = "edition-1",
) -> RuleEvaluation:
    return RuleEvaluation(
        rule_id="education-level-v1",
        scope=scope,
        target_id=target_id,
        status=status,
        reason_code=reason_code,
        message="Rule evaluated.",
        evidence=[evidence()],
    )


class FakeEducationRule:
    rule_id = "education-level-v1"
    scope = EligibilityScope.EDITION

    def evaluate(self, context: EligibilityContext) -> RuleEvaluation:
        if context.student_profile.education_level is None:
            return evaluation(
                EligibilityStatus.UNKNOWN,
                EligibilityReasonCode.PROFILE_DATA_MISSING,
            )
        return evaluation(
            EligibilityStatus.ELIGIBLE,
            EligibilityReasonCode.RULE_SATISFIED,
        )


def test_three_statuses_and_protocol_is_pure_and_repeatable() -> None:
    assert set(EligibilityStatus) == {
        EligibilityStatus.ELIGIBLE,
        EligibilityStatus.INELIGIBLE,
        EligibilityStatus.UNKNOWN,
    }
    rule: EligibilityRule = FakeEducationRule()
    target = context()
    before = target.model_dump(mode="json")

    assert rule.rule_id == "education-level-v1"
    assert rule.scope is EligibilityScope.EDITION
    assert rule.evaluate(target) == rule.evaluate(target)
    assert rule.evaluate(target).reason_code is EligibilityReasonCode.PROFILE_DATA_MISSING
    assert target.model_dump(mode="json") == before


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (EligibilityStatus.ELIGIBLE, EligibilityReasonCode.RULE_SATISFIED),
        (EligibilityStatus.INELIGIBLE, EligibilityReasonCode.RULE_VIOLATED),
        (EligibilityStatus.UNKNOWN, EligibilityReasonCode.PROFILE_DATA_MISSING),
        (EligibilityStatus.UNKNOWN, EligibilityReasonCode.RULE_DATA_MISSING),
    ],
)
def test_rule_evaluation_status_reason_and_json(
    status: EligibilityStatus, reason: EligibilityReasonCode
) -> None:
    result = evaluation(status, reason)

    assert result.rule_id == "education-level-v1"
    assert result.evidence[0].field == "education_level"
    assert result.model_dump(mode="json")["reason_code"] == reason.value
    assert RuleEvaluation.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("rule_id", ["", " \t "])
def test_rule_id_must_be_nonblank(rule_id: str) -> None:
    with pytest.raises(ValidationError, match="rule_id"):
        RuleEvaluation(
            rule_id=rule_id,
            scope=EligibilityScope.EDITION,
            target_id="edition-1",
            status=EligibilityStatus.ELIGIBLE,
            reason_code=EligibilityReasonCode.RULE_SATISFIED,
            message="checked",
            evidence=[evidence()],
        )


def test_rule_reason_must_match_status_and_evidence_is_required() -> None:
    with pytest.raises(ValidationError, match="reason_code"):
        evaluation(EligibilityStatus.ELIGIBLE, EligibilityReasonCode.RULE_VIOLATED)
    with pytest.raises(ValidationError, match="evidence"):
        RuleEvaluation(
            rule_id="rule-v1",
            scope=EligibilityScope.EDITION,
            target_id="edition-1",
            status=EligibilityStatus.UNKNOWN,
            reason_code=EligibilityReasonCode.RULE_DATA_MISSING,
            message="No verified rule data.",
            evidence=[],
        )


def test_context_exposes_ids_and_validates_relationships() -> None:
    target = context(with_track=True)
    assert (target.competition_id, target.edition_id, target.track_id) == (
        "competition-1", "edition-1", "track-1"
    )
    assert context().track_id is None
    assert EligibilityContext.model_validate_json(target.model_dump_json()) == target
    with pytest.raises(ValidationError, match="edition must belong"):
        EligibilityContext(
            student_profile=target.student_profile,
            competition=target.competition,
            edition=CompetitionEdition(
                id="other", competition_id="wrong", year=2026, name="Other"
            ),
        )
    with pytest.raises(ValidationError, match="track must belong"):
        EligibilityContext(
            student_profile=target.student_profile,
            competition=target.competition,
            edition=target.edition,
            track=CompetitionTrack(id="wrong", edition_id="other", name="Wrong"),
        )


def decision(status: EligibilityStatus, item: RuleEvaluation) -> EligibilityDecision:
    return EligibilityDecision(
        status=status,
        reason_codes=[item.reason_code.value],
        evidence=item.evidence,
        competition_id="competition-1",
        edition_id="edition-1",
        rule_evaluations=[item],
    )


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (EligibilityStatus.ELIGIBLE, EligibilityReasonCode.RULE_SATISFIED),
        (EligibilityStatus.INELIGIBLE, EligibilityReasonCode.RULE_VIOLATED),
        (EligibilityStatus.UNKNOWN, EligibilityReasonCode.PROFILE_DATA_MISSING),
        (EligibilityStatus.UNKNOWN, EligibilityReasonCode.RULE_DATA_MISSING),
    ],
)
def test_decision_reuses_decision_result_and_round_trips(
    status: EligibilityStatus, reason: EligibilityReasonCode
) -> None:
    result = decision(status, evaluation(status, reason))
    assert isinstance(result, DecisionResult)
    assert result.status is status
    assert result.reason_codes == [reason.value]
    assert EligibilityDecision.model_validate_json(result.model_dump_json()) == result
    assert json.loads(result.model_dump_json()) == result.model_dump(mode="json")


def test_unknown_can_cite_missing_official_rule_without_inventing_a_rule() -> None:
    result = EligibilityDecision(
        status=EligibilityStatus.UNKNOWN,
        reason_codes=[EligibilityReasonCode.RULE_DATA_MISSING.value],
        evidence=[Evidence(code="missing-rule", message="No structured official rule.")],
        competition_id="competition-1",
        edition_id="edition-1",
    )
    assert result.rule_evaluations == []


@pytest.mark.parametrize(
    ("status", "item", "reason"),
    [
        (
            EligibilityStatus.INELIGIBLE,
            evaluation(EligibilityStatus.ELIGIBLE, EligibilityReasonCode.RULE_SATISFIED),
            "violated rule",
        ),
        (
            EligibilityStatus.UNKNOWN,
            evaluation(EligibilityStatus.ELIGIBLE, EligibilityReasonCode.RULE_SATISFIED),
            "unknown reason",
        ),
        (
            EligibilityStatus.ELIGIBLE,
            evaluation(EligibilityStatus.INELIGIBLE, EligibilityReasonCode.RULE_VIOLATED),
            "satisfied rules only",
        ),
    ],
)
def test_decision_rejects_inconsistent_states(
    status: EligibilityStatus, item: RuleEvaluation, reason: str
) -> None:
    with pytest.raises(ValidationError, match=reason):
        decision(status, item)


def test_eligible_cannot_be_claimed_without_any_rules() -> None:
    with pytest.raises(ValidationError, match="satisfied rules only"):
        EligibilityDecision(
            status=EligibilityStatus.ELIGIBLE,
            reason_codes=[EligibilityReasonCode.RULE_SATISFIED.value],
            evidence=[evidence()],
            competition_id="competition-1",
            edition_id="edition-1",
        )


def test_decision_requires_reason_and_evidence() -> None:
    item = evaluation(EligibilityStatus.ELIGIBLE, EligibilityReasonCode.RULE_SATISFIED)
    with pytest.raises(ValidationError, match="reason code"):
        EligibilityDecision(
            status=EligibilityStatus.ELIGIBLE,
            reason_codes=[],
            evidence=item.evidence,
            competition_id="competition-1",
            edition_id="edition-1",
            rule_evaluations=[item],
        )
    with pytest.raises(ValidationError, match="evidence"):
        EligibilityDecision(
            status=EligibilityStatus.ELIGIBLE,
            reason_codes=[item.reason_code.value],
            evidence=[],
            competition_id="competition-1",
            edition_id="edition-1",
            rule_evaluations=[item],
        )


def test_decision_audit_rejects_mismatched_rule_reason_or_target() -> None:
    item = evaluation(EligibilityStatus.ELIGIBLE, EligibilityReasonCode.RULE_SATISFIED)
    with pytest.raises(ValidationError, match="reason is missing"):
        EligibilityDecision(
            status=EligibilityStatus.ELIGIBLE,
            reason_codes=[EligibilityReasonCode.RULE_VIOLATED.value],
            evidence=item.evidence,
            competition_id="competition-1",
            edition_id="edition-1",
            rule_evaluations=[item],
        )
    with pytest.raises(ValidationError, match="target does not match"):
        EligibilityDecision(
            status=EligibilityStatus.ELIGIBLE,
            reason_codes=[item.reason_code.value],
            evidence=item.evidence,
            competition_id="competition-1",
            edition_id="other-edition",
            rule_evaluations=[item],
        )


def test_eligible_decision_rejects_missing_data_reason() -> None:
    item = evaluation(EligibilityStatus.ELIGIBLE, EligibilityReasonCode.RULE_SATISFIED)
    with pytest.raises(ValidationError, match="satisfied rules only"):
        EligibilityDecision(
            status=EligibilityStatus.ELIGIBLE,
            reason_codes=[
                item.reason_code.value,
                EligibilityReasonCode.RULE_DATA_MISSING.value,
            ],
            evidence=item.evidence,
            competition_id="competition-1",
            edition_id="edition-1",
            rule_evaluations=[item],
        )


def test_verified_source_evidence_serializes_without_ingestion_artifacts() -> None:
    source = SourceMetadata(
        source_url="https://example.org/rules",
        source_type=SourceType.OFFICIAL,
        observed_at=datetime(2026, 10, 11, tzinfo=timezone.utc),
        verification_status=VerificationStatus.VERIFIED,
    )
    item = evaluation(EligibilityStatus.ELIGIBLE, EligibilityReasonCode.RULE_SATISFIED)
    item.evidence = [Evidence(code="official-rule", message="Official rule.", source=source)]
    result = decision(EligibilityStatus.ELIGIBLE, item)
    dump = result.model_dump(mode="json")
    assert dump["evidence"][0]["source"]["verification_status"] == "verified"
    assert EligibilityDecision.model_validate_json(result.model_dump_json()) == result
    assert not any(key in dump for key in ("raw_payload", "schema_version", "manifest"))
