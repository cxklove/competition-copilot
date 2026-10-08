from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from competition_copilot.domain.skill import StudentSkill


class EducationLevel(str, Enum):
    UNDERGRADUATE = "undergraduate"
    GRADUATE = "graduate"


class StudentProfile(BaseModel):
    """Student details explicitly provided for later competition decisions."""

    model_config = ConfigDict(extra="forbid")

    id: str
    education_level: EducationLevel | None = None
    grade: str | None = None
    school: str | None = None
    major: str | None = None
    interests: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    weekly_available_hours: float | None = Field(
        default=None, ge=0, le=168, allow_inf_nan=False
    )
    skills: list[StudentSkill] = Field(default_factory=list)

    @field_validator("id", "grade", "school", "major")
    @classmethod
    def strip_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("interests", "goals")
    @classmethod
    def normalize_strings(cls, values: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for value in values:
            stripped = value.strip()
            if not stripped:
                raise ValueError("must not contain blank values")
            if stripped not in seen:
                seen.add(stripped)
                normalized.append(stripped)
        return normalized

    @field_validator("skills")
    @classmethod
    def reject_duplicate_skill_ids(cls, skills: list[StudentSkill]) -> list[StudentSkill]:
        seen = set()
        for skill in skills:
            if skill.skill_id in seen:
                raise ValueError("skills must not contain duplicate skill_id values")
            seen.add(skill.skill_id)
        return skills
