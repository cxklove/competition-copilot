"""Validate explicitly supplied local/profile evidence before P7 preparation.

No file access, inference, gap calculation or default evidence generation. The
existing Domain Evidence owns field/value. The input-only declaration binds the
student identity and self-assessment metadata absent from that shared contract.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.skill import SkillLevel
from competition_copilot.domain.skill_gap import (
    SkillFactRole,
    skill_fact_field,
    skill_fact_value,
)
from competition_copilot.domain.student import StudentProfile


class StudentSkillEvidenceDeclaration(BaseModel):
    """Explicit source declaration for a local fixture, not a public Agent API."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    student_id: str = Field(strict=True, min_length=1)
    skill_id: str = Field(strict=True, min_length=1)
    self_assessed: bool = Field(strict=True)
    evidence: Evidence

    @field_validator("student_id", "skill_id")
    @classmethod
    def nonblank_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Evidence identity must not be blank")
        return value


def prepare_student_skill_evidence(
    profile: StudentProfile,
    declarations: tuple[StudentSkillEvidenceDeclaration, ...],
) -> tuple[Evidence, ...]:
    """Forward only declared, matching facts; missing facts stay missing.

    P7's unchanged completeness validator remains responsible for requiring
    evidence for every relevant known skill. Messages explicitly retain the
    declaration's student/skill/self-assessment binding through the existing
    Evidence-only Domain boundary. No external provenance is asserted here.
    """
    skills = {skill.skill_id: skill for skill in profile.skills}
    prepared = []
    for supplied in declarations:
        declaration = StudentSkillEvidenceDeclaration.model_validate(supplied)
        fact = Evidence.model_validate(declaration.evidence.model_dump())
        if declaration.student_id != profile.id:
            raise ValueError("Student evidence identity mismatch")
        skill = skills.get(declaration.skill_id)
        if skill is None or skill.level is SkillLevel.UNKNOWN:
            raise ValueError("Student evidence requires an existing known skill record")
        if declaration.self_assessed != skill.self_assessed:
            raise ValueError("Student evidence self-assessment mismatch")
        if (fact.field != skill_fact_field(SkillFactRole.STUDENT_SKILL, skill.skill_id)
                or fact.value != skill_fact_value(skill.level)):
            raise ValueError("Student evidence skill fact mismatch")
        if fact.source is not None:
            raise ValueError("Local profile evidence must not assert external verification")
        if any(marker not in fact.message for marker in (
            f"student_id={profile.id};", f"skill_id={skill.skill_id};",
            f"self_assessed={str(skill.self_assessed).lower()};",
        )):
            raise ValueError("Student evidence message must retain explicit identity and self-assessment")
        prepared.append(fact)
    return tuple(prepared)
