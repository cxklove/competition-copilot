"""Read-only reviewed provenance; independent of ingestion and storage."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from competition_copilot.domain.source_metadata import SourceMetadata


class ReviewedTemporalProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    field: Literal["registration_start", "registration_end", "competition_start", "competition_end"]
    timezone_name: str
    timezone_basis: Literal["source_explicit", "jurisdiction_default"]
    precision: Literal["minute", "second"]


class CompetitionProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    competition_id: str
    edition_id: str
    track_id: str | None = None
    section: Literal["competition", "edition", "track", "time_windows"]
    source: SourceMetadata
    temporal: tuple[ReviewedTemporalProvenance, ...] = ()


class CompetitionProvenanceReader(Protocol):
    def read_provenance(
        self, competition_id: str, edition_id: str | None = None,
    ) -> tuple[CompetitionProvenance, ...]: ...
