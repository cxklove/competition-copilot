"""Unreviewed data read from an external competition source."""

from typing import Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from competition_copilot.ingestion.temporal_provenance import (
    TemporalProvenance,
    validate_timezone_offset,
)


class RawCompetitionData(BaseModel):
    """Preserve source values before normalization or human review."""

    model_config = ConfigDict(extra="forbid")

    competition_id: str | None = None
    name: str | None = None
    short_name: str | None = None
    edition_id: str | None = None
    edition_name: str | None = None
    edition_year: str | int | None = None
    official_url: str | None = None
    registration_start: str | None = None
    registration_end: str | None = None
    competition_start: str | None = None
    competition_end: str | None = None
    temporal_provenance: list[TemporalProvenance] = Field(default_factory=list)
    tracks: list[str] = Field(default_factory=list)
    track_ids: list[str] = Field(default_factory=list)
    source_url: str
    source_type: str | None = None
    observed_at: AwareDatetime
    raw_payload: dict[str, object] | None = None

    @field_validator("source_url")
    @classmethod
    def require_source_url(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_url must not be blank")
        return value

    @model_validator(mode="after")
    def require_temporal_provenance_consistency(self) -> Self:
        seen = set()
        for provenance in self.temporal_provenance:
            if provenance.field in seen:
                raise ValueError(f"duplicate temporal provenance field: {provenance.field}")
            seen.add(provenance.field)
            value = getattr(self, provenance.field.value)
            if value is None:
                raise ValueError(f"{provenance.field} provenance requires a time value")
            validate_timezone_offset(value, provenance)
        return self
