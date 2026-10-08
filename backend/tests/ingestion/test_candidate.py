import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.ingestion.candidate import (
    CandidateStatus,
    CompetitionCandidate,
    IssueSeverity,
    ValidationIssue,
)
from competition_copilot.ingestion.models import RawCompetitionData

CREATED_AT = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def raw_data() -> RawCompetitionData:
    return RawCompetitionData(
        source_url="https://example.org/notice",
        observed_at=CREATED_AT,
        name="Example Competition",
        raw_payload={"original_name": "Example Competition"},
    )


def test_pending_candidate_allows_missing_parsed_data() -> None:
    candidate = CompetitionCandidate(
        id="candidate-1", raw_data=raw_data(), created_at=CREATED_AT
    )

    assert candidate.status is CandidateStatus.PENDING
    assert candidate.competition is None
    assert candidate.edition is None
    assert candidate.tracks == []
    assert candidate.validation_issues == []
    assert candidate.reviewed_at is None
    assert candidate.review_note is None
    assert candidate.raw_data.raw_payload == {
        "original_name": "Example Competition"
    }
    assert not isinstance(candidate, Competition)


def test_complete_candidate_stays_pending_without_review() -> None:
    candidate = CompetitionCandidate(
        id="candidate-1",
        raw_data=raw_data(),
        competition=Competition(id="example", name="Example Competition"),
        edition=CompetitionEdition(
            id="example-2026", competition_id="example", year=2026, name="2026"
        ),
        tracks=[
            CompetitionTrack(
                id="innovation", edition_id="example-2026", name="Innovation"
            )
        ],
        created_at=CREATED_AT,
    )

    assert candidate.competition is not None
    assert candidate.competition.id == "example"
    assert candidate.edition is not None
    assert candidate.edition.year == 2026
    assert len(candidate.tracks) == 1
    assert candidate.status is CandidateStatus.PENDING
    assert candidate.validation_issues == []


@pytest.mark.parametrize("status", list(CandidateStatus))
def test_all_candidate_statuses_are_representable(status: CandidateStatus) -> None:
    candidate = CompetitionCandidate(
        id="candidate-1", raw_data=raw_data(), status=status, created_at=CREATED_AT
    )

    assert candidate.status is status


def test_validation_issues_preserve_severity_and_optional_field() -> None:
    issues = [
        ValidationIssue(
            code="MISSING_DATE",
            message="Registration date is missing",
            field="registration_end",
            severity=IssueSeverity.ERROR,
        ),
        ValidationIssue(
            code="CHECK_NAME",
            message="Name needs review",
            severity=IssueSeverity.WARNING,
        ),
    ]
    candidate = CompetitionCandidate(
        id="candidate-1",
        raw_data=raw_data(),
        validation_issues=issues,
        created_at=CREATED_AT,
    )

    assert candidate.validation_issues == issues
    assert candidate.validation_issues[0].field == "registration_end"
    assert candidate.validation_issues[1].field is None
    assert candidate.status is CandidateStatus.PENDING


def test_invalid_issue_severity_is_rejected() -> None:
    with pytest.raises(ValidationError, match="severity"):
        ValidationIssue(code="CHECK_NAME", message="Review", severity="critical")


@pytest.mark.parametrize("candidate_id", ["", " \t "])
def test_blank_candidate_id_is_rejected(candidate_id: str) -> None:
    with pytest.raises(ValidationError, match="id"):
        CompetitionCandidate(
            id=candidate_id, raw_data=raw_data(), created_at=CREATED_AT
        )


def test_naive_created_at_is_rejected() -> None:
    with pytest.raises(ValidationError, match="created_at"):
        CompetitionCandidate(
            id="candidate-1",
            raw_data=raw_data(),
            created_at=datetime(2026, 10, 8, 12, 0),
        )


def test_naive_reviewed_at_is_rejected() -> None:
    with pytest.raises(ValidationError, match="reviewed_at"):
        CompetitionCandidate(
            id="candidate-1",
            raw_data=raw_data(),
            created_at=CREATED_AT,
            reviewed_at=datetime(2026, 10, 8, 13, 0),
        )


def test_timezone_aware_reviewed_at_is_accepted() -> None:
    reviewed_at = datetime(
        2026, 10, 8, 21, 0, tzinfo=timezone(timedelta(hours=8))
    )
    candidate = CompetitionCandidate(
        id="candidate-1",
        raw_data=raw_data(),
        created_at=CREATED_AT,
        reviewed_at=reviewed_at,
        review_note="Recorded for later review",
    )

    assert candidate.reviewed_at == reviewed_at
    assert candidate.reviewed_at.utcoffset() == timedelta(hours=8)
    assert candidate.review_note == "Recorded for later review"
    assert candidate.status is CandidateStatus.PENDING


def test_serialization_round_trip_preserves_provisional_data() -> None:
    original = CompetitionCandidate(
        id="candidate-1",
        raw_data=raw_data(),
        competition=Competition(id="example", name="Example Competition"),
        validation_issues=[
            ValidationIssue(
                code="CHECK_DATE",
                message="Date needs review",
                field="registration_end",
                severity=IssueSeverity.WARNING,
            )
        ],
        created_at=CREATED_AT,
        reviewed_at=datetime(2026, 10, 8, 13, 0, tzinfo=timezone.utc),
        review_note="Needs source confirmation",
    )

    payload = json.loads(original.model_dump_json())
    restored = CompetitionCandidate.model_validate(payload)

    assert payload["status"] == "pending"
    assert payload["validation_issues"][0]["severity"] == "warning"
    assert payload["raw_data"]["raw_payload"] == {
        "original_name": "Example Competition"
    }
    assert restored == original
