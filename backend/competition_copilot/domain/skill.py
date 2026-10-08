from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Skill(BaseModel):
    """A standard skill independent of students and competitions."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)

    @field_validator("id", "name", "description")
    @classmethod
    def strip_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, aliases: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for alias in aliases:
            stripped = alias.strip()
            if not stripped:
                raise ValueError("aliases must not contain blank values")
            if stripped not in seen:
                seen.add(stripped)
                normalized.append(stripped)
        return normalized


class SkillLevel(str, Enum):
    UNKNOWN = "unknown"
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class StudentSkill(BaseModel):
    """A student's current state for one standard skill."""

    model_config = ConfigDict(extra="forbid")

    skill_id: str
    level: SkillLevel = SkillLevel.UNKNOWN
    self_assessed: bool = True
    note: str | None = None

    @field_validator("skill_id", "note")
    @classmethod
    def strip_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped
