"""Reviewed P7 artifacts; reuse skill identities and exact requirement contracts."""

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from competition_copilot.domain.skill import Skill
from competition_copilot.domain.skill_gap import SkillRequirementSet, _SkillGapSnapshot
from competition_copilot.domain.source_metadata import SourceType, VerificationStatus


class _SkillSnapshot(Skill, _SkillGapSnapshot):
    """Immutable view of the existing Skill identity, not a new taxonomy."""

    aliases: tuple[str, ...] = ()

    @field_validator("aliases")
    @classmethod
    def immutable_aliases(cls, value: object) -> tuple[str, ...]:
        return tuple(value)


class SkillRequirementSetEnvelope(_SkillGapSnapshot):
    """One reviewed version per exact target. Coverage notes are system assessment.

    An embedded minimal Skill catalog resolves every requirement ID. Source-backed
    authoring/review must establish skill, type, level and coverage; schema
    validation cannot prove that an official text supports an interpretation.
    """

    schema_version: Literal["1.0"]
    artifact_type: Literal["skill_requirement_set"]
    requirement_version: str = Field(strict=True, min_length=1)
    review_note: str = Field(strict=True, min_length=1)
    requirement_set: SkillRequirementSet
    skills: tuple[_SkillSnapshot, ...]

    @field_validator("requirement_version", "review_note")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("artifact version/review note must not be blank")
        return value

    @model_validator(mode="after")
    def validate_catalog_and_provenance(self) -> Self:
        ids = [skill.id for skill in self.skills]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate Skill identity in artifact catalog")
        required_ids = {r.skill_id for r in self.requirement_set.requirements}
        if set(ids) != required_ids:
            raise ValueError("artifact Skill catalog must resolve exactly all requirement IDs")
        for requirement in self.requirement_set.requirements:
            for evidence in requirement.presence_evidence + requirement.evidence:
                if (
                    evidence.source is None
                    or evidence.source.source_type is not SourceType.OFFICIAL
                    or evidence.source.verification_status is not VerificationStatus.VERIFIED
                ):
                    raise ValueError("requirement artifact needs verified official fact evidence")
        return self
