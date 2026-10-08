from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from competition_copilot.domain.source_metadata import SourceMetadata


class ResourceType(str, Enum):
    ARTICLE = "article"
    COURSE = "course"
    VIDEO = "video"
    BOOK = "book"
    DOCUMENTATION = "documentation"
    REPOSITORY = "repository"
    OTHER = "other"


class LearningResource(BaseModel):
    """A learning resource and its explicitly assigned standard skill IDs."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    resource_type: ResourceType
    url: HttpUrl
    description: str | None = None
    skill_ids: list[str] = Field(default_factory=list)
    source: SourceMetadata | None = None

    @field_validator("id", "title", "description")
    @classmethod
    def strip_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("skill_ids")
    @classmethod
    def normalize_skill_ids(cls, skill_ids: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for skill_id in skill_ids:
            stripped = skill_id.strip()
            if not stripped:
                raise ValueError("skill_ids must not contain blank values")
            if stripped not in seen:
                seen.add(stripped)
                normalized.append(stripped)
        return normalized
