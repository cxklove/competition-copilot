"""Explicit ingestion evidence for the timezone of structured clock times."""

from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, field_validator


class TemporalField(StrEnum):
    REGISTRATION_START = "registration_start"
    REGISTRATION_END = "registration_end"
    COMPETITION_START = "competition_start"
    COMPETITION_END = "competition_end"


class TimezoneBasis(StrEnum):
    SOURCE_EXPLICIT = "source_explicit"
    JURISDICTION_DEFAULT = "jurisdiction_default"


class TemporalPrecision(StrEnum):
    MINUTE = "minute"
    SECOND = "second"


class SeedTemporalProvenance(BaseModel):
    """Reviewed timezone interpretation retained with a structured Seed time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: TemporalField
    timezone_name: str
    timezone_basis: TimezoneBasis
    precision: TemporalPrecision

    @field_validator("timezone_name")
    @classmethod
    def require_iana_timezone(cls, value: str) -> str:
        if not value or not value.strip() or value != value.strip():
            raise ValueError("timezone_name must be a nonblank IANA timezone")
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone_name must be a valid IANA timezone") from exc
        return value


class TemporalProvenance(SeedTemporalProvenance):
    """Raw evidence; source_text is deliberately kept out of the Seed."""

    source_text: str

    @field_validator("source_text")
    @classmethod
    def require_source_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_text must not be blank")
        return value

    def for_seed(self) -> SeedTemporalProvenance:
        return SeedTemporalProvenance.model_validate(
            self.model_dump(exclude={"source_text"})
        )


def validate_timezone_offset(
    value: str | datetime, provenance: SeedTemporalProvenance
) -> None:
    """Require the recorded offset to describe the same local instant in the IANA zone."""

    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    except ValueError as exc:
        raise ValueError(f"{provenance.field} must be an aware ISO datetime") from exc
    if parsed.utcoffset() is None:
        raise ValueError(f"{provenance.field} must be timezone-aware")
    local = parsed.astimezone(ZoneInfo(provenance.timezone_name))
    if local.replace(tzinfo=None) != parsed.replace(tzinfo=None):
        raise ValueError(
            f"{provenance.field} offset is inconsistent with {provenance.timezone_name}"
        )
