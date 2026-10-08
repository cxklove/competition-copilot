"""Explicit in-memory human review actions for competition candidates."""

from collections.abc import Set
from datetime import datetime

from pydantic import BaseModel, ConfigDict

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
from competition_copilot.ingestion.validator import CompetitionCandidateValidator


class CandidateReviewError(ValueError):
    """A requested review action cannot be applied to this candidate."""

    def __init__(
        self, code: str, message: str, issues: list[ValidationIssue] | None = None
    ) -> None:
        self.code = code
        self.issues = issues or []
        super().__init__(message)


class ApprovedCompetitionBundle(BaseModel):
    """A detached output created only after explicit candidate approval."""

    model_config = ConfigDict(extra="forbid")

    competition: Competition
    edition: CompetitionEdition
    tracks: list[CompetitionTrack]


def _require_pending(candidate: CompetitionCandidate) -> None:
    if candidate.status is not CandidateStatus.PENDING:
        raise CandidateReviewError(
            "NOT_PENDING", "only pending candidates can be reviewed"
        )


def _require_reviewed_at(reviewed_at: datetime) -> None:
    if (
        not isinstance(reviewed_at, datetime)
        or reviewed_at.tzinfo is None
        or reviewed_at.utcoffset() is None
    ):
        raise CandidateReviewError(
            "INVALID_REVIEWED_AT", "reviewed_at must be timezone-aware"
        )


def _record_review(
    candidate: CompetitionCandidate,
    status: CandidateStatus,
    reviewed_at: datetime,
    review_note: str | None,
) -> CompetitionCandidate:
    candidate.reviewed_at = reviewed_at
    candidate.review_note = review_note
    candidate.status = status
    return candidate


def approve_candidate(
    candidate: CompetitionCandidate,
    *,
    reviewed_at: datetime,
    review_note: str | None = None,
    known_competition_ids: Set[str] = frozenset(),
    known_edition_ids: Set[str] = frozenset(),
) -> CompetitionCandidate:
    """Approve only an explicitly reviewed, structurally valid pending candidate."""

    _require_pending(candidate)
    _require_reviewed_at(reviewed_at)
    issues = CompetitionCandidateValidator().validate(
        candidate,
        known_competition_ids=known_competition_ids,
        known_edition_ids=known_edition_ids,
    )
    errors = [issue for issue in issues if issue.severity is IssueSeverity.ERROR]
    if errors:
        raise CandidateReviewError(
            "VALIDATION_ERRORS", "candidate has error-level validation issues", errors
        )
    return _record_review(candidate, CandidateStatus.APPROVED, reviewed_at, review_note)


def reject_candidate(
    candidate: CompetitionCandidate,
    *,
    reviewed_at: datetime,
    review_note: str | None = None,
) -> CompetitionCandidate:
    """Record an explicit human rejection of a pending candidate."""

    _require_pending(candidate)
    _require_reviewed_at(reviewed_at)
    return _record_review(candidate, CandidateStatus.REJECTED, reviewed_at, review_note)


def mark_duplicate(
    candidate: CompetitionCandidate,
    *,
    reviewed_at: datetime,
    review_note: str | None = None,
) -> CompetitionCandidate:
    """Record an explicit human duplicate decision for a pending candidate."""

    _require_pending(candidate)
    _require_reviewed_at(reviewed_at)
    return _record_review(candidate, CandidateStatus.DUPLICATE, reviewed_at, review_note)


def approved_bundle(candidate: CompetitionCandidate) -> ApprovedCompetitionBundle:
    """Return detached models from an approved candidate without storing them."""

    if candidate.status is not CandidateStatus.APPROVED or candidate.reviewed_at is None:
        raise CandidateReviewError(
            "NOT_APPROVED", "candidate must have an explicit approval record"
        )
    _require_reviewed_at(candidate.reviewed_at)
    issues = CompetitionCandidateValidator().validate(candidate)
    errors = [issue for issue in issues if issue.severity is IssueSeverity.ERROR]
    if errors:
        raise CandidateReviewError(
            "VALIDATION_ERRORS", "candidate has error-level validation issues", errors
        )
    assert candidate.competition is not None
    assert candidate.edition is not None
    return ApprovedCompetitionBundle(
        competition=candidate.competition.model_copy(deep=True),
        edition=candidate.edition.model_copy(deep=True),
        tracks=[track.model_copy(deep=True) for track in candidate.tracks],
    )
