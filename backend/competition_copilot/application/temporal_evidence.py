"""Presentation-only temporal evidence. Never a structured time authority."""

from hashlib import sha256
from typing import Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from competition_copilot.domain.digital_twin import StableId
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    VerificationStatus,
)


class TemporalCandidateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    schema_version: Literal["1.0"] = "1.0"
    candidate_id: str = ""
    competition_id: StableId
    edition_id: StableId
    track_id: StableId | None = None
    field: Literal["registration", "competition", "registration_start", "registration_end",
                   "competition_start", "competition_end"]
    raw_text: str = Field(min_length=1)
    precision: Literal["DATETIME", "DATE", "MONTH", "TEXT_ONLY"]
    relation: Literal["RANGE", "BEFORE"] | None = None
    source: SourceMetadata
    verification_status: VerificationStatus = VerificationStatus.PENDING
    raw_reference: str = Field(pattern=r"^data/raw/[^/\\]+\.json$")
    raw_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    text_locator: str = Field(pattern=r"^/raw_payload/[A-Za-z_]+$")
    review_reference: StableId
    review_note: str = Field(min_length=1)

    @model_validator(mode="after")
    def content_identity(self) -> Self:
        if not self.raw_text.strip() or not self.review_note.strip():
            raise ValueError("Temporal evidence and review note must not be blank")
        payload = self.model_dump_json(exclude={"candidate_id"})
        expected = "temporal-candidate-v1:" + sha256(payload.encode()).hexdigest()
        if self.candidate_id and self.candidate_id != expected:
            raise ValueError("Temporal candidate content identity mismatch")
        object.__setattr__(self, "candidate_id", expected)
        return self

    def model_copy(self, *, update=None, deep=False):
        if update is not None:
            raise TypeError("Construct a validated temporal candidate")
        return super().model_copy(deep=deep)


class TemporalEvidenceProvider(Protocol):
    def read_candidates(self, competition_id: str, edition_id: str,
                        track_id: str | None = None) -> tuple[TemporalCandidateSnapshot, ...]: ...
