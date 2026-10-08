import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.decision import DecisionResult, DecisionStatus, Evidence
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    SourceType,
    VerificationStatus,
)


def test_valid_minimal_evidence() -> None:
    evidence = Evidence(code="  rule-1  ", message="  Rule was checked.  ")

    assert evidence.code == "rule-1"
    assert evidence.message == "Rule was checked."
    assert evidence.source is None
    assert evidence.field is None
    assert evidence.value is None


def test_valid_complete_evidence() -> None:
    source = SourceMetadata(
        source_url="https://example.com/rules",
        source_type=SourceType.OFFICIAL,
        observed_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
        verification_status=VerificationStatus.VERIFIED,
    )
    evidence = Evidence(
        code="education-level",
        message="Graduate students are eligible.",
        source=source,
        field="  education_level  ",
        value="graduate",
    )

    assert evidence.code == "education-level"
    assert evidence.message == "Graduate students are eligible."
    assert evidence.source is source
    assert evidence.field == "education_level"
    assert evidence.value == "graduate"


def test_missing_code_is_rejected() -> None:
    with pytest.raises(ValidationError, match="code"):
        Evidence(message="Rule was checked.")


@pytest.mark.parametrize("code", ["", " \t\n "])
def test_empty_or_whitespace_code_is_rejected(code: str) -> None:
    with pytest.raises(ValidationError, match="code"):
        Evidence(code=code, message="Rule was checked.")


@pytest.mark.parametrize("message", ["", " \t\n "])
def test_empty_or_whitespace_message_is_rejected(message: str) -> None:
    with pytest.raises(ValidationError, match="message"):
        Evidence(code="rule-1", message=message)


def test_missing_message_is_rejected() -> None:
    with pytest.raises(ValidationError, match="message"):
        Evidence(code="rule-1")


def test_source_is_optional() -> None:
    assert Evidence(code="rule-1", message="Rule was checked.").source is None


def test_field_is_optional_and_trimmed() -> None:
    evidence = Evidence(code="rule-1", message="Rule was checked.", field="  grade  ")

    assert evidence.field == "grade"


@pytest.mark.parametrize("field", ["", " \t\n "])
def test_blank_field_is_rejected(field: str) -> None:
    with pytest.raises(ValidationError, match="field"):
        Evidence(code="rule-1", message="Rule was checked.", field=field)


@pytest.mark.parametrize(
    ("value", "expected_type"),
    [("10", str), (10, int), (10.5, float), (True, bool), (None, type(None))],
)
def test_value_preserves_simple_scalar_type(value: object, expected_type: type) -> None:
    evidence = Evidence.model_validate(
        {"code": "rule-1", "message": "Rule was checked.", "value": value}
    )

    assert evidence.value == value
    assert type(evidence.value) is expected_type


@pytest.mark.parametrize("value", [{"score": 10}, ["score", 10]])
def test_complex_value_is_rejected(value: object) -> None:
    with pytest.raises(ValidationError, match="value"):
        Evidence.model_validate(
            {"code": "rule-1", "message": "Rule was checked.", "value": value}
        )


def test_source_uses_source_metadata_validation() -> None:
    with pytest.raises(ValidationError, match="source"):
        Evidence.model_validate(
            {
                "code": "rule-1",
                "message": "Rule was checked.",
                "source": {"source_url": "ftp://example.com/rules"},
            }
        )


def test_serialization() -> None:
    evidence = Evidence(
        code="  weekly-hours  ",
        message="  Hours were provided.  ",
        field="  weekly_available_hours  ",
        value=10.5,
    )
    expected = {
        "code": "weekly-hours",
        "message": "Hours were provided.",
        "source": None,
        "field": "weekly_available_hours",
        "value": 10.5,
    }

    assert evidence.model_dump(mode="json") == expected
    assert json.loads(evidence.model_dump_json()) == expected


