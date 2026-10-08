from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.temporal import TimeWindow


class Competition(BaseModel):
    """A competition identity shared across editions."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    short_name: str | None = None
    description: str | None = None
    official_url: HttpUrl | None = None

    @field_validator("id", "name", "short_name", "description")
    @classmethod
    def strip_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class CompetitionEdition(BaseModel):
    """A particular edition or season of a competition."""

    model_config = ConfigDict(extra="forbid")

    id: str
    competition_id: str
    year: int = Field(strict=True, ge=1900, le=2100)
    name: str
    registration_window: TimeWindow | None = None
    competition_window: TimeWindow | None = None
    official_url: HttpUrl | None = None
    source: SourceMetadata | None = None

    @field_validator("id", "competition_id", "name")
    @classmethod
    def strip_non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class CompetitionTrack(BaseModel):
    """A track within one competition edition."""

    model_config = ConfigDict(extra="forbid")

    id: str
    edition_id: str
    name: str
    description: str | None = None
    official_url: HttpUrl | None = None
    source: SourceMetadata | None = None

    @field_validator("id", "edition_id", "name", "description")
    @classmethod
    def strip_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped
