from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pytest

from competition_copilot.domain.source_metadata import VerificationStatus
from competition_copilot.ingestion.approval import (
    CandidateReviewError,
    approve_candidate,
    approved_bundle,
    mark_duplicate,
    reject_candidate,
)
from competition_copilot.ingestion.candidate import (
    CandidateStatus,
    CompetitionCandidate,
    IssueSeverity,
    ValidationIssue,
)
from competition_copilot.ingestion.models import RawCompetitionData
from competition_copilot.ingestion.normalizer import CompetitionNormalizer
from competition_copilot.ingestion.validator import CompetitionCandidateValidator

CREATED_AT = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
REVIEWED_AT = datetime(2026, 10, 8, 21, 0, tzinfo=timezone(timedelta(hours=8)))


def pending_candidate() -> CompetitionCandidate:
    raw = RawCompetitionData(
        competition_id="example",
        name="Example Competition",
        edition_id="example-2026",
        edition_name="2026 Edition",
        edition_year="2026",
        tracks=["Innovation"],
        track_ids=["innovation"],
        source_url="https://example.org/notice",
        source_type="official",
        observed_at=CREATED_AT,
    )
    competition, edition, tracks = CompetitionNormalizer().normalize(raw)
    return CompetitionCandidate(
        id="candidate-1",
        raw_data=raw,
        competition=competition,
        edition=edition,
        tracks=tracks,
        created_at=CREATED_AT,
    )


def test_valid_approval_requires_explicit_action_and_creates_detached_bundle() -> None:
    candidate = pending_candidate()
    assert CompetitionCandidateValidator().validate(candidate) == []
    assert candidate.status is CandidateStatus.PENDING

    result = approve_candidate(
        candidate, reviewed_at=REVIEWED_AT, review_note="Checked notice manually"
    )
    bundle = approved_bundle(candidate)

    assert result is candidate
    assert candidate.status is CandidateStatus.APPROVED
    assert candidate.reviewed_at == REVIEWED_AT
    assert candidate.review_note == "Checked notice manually"
    assert bundle.competition.id == "example"
    assert bundle.edition.id == "example-2026"
    assert [track.id for track in bundle.tracks] == ["innovation"]
    assert bundle.edition.source is not None
    assert bundle.edition.source.verification_status is VerificationStatus.PENDING
    assert candidate.competition is not None
    candidate.competition.name = "Changed provisional name"
    assert bundle.competition.name == "Example Competition"


def test_approval_with_existing_error_is_rejected_without_state_change() -> None:
    candidate = pending_candidate()
    candidate.validation_issues.append(
        ValidationIssue(
            code="UNRESOLVED_CONFLICT",
            message="Sources conflict",
            severity=IssueSeverity.ERROR,
        )
    )

    with pytest.raises(CandidateReviewError) as error:
        approve_candidate(candidate, reviewed_at=REVIEWED_AT)

    assert error.value.code == "VALIDATION_ERRORS"
    assert [issue.code for issue in error.value.issues] == ["UNRESOLVED_CONFLICT"]
    assert candidate.status is CandidateStatus.PENDING
    assert candidate.reviewed_at is None


def test_approval_with_structural_error_is_rejected() -> None:
    candidate = pending_candidate()
    candidate.edition = None

    with pytest.raises(CandidateReviewError) as error:
        approve_candidate(candidate, reviewed_at=REVIEWED_AT)

    assert error.value.code == "VALIDATION_ERRORS"
    assert [issue.code for issue in error.value.issues] == ["MISSING_EDITION"]
    assert candidate.status is CandidateStatus.PENDING


def test_warning_does_not_block_explicit_approval() -> None:
    candidate = pending_candidate()
    candidate.validation_issues.append(
        ValidationIssue(
            code="CHECK_NAME",
            message="Name needs review",
            severity=IssueSeverity.WARNING,
        )
    )

    approve_candidate(candidate, reviewed_at=REVIEWED_AT)

    assert candidate.status is CandidateStatus.APPROVED
    assert candidate.validation_issues[0].severity is IssueSeverity.WARNING


def test_approval_requires_pending_and_repeated_approval_is_rejected() -> None:
    candidate = pending_candidate()
    reject_candidate(candidate, reviewed_at=REVIEWED_AT)

    with pytest.raises(CandidateReviewError) as error:
        approve_candidate(candidate, reviewed_at=REVIEWED_AT)
    assert error.value.code == "NOT_PENDING"
    assert candidate.status is CandidateStatus.REJECTED

    another = pending_candidate()
    approve_candidate(another, reviewed_at=REVIEWED_AT)
    with pytest.raises(CandidateReviewError) as repeated:
        approve_candidate(another, reviewed_at=REVIEWED_AT)
    assert repeated.value.code == "NOT_PENDING"
    assert another.status is CandidateStatus.APPROVED


def test_reject_records_explicit_review_information() -> None:
    candidate = pending_candidate()

    reject_candidate(candidate, reviewed_at=REVIEWED_AT, review_note="Source unclear")

    assert candidate.status is CandidateStatus.REJECTED
    assert candidate.reviewed_at == REVIEWED_AT
    assert candidate.review_note == "Source unclear"


def test_mark_duplicate_records_explicit_review_information() -> None:
    candidate = pending_candidate()

    mark_duplicate(candidate, reviewed_at=REVIEWED_AT, review_note="Same edition")

    assert candidate.status is CandidateStatus.DUPLICATE
    assert candidate.reviewed_at == REVIEWED_AT
    assert candidate.review_note == "Same edition"


@pytest.mark.parametrize(
    "action", [approve_candidate, reject_candidate, mark_duplicate]
)
def test_review_actions_reject_naive_reviewed_at(
    action: Callable[..., CompetitionCandidate],
) -> None:
    candidate = pending_candidate()

    with pytest.raises(CandidateReviewError) as error:
        action(candidate, reviewed_at=datetime(2026, 10, 8, 13, 0))

    assert error.value.code == "INVALID_REVIEWED_AT"
    assert candidate.status is CandidateStatus.PENDING
    assert candidate.reviewed_at is None


def test_approved_bundle_requires_approval() -> None:
    candidate = pending_candidate()

    with pytest.raises(CandidateReviewError) as error:
        approved_bundle(candidate)

    assert error.value.code == "NOT_APPROVED"


def test_approved_bundle_rejects_invalid_review_time() -> None:
    candidate = pending_candidate()
    approve_candidate(candidate, reviewed_at=REVIEWED_AT)
    candidate.reviewed_at = datetime(2026, 10, 8, 13, 0)

    with pytest.raises(CandidateReviewError) as error:
        approved_bundle(candidate)

    assert error.value.code == "INVALID_REVIEWED_AT"


def test_known_duplicate_id_blocks_approval() -> None:
    candidate = pending_candidate()

    with pytest.raises(CandidateReviewError) as error:
        approve_candidate(
            candidate,
            reviewed_at=REVIEWED_AT,
            known_competition_ids={"example"},
        )

    assert error.value.code == "VALIDATION_ERRORS"
    assert [issue.code for issue in error.value.issues] == [
        "DUPLICATE_COMPETITION_ID"
    ]
    assert candidate.status is CandidateStatus.PENDING


def test_candidate_status_change_is_deterministic_for_same_inputs() -> None:
    first = pending_candidate()
    second = pending_candidate()

    approve_candidate(first, reviewed_at=REVIEWED_AT, review_note="Checked")
    approve_candidate(second, reviewed_at=REVIEWED_AT, review_note="Checked")

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