def test_model_validate_round_trip() -> None:
    original = Evidence(
        code="source-checked",
        message="The rule is from a verified source.",
        source=SourceMetadata(
            source_url="https://example.com/rules",
            source_type=SourceType.OFFICIAL,
            observed_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
            verification_status=VerificationStatus.VERIFIED,
        ),
        field="education_level",
        value=True,
    )

    restored = Evidence.model_validate(original.model_dump(mode="json"))

    assert restored == original
    assert isinstance(restored.source, SourceMetadata)
    assert type(restored.value) is bool


@pytest.mark.parametrize("status", list(DecisionStatus))
def test_decision_statuses_are_accepted(status: DecisionStatus) -> None:
    result = DecisionResult(status=status, reason_codes=["rule-1"])

    assert result.status is status


def test_invalid_decision_status_is_rejected() -> None:
    with pytest.raises(ValidationError, match="status"):
        DecisionResult.model_validate(
            {"status": "pending", "reason_codes": ["rule-1"]}
        )


def test_reason_codes_are_trimmed_deduplicated_and_ordered() -> None:
    result = DecisionResult(
        status=DecisionStatus.PASS,
        reason_codes=["  rule-1  ", "rule-2", "rule-1", "RULE-1"],
    )

    assert result.reason_codes == ["rule-1", "rule-2", "RULE-1"]


@pytest.mark.parametrize("reason_code", ["", " \t\n "])
def test_blank_reason_code_is_rejected(reason_code: str) -> None:
    with pytest.raises(ValidationError, match="reason_codes"):
        DecisionResult(
            status=DecisionStatus.FAIL,
            reason_codes=["rule-1", reason_code],
        )


def test_evidence_list_accepts_evidence_objects() -> None:
    evidence = Evidence(code="rule-1", message="Rule was checked.")
    result = DecisionResult(
        status=DecisionStatus.PASS,
        reason_codes=["rule-1"],
        evidence=[evidence],
    )

    assert result.evidence == [evidence]


def test_evidence_defaults_to_independent_empty_lists() -> None:
    first = DecisionResult(status=DecisionStatus.UNKNOWN, reason_codes=["missing-data"])
    second = DecisionResult(status=DecisionStatus.UNKNOWN, reason_codes=["missing-data"])

    assert first.evidence == []
    first.evidence.append(Evidence(code="missing-data", message="No value supplied."))
    assert second.evidence == []


def test_status_is_not_inferred_from_reasons_or_evidence() -> None:
    result = DecisionResult(
        status=DecisionStatus.UNKNOWN,
        reason_codes=["passed-rule"],
        evidence=[Evidence(code="passed-rule", message="A rule passed.")],
    )

    assert result.status is DecisionStatus.UNKNOWN
    assert DecisionResult(status=DecisionStatus.PASS, reason_codes=[]).status is (
        DecisionStatus.PASS
    )


def test_decision_result_serialization() -> None:
    result = DecisionResult(
        status=DecisionStatus.FAIL,
        reason_codes=["  missing-grade  ", "missing-grade"],
        evidence=[Evidence(code="grade", message="Grade was not provided.")],
    )
    expected = {
        "status": "fail",
        "reason_codes": ["missing-grade"],
        "evidence": [
            {
                "code": "grade",
                "message": "Grade was not provided.",
                "source": None,
                "field": None,
                "value": None,
            }
        ],
    }

    assert result.model_dump(mode="json") == expected
    assert json.loads(result.model_dump_json()) == expected


def test_decision_result_model_validate_round_trip() -> None:
    original = DecisionResult(
        status=DecisionStatus.UNKNOWN,
        reason_codes=["missing-grade"],
        evidence=[Evidence(code="grade", message="Grade was not provided.")],
    )

    restored = DecisionResult.model_validate(original.model_dump(mode="json"))

    assert restored == original
    assert restored.status is DecisionStatus.UNKNOWN
    assert isinstance(restored.evidence[0], Evidence)
