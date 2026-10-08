from datetime import datetime, timezone

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    SourceType,
    VerificationStatus,
)
from competition_copilot.ingestion.candidate import (
    CandidateStatus,
    CompetitionCandidate,
    IssueSeverity,
    ValidationIssue,
)
from competition_copilot.ingestion.models import RawCompetitionData
from competition_copilot.ingestion.validator import CompetitionCandidateValidator

OBSERVED_AT = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def valid_candidate() -> CompetitionCandidate:
    source = SourceMetadata(
        source_url="https://example.org/notice",
        source_type=SourceType.OFFICIAL,
        observed_at=OBSERVED_AT,
        verification_status=VerificationStatus.PENDING,
    )
    return CompetitionCandidate(
        id="candidate-1",
        raw_data=RawCompetitionData(
            source_url="https://example.org/notice",
            official_url="https://example.org/competition",
            observed_at=OBSERVED_AT,
        ),
        competition=Competition(
            id="example",
            name="Example Competition",
            official_url="https://example.org/competition",
        ),
        edition=CompetitionEdition(
            id="example-2026",
            competition_id="example",
            year=2026,
            name="2026 Edition",
            source=source,
        ),
        tracks=[
            CompetitionTrack(
                id="innovation", edition_id="example-2026", name="Innovation", source=source
            )
        ],
        created_at=OBSERVED_AT,
    )


def test_valid_candidate_has_no_issues_and_stays_pending() -> None:
    candidate = valid_candidate()

    assert CompetitionCandidateValidator().validate(candidate) == []
    assert candidate.status is CandidateStatus.PENDING
    assert candidate.validation_issues == []


def test_missing_competition_is_reported() -> None:
    candidate = valid_candidate()
    candidate.competition = None

    issues = CompetitionCandidateValidator().validate(candidate)

    assert [(issue.code, issue.field) for issue in issues] == [
        ("MISSING_COMPETITION", "competition")
    ]


def test_missing_edition_is_reported() -> None:
    candidate = valid_candidate()
    candidate.edition = None

    issues = CompetitionCandidateValidator().validate(candidate)

    assert [(issue.code, issue.field) for issue in issues] == [
        ("MISSING_EDITION", "edition")
    ]


def test_wrong_competition_id_is_reported() -> None:
    candidate = valid_candidate()
    assert candidate.edition is not None
    candidate.edition.competition_id = "other"

    issues = CompetitionCandidateValidator().validate(candidate)

    assert [(issue.code, issue.field) for issue in issues] == [
        ("COMPETITION_ID_MISMATCH", "edition.competition_id")
    ]


def test_wrong_track_edition_id_is_reported() -> None:
    candidate = valid_candidate()
    candidate.tracks[0].edition_id = "other-edition"

    issues = CompetitionCandidateValidator().validate(candidate)

    assert [(issue.code, issue.field) for issue in issues] == [
        ("TRACK_EDITION_ID_MISMATCH", "tracks[0].edition_id")
    ]


def test_missing_edition_and_track_source_are_reported() -> None:
    candidate = valid_candidate()
    assert candidate.edition is not None
    candidate.edition.source = None
    candidate.tracks[0].source = None

    issues = CompetitionCandidateValidator().validate(candidate)

    assert [(issue.code, issue.field) for issue in issues] == [
        ("MISSING_SOURCE_METADATA", "edition.source"),
        ("MISSING_SOURCE_METADATA", "tracks[0].source"),
    ]


def test_invalid_raw_urls_are_reported_without_network_access() -> None:
    candidate = valid_candidate()
    candidate.raw_data.source_url = "not a URL"
    candidate.raw_data.official_url = "ftp://example.org/competition"

    issues = CompetitionCandidateValidator().validate(candidate)

    assert [(issue.code, issue.field) for issue in issues] == [
        ("INVALID_URL", "raw_data.source_url"),
        ("INVALID_URL", "raw_data.official_url"),
    ]


def test_known_ids_are_reported_as_duplicates() -> None:
    candidate = valid_candidate()

    issues = CompetitionCandidateValidator().validate(
        candidate,
        known_competition_ids={"example"},
        known_edition_ids={"example-2026"},
    )

    assert [(issue.code, issue.field) for issue in issues] == [
        ("DUPLICATE_COMPETITION_ID", "competition.id"),
        ("DUPLICATE_EDITION_ID", "edition.id"),
    ]
    assert candidate.status is CandidateStatus.PENDING


def test_existing_warning_is_preserved_without_error() -> None:
    candidate = valid_candidate()
    warning = ValidationIssue(
        code="CHECK_NAME",
        message="Name needs review",
        field="competition.name",
        severity=IssueSeverity.WARNING,
    )
    candidate.validation_issues = [warning]

    issues = CompetitionCandidateValidator().validate(candidate)

    assert issues == [warning]
    assert all(issue.severity is not IssueSeverity.ERROR for issue in issues)
    assert candidate.status is CandidateStatus.PENDING


def test_existing_error_is_preserved_as_blocking_issue() -> None:
    candidate = valid_candidate()
    error = ValidationIssue(
        code="UNRESOLVED_CONFLICT",
        message="Sources conflict",
        severity=IssueSeverity.ERROR,
    )
    candidate.validation_issues = [error]

    issues = CompetitionCandidateValidator().validate(candidate)

    assert issues == [error]
    assert any(issue.severity is IssueSeverity.ERROR for issue in issues)
    assert candidate.status is CandidateStatus.PENDING


def test_repeated_validation_is_deterministic_and_does_not_mutate_candidate() -> None:
    candidate = valid_candidate()
    candidate.tracks[0].edition_id = "other-edition"
    before = candidate.model_dump(mode="json")
    validator = CompetitionCandidateValidator()

    first = validator.validate(candidate, known_competition_ids={"example"})
    second = validator.validate(candidate, known_competition_ids={"example"})

    assert first == second
    assert candidate.model_dump(mode="json") == before
    assert candidate.status is CandidateStatus.PENDING
