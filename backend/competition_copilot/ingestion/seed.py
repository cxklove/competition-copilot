"""Auditable, static seed artifacts built from reviewed and verified facts."""

from typing import Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
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
from competition_copilot.ingestion.candidate import (
    CandidateStatus,
    CompetitionCandidate,
    IssueSeverity,
    ValidationIssue,
)
from competition_copilot.ingestion.temporal_provenance import (
    SeedTemporalProvenance,
    TemporalField,
    validate_timezone_offset,
)
from competition_copilot.ingestion.verification import (
    SourceVerificationRecord,
    VerifiedCompetitionBundle,
)


class SeedApprovalRecord(BaseModel):
    """Minimum human approval evidence retained without the raw candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    status: Literal[CandidateStatus.APPROVED]
    reviewed_at: AwareDatetime
    review_note: str

    @field_validator("candidate_id", "review_note")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class CompetitionSeedEnvelope(BaseModel):
    """Versioned verified facts and the two separate human audit records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0", "1.1"]
    artifact_type: Literal["verified_competition_seed"]
    raw_fixture_path: str
    approval: SeedApprovalRecord
    verification: SourceVerificationRecord
    validation_issues: list[ValidationIssue]
    competition: Competition
    competition_source: SourceMetadata
    edition: CompetitionEdition
    tracks: list[CompetitionTrack]
    temporal_provenance: list[SeedTemporalProvenance] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def require_versioned_temporal_field(cls, value: object) -> object:
        if isinstance(value, dict):
            if value.get("schema_version") == "1.0" and "temporal_provenance" in value:
                raise ValueError("Seed 1.0 cannot contain temporal_provenance")
            if value.get("schema_version") == "1.1" and "temporal_provenance" not in value:
                raise ValueError("Seed 1.1 requires temporal_provenance")
        return value

    @field_validator("raw_fixture_path")
    @classmethod
    def require_raw_fixture_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("raw_fixture_path must not be blank")
        if not value.startswith("data/raw/") or value == "data/raw/":
            raise ValueError("raw_fixture_path must refer to data/raw/")
        return value

    @model_validator(mode="after")
    def require_verified_consistent_facts(self) -> Self:
        if self.schema_version == "1.0" and self.temporal_provenance:
            raise ValueError("Seed 1.0 cannot contain temporal provenance")
        if self.approval.candidate_id != self.verification.candidate_id:
            raise ValueError("approval and verification candidate IDs differ")
        if self.verification.new_status is not VerificationStatus.VERIFIED:
            raise ValueError("verification must end in verified status")
        if self.competition_source.verification_status is not VerificationStatus.VERIFIED:
            raise ValueError("competition source must be verified")
        if self.verification.source_url != self.competition_source.source_url:
            raise ValueError("verification and competition source URLs differ")
        if self.edition.competition_id != self.competition.id:
            raise ValueError("edition competition ID differs from competition ID")
        if self.edition.source != self.competition_source:
            raise ValueError("edition source must match verified competition source")
        for track in self.tracks:
            if track.edition_id != self.edition.id:
                raise ValueError("track edition ID differs from edition ID")
            if track.source != self.competition_source:
                raise ValueError("track source must match verified competition source")
        if any(issue.severity is IssueSeverity.ERROR for issue in self.validation_issues):
            raise ValueError("verified seed cannot contain error-level validation issues")
        seen = set()
        for provenance in self.temporal_provenance:
            if provenance.field in seen:
                raise ValueError(f"duplicate temporal provenance field: {provenance.field}")
            seen.add(provenance.field)
            window_name = (
                "registration_window"
                if provenance.field in (
                    TemporalField.REGISTRATION_START,
                    TemporalField.REGISTRATION_END,
                )
                else "competition_window"
            )
            window = getattr(self.edition, window_name)
            endpoint = (
                "start_at"
                if provenance.field in (
                    TemporalField.REGISTRATION_START,
                    TemporalField.COMPETITION_START,
                )
                else "end_at"
            )
            value = getattr(window, endpoint) if window is not None else None
            if value is None:
                raise ValueError(f"{provenance.field} provenance requires a time value")
            validate_timezone_offset(value, provenance)
        return self


def build_seed_envelope(
    candidate: CompetitionCandidate,
    verified_bundle: VerifiedCompetitionBundle,
    validation_issues: list[ValidationIssue],
    raw_fixture_path: str,
) -> CompetitionSeedEnvelope:
    """Package already approved and verified facts; perform no workflow actions."""

    if candidate.status is not CandidateStatus.APPROVED:
        raise ValueError("candidate must be approved before seed creation")
    approval = SeedApprovalRecord(
        candidate_id=candidate.id,
        status=candidate.status,
        reviewed_at=candidate.reviewed_at,
        review_note=candidate.review_note,
    )
    bundle = verified_bundle.model_copy(deep=True)
    seed = CompetitionSeedEnvelope(
        schema_version="1.1",
        artifact_type="verified_competition_seed",
        raw_fixture_path=raw_fixture_path,
        approval=approval,
        verification=bundle.verification,
        validation_issues=[issue.model_copy(deep=True) for issue in validation_issues],
        competition=bundle.competition,
        competition_source=bundle.competition_source,
        edition=bundle.edition,
        tracks=bundle.tracks,
        temporal_provenance=[
            provenance.for_seed()
            for provenance in candidate.raw_data.temporal_provenance
        ],
    )
    if (
        candidate.competition != seed.competition
        or candidate.edition is None
        or candidate.edition.model_dump(exclude={"source"})
        != seed.edition.model_dump(exclude={"source"})
        or [track.model_dump(exclude={"source"}) for track in candidate.tracks]
        != [track.model_dump(exclude={"source"}) for track in seed.tracks]
    ):
        raise ValueError("verified bundle facts do not match the approved candidate")
    return seed


def serialize_seed(seed: CompetitionSeedEnvelope) -> bytes:
    """Return indented UTF-8 JSON without changing business array order."""

    excluded = {"temporal_provenance"} if seed.schema_version == "1.0" else None
    return seed.model_dump_json(indent=2, exclude=excluded).encode("utf-8")


def deserialize_seed(payload: bytes | str) -> CompetitionSeedEnvelope:
    """Load and validate the complete seed contract without reading Raw files."""

    return CompetitionSeedEnvelope.model_validate_json(payload)
