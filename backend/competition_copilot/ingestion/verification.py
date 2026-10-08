"""Explicit, auditable source verification after candidate approval."""

from datetime import datetime
from typing import Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    HttpUrl,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    VerificationStatus,
)
from competition_copilot.ingestion.approval import ApprovedCompetitionBundle
from competition_copilot.ingestion.candidate import (
    CandidateStatus,
    CompetitionCandidate,
)

_HTTP_URL = TypeAdapter(HttpUrl)


class SourceVerificationError(ValueError):
    """The explicit source verification action cannot be completed."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class SourceVerificationRecord(BaseModel):
    """Immutable evidence of one pending-to-verified source transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    verified_at: AwareDatetime
    verification_note: str
    previous_status: VerificationStatus
    new_status: VerificationStatus
    source_url: HttpUrl

    @field_validator("candidate_id", "verification_note")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def require_supported_transition(self) -> Self:
        if (
            self.previous_status is not VerificationStatus.PENDING
            or self.new_status is not VerificationStatus.VERIFIED
        ):
            raise ValueError("verification record must describe pending to verified")
        return self


class VerifiedCompetitionBundle(BaseModel):
    """Detached facts with explicit verified provenance and review evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    competition: Competition
    competition_source: SourceMetadata
    edition: CompetitionEdition
    tracks: list[CompetitionTrack]
    verification: SourceVerificationRecord


def _require_verification_inputs(
    verified_at: datetime, verification_note: str
) -> None:
    if (
        not isinstance(verified_at, datetime)
        or verified_at.tzinfo is None
        or verified_at.utcoffset() is None
    ):
        raise SourceVerificationError(
            "INVALID_VERIFIED_AT", "verified_at must be timezone-aware"
        )
    if not isinstance(verification_note, str) or not verification_note.strip():
        raise SourceVerificationError(
            "INVALID_VERIFICATION_NOTE", "verification_note must not be blank"
        )


def _require_pending_source(source: SourceMetadata) -> None:
    if source.verification_status is VerificationStatus.VERIFIED:
        raise SourceVerificationError(
            "ALREADY_VERIFIED", "source has already been verified"
        )
    if source.verification_status is not VerificationStatus.PENDING:
        raise SourceVerificationError(
            "INVALID_SOURCE_STATUS", "only pending sources can be verified"
        )


def verify_approved_bundle(
    candidate: CompetitionCandidate,
    bundle: ApprovedCompetitionBundle | VerifiedCompetitionBundle,
    *,
    verified_at: datetime,
    verification_note: str,
) -> VerifiedCompetitionBundle:
    """Verify one approved candidate's existing single-source provenance."""

    if candidate.status is not CandidateStatus.APPROVED:
        raise SourceVerificationError(
            "CANDIDATE_NOT_APPROVED", "candidate must be approved first"
        )
    if candidate.reviewed_at is None or candidate.reviewed_at.utcoffset() is None:
        raise SourceVerificationError(
            "MISSING_APPROVAL_RECORD", "candidate must have an approval time"
        )
    if isinstance(bundle, VerifiedCompetitionBundle):
        raise SourceVerificationError(
            "ALREADY_VERIFIED", "verified bundles cannot be verified again"
        )
    if not isinstance(bundle, ApprovedCompetitionBundle):
        raise SourceVerificationError("INVALID_BUNDLE", "approved bundle is required")
    _require_verification_inputs(verified_at, verification_note)

    if (
        candidate.competition != bundle.competition
        or candidate.edition != bundle.edition
        or candidate.tracks != bundle.tracks
    ):
        raise SourceVerificationError(
            "BUNDLE_MISMATCH", "bundle does not match the approved candidate"
        )

    source = bundle.edition.source
    if source is None:
        raise SourceVerificationError(
            "MISSING_SOURCE", "approved edition has no source metadata"
        )
    _require_pending_source(source)
    for track in bundle.tracks:
        if track.source is None:
            raise SourceVerificationError(
                "MISSING_SOURCE", "approved track has no source metadata"
            )
        _require_pending_source(track.source)
        if track.source != source:
            raise SourceVerificationError(
                "PROVENANCE_MISMATCH", "track source differs from edition source"
            )

    try:
        raw_source_url = _HTTP_URL.validate_python(
            candidate.raw_data.source_url.strip()
        )
    except ValidationError as exc:
        raise SourceVerificationError(
            "PROVENANCE_MISMATCH", "candidate raw source URL is invalid"
        ) from exc
    if (
        source.source_url != raw_source_url
        or candidate.raw_data.source_type is None
        or source.source_type.value != candidate.raw_data.source_type.strip()
        or source.observed_at.isoformat()
        != candidate.raw_data.observed_at.isoformat()
    ):
        raise SourceVerificationError(
            "PROVENANCE_MISMATCH", "source metadata differs from candidate raw data"
        )

    verified_source = SourceMetadata(
        source_url=source.source_url,
        source_type=source.source_type,
        observed_at=source.observed_at,
        verification_status=VerificationStatus.VERIFIED,
    )
    record = SourceVerificationRecord(
        candidate_id=candidate.id,
        verified_at=verified_at,
        verification_note=verification_note,
        previous_status=source.verification_status,
        new_status=verified_source.verification_status,
        source_url=source.source_url,
    )
    edition = bundle.edition.model_copy(deep=True)
    edition.source = verified_source
    tracks = [track.model_copy(deep=True) for track in bundle.tracks]
    for track in tracks:
        track.source = verified_source
    return VerifiedCompetitionBundle(
        competition=bundle.competition.model_copy(deep=True),
        competition_source=verified_source,
        edition=edition,
        tracks=tracks,
        verification=record,
    )
