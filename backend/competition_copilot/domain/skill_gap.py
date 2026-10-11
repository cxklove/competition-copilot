"""Pure contracts for explicit skill requirements and auditable skill gaps.

REQUIRED means core task capability, never hard participation eligibility.
Models validate supplied conclusions; comparison and aggregation belong to P7.2.
No requirements are inferred from target names or descriptions.
"""

from collections.abc import Mapping
from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.skill import SkillLevel, StudentSkill
from competition_copilot.domain.source_metadata import VerificationStatus
from competition_copilot.domain.student import StudentProfile


class _SkillGapSnapshot(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always"
    )

    @model_validator(mode="before")
    @classmethod
    def detach_input(cls, value: Any) -> Any:
        return value.model_dump() if isinstance(value, BaseModel) else value

    def model_copy(
        self, *, update: Mapping[str, Any] | None = None, deep: bool = False
    ) -> Self:
        if update is not None:
            raise TypeError("Construct a new validated snapshot instead of updating a copy")
        return super().model_copy(deep=deep)


class _EvidenceSnapshot(Evidence, _SkillGapSnapshot):
    """Reuse shared evidence fields while protecting the P7 audit snapshot."""


class SkillFactRole(str, Enum):
    """Fact roles encoded explicitly in canonical Evidence.field namespaces."""

    REQUIREMENT = "requirement"
    STUDENT_SKILL = "student_skill"


def skill_fact_field(role: SkillFactRole, skill_id: str) -> str:
    """Single P7 convention for role and exact skill identity, without parsing.

    Requirement: requirements.<skill_id>.required_level
    Student: skills.<skill_id>.level
    Namespaces are disjoint even when skill IDs contain dots.
    """
    if not isinstance(skill_id, str) or not skill_id.strip():
        raise ValueError("skill fact requires a nonblank skill_id")
    prefix, suffix = {
        SkillFactRole.REQUIREMENT: ("requirements", "required_level"),
        SkillFactRole.STUDENT_SKILL: ("skills", "level"),
    }[role]
    return f"{prefix}.{skill_id.strip()}.{suffix}"


def skill_fact_value(level: SkillLevel) -> str:
    """Canonical serialized known proficiency; never str(Enum) or a display label."""
    if not isinstance(level, SkillLevel) or level is SkillLevel.UNKNOWN:
        raise ValueError("skill fact level must be a known SkillLevel")
    return level.value


def _validate_skill_fact(
    evidence: Evidence, role: SkillFactRole, skill_id: str, level: SkillLevel
) -> None:
    if evidence.field != skill_fact_field(role, skill_id):
        raise ValueError("evidence fact role or skill identity does not match")
    if evidence.value != skill_fact_value(level):
        raise ValueError("evidence fact value does not match declared level")


class _CompetitionSnapshot(Competition, _SkillGapSnapshot):
    pass


class _EditionSnapshot(CompetitionEdition, _SkillGapSnapshot):
    pass


class _TrackSnapshot(CompetitionTrack, _SkillGapSnapshot):
    pass


class _StudentSkillSnapshot(StudentSkill, _SkillGapSnapshot):
    pass


class _StudentProfileSnapshot(StudentProfile, _SkillGapSnapshot):
    interests: tuple[str, ...] = ()
    goals: tuple[str, ...] = ()
    skills: tuple[_StudentSkillSnapshot, ...] = ()

    @field_validator("interests", "goals", "skills")
    @classmethod
    def immutable_collections(cls, values: Any) -> tuple:
        return tuple(values)


class SkillRequirementScope(str, Enum):
    EDITION = "edition"
    TRACK = "track"


class SkillRequirementTarget(_SkillGapSnapshot):
    """An exact edition or track; no inheritance across targets."""

    competition_id: str = Field(strict=True, min_length=1)
    edition_id: str = Field(strict=True, min_length=1)
    track_id: str | None = Field(default=None, strict=True, min_length=1)
    scope: SkillRequirementScope

    @field_validator("competition_id", "edition_id", "track_id")
    @classmethod
    def nonblank_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("target ID must not be blank")
        return value

    @model_validator(mode="after")
    def check_scope(self) -> Self:
        if (self.scope is SkillRequirementScope.TRACK) != (self.track_id is not None):
            raise ValueError("scope must match presence of track_id")
        return self


class SkillRequirementType(str, Enum):
    REQUIRED = "required"
    DESIRED = "desired"


class SkillRequirementCoverage(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"


class SkillRequirement(_SkillGapSnapshot):
    """Structured skill fact; target/scope belongs to its requirement set.

    Skill identity references the existing Skill.id vocabulary. Required
    proficiency uses StudentSkill.level; UNKNOWN is not a known requirement.
    """

    skill_id: str = Field(strict=True, min_length=1)
    required_level: SkillLevel
    requirement_type: SkillRequirementType
    evidence: tuple[_EvidenceSnapshot, ...] = Field(min_length=1)

    @field_validator("skill_id")
    @classmethod
    def nonblank_skill(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("skill_id must not be blank")
        return value

    @model_validator(mode="after")
    def check_requirement(self) -> Self:
        if self.required_level is SkillLevel.UNKNOWN:
            raise ValueError("requirement level must be known")
        for fact in self.evidence:
            _validate_skill_fact(
                fact, SkillFactRole.REQUIREMENT, self.skill_id, self.required_level
            )
        if not any(
            e.source is not None
            and e.source.verification_status is VerificationStatus.VERIFIED
            for e in self.evidence
        ):
            raise ValueError("requirement needs verified source evidence")
        return self


class SkillRequirementSet(_SkillGapSnapshot):
    """Explicit coverage assessment, not inferred from item count or parsing.

    Empty sets represent MISSING only; no implicit 'no skill requirements'.
    A skill appears once per exact target, including across REQUIRED/DESIRED,
    avoiding ambiguous level/type precedence.
    """

    target: SkillRequirementTarget
    coverage: SkillRequirementCoverage
    coverage_note: str = Field(min_length=1)
    requirements: tuple[SkillRequirement, ...] = ()

    @field_validator("coverage_note")
    @classmethod
    def nonblank_note(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("coverage assessment must not be blank")
        return value

    @model_validator(mode="after")
    def check_requirements(self) -> Self:
        if (self.coverage is SkillRequirementCoverage.MISSING) != (not self.requirements):
            raise ValueError("empty requirements must explicitly have MISSING coverage")
        ids = [r.skill_id for r in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate skill requirement for exact target")
        return self


class SkillGapContext(_SkillGapSnapshot):
    student_profile: _StudentProfileSnapshot
    competition: _CompetitionSnapshot
    edition: _EditionSnapshot
    track: _TrackSnapshot | None = None
    requirements: SkillRequirementSet
    student_skill_evidence: tuple[_EvidenceSnapshot, ...] = ()

    @model_validator(mode="after")
    def check_target(self) -> Self:
        if self.edition.competition_id != self.competition.id:
            raise ValueError("edition must belong to competition")
        if self.track is not None and self.track.edition_id != self.edition.id:
            raise ValueError("track must belong to edition")
        target = self.requirements.target
        if (target.competition_id, target.edition_id, target.track_id) != (
            self.competition.id,
            self.edition.id,
            self.track.id if self.track is not None else None,
        ):
            raise ValueError("requirement target does not match context")
        return self

    @model_validator(mode="after")
    def check_student_evidence(self) -> Self:
        """Require supplied provenance for relevant known facts, never invent it."""
        skills_by_field = {
            skill_fact_field(SkillFactRole.STUDENT_SKILL, skill.skill_id): skill
            for skill in self.student_profile.skills
        }
        evidenced_ids = set()
        for fact in self.student_skill_evidence:
            skill = skills_by_field.get(fact.field)
            if skill is None:
                raise ValueError("student evidence must bind an existing STUDENT_SKILL fact")
            if skill.level is SkillLevel.UNKNOWN:
                raise ValueError("unknown student level must not carry known-level evidence")
            _validate_skill_fact(
                fact, SkillFactRole.STUDENT_SKILL, skill.skill_id, skill.level
            )
            evidenced_ids.add(skill.skill_id)
        relevant_ids = {r.skill_id for r in self.requirements.requirements}
        for skill in self.student_profile.skills:
            if (
                skill.skill_id in relevant_ids
                and skill.level is not SkillLevel.UNKNOWN
                and skill.skill_id not in evidenced_ids
            ):
                raise ValueError("known relevant student skill needs student evidence")
        return self


class SkillGapItemStatus(str, Enum):
    SATISFIED = "satisfied"
    GAP = "gap"
    UNKNOWN = "unknown"


class SkillGapStatus(str, Enum):
    NO_GAP = "no_gap"
    GAP_IDENTIFIED = "gap_identified"
    UNDETERMINED = "undetermined"


class SkillGapReasonCode(str, Enum):
    REQUIREMENT_SATISFIED = "REQUIREMENT_SATISFIED"
    SKILL_BELOW_REQUIREMENT = "SKILL_BELOW_REQUIREMENT"
    STUDENT_SKILL_DATA_MISSING = "STUDENT_SKILL_DATA_MISSING"
    REQUIREMENT_DATA_MISSING = "REQUIREMENT_DATA_MISSING"
    PARTIAL_REQUIREMENT_COVERAGE = "PARTIAL_REQUIREMENT_COVERAGE"


class SkillGapItem(_SkillGapSnapshot):
    """A supplied per-skill conclusion, with separate requirement/student audit.

    No numeric gap is defined for the ordinal SkillLevel scale. The compatibility
    table only rejects contradictory snapshots; it does not produce a result.
    """

    requirement: SkillRequirement
    student_level: SkillLevel | None = None
    status: SkillGapItemStatus
    reason_code: SkillGapReasonCode
    student_evidence: tuple[_EvidenceSnapshot, ...] = ()

    @model_validator(mode="after")
    def check_item(self) -> Self:
        expected = {
            SkillGapItemStatus.SATISFIED: SkillGapReasonCode.REQUIREMENT_SATISFIED,
            SkillGapItemStatus.GAP: SkillGapReasonCode.SKILL_BELOW_REQUIREMENT,
            SkillGapItemStatus.UNKNOWN: SkillGapReasonCode.STUDENT_SKILL_DATA_MISSING,
        }
        if self.reason_code is not expected[self.status]:
            raise ValueError("item reason conflicts with status")
        unavailable = self.student_level in (None, SkillLevel.UNKNOWN)
        if (self.status is SkillGapItemStatus.UNKNOWN) != unavailable:
            raise ValueError("unknown student skill must remain UNKNOWN")
        if unavailable and self.student_evidence:
            raise ValueError("unknown student level must not carry known-level evidence")
        if not unavailable:
            if not self.student_evidence:
                raise ValueError("known student level needs student evidence")
            for fact in self.student_evidence:
                _validate_skill_fact(
                    fact, SkillFactRole.STUDENT_SKILL,
                    self.requirement.skill_id, self.student_level,
                )
            satisfied_levels = {
                SkillLevel.BEGINNER: {
                    SkillLevel.BEGINNER, SkillLevel.INTERMEDIATE, SkillLevel.ADVANCED,
                },
                SkillLevel.INTERMEDIATE: {SkillLevel.INTERMEDIATE, SkillLevel.ADVANCED},
                SkillLevel.ADVANCED: {SkillLevel.ADVANCED},
            }
            satisfied = self.student_level in satisfied_levels[self.requirement.required_level]
            if (self.status is SkillGapItemStatus.SATISFIED) != satisfied:
                raise ValueError("item status conflicts with supplied proficiency levels")
        return self


class SkillGapDecision(_SkillGapSnapshot):
    """Gap existence and requirement coverage remain independent facts.

    NO_GAP confirms all declared skills (REQUIRED and DESIRED) are satisfied,
    with COMPLETE coverage. GAP_IDENTIFIED can retain PARTIAL coverage or unknown
    student facts for other skills. Validators reject contradictions only; an
    engine must later compute the supplied status and individual conclusions.
    """

    target: SkillRequirementTarget
    requirements: SkillRequirementSet
    gap_status: SkillGapStatus
    items: tuple[SkillGapItem, ...] = ()
    reason_codes: tuple[SkillGapReasonCode, ...] = Field(min_length=1)
    audit_evidence: tuple[_EvidenceSnapshot, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def check_decision(self) -> Self:
        if self.target != self.requirements.target:
            raise ValueError("decision target does not match requirements")
        facts = {r.skill_id: r for r in self.requirements.requirements}
        item_ids = [i.requirement.skill_id for i in self.items]
        if len(item_ids) != len(set(item_ids)) or set(item_ids) != set(facts):
            raise ValueError("items must cover each known requirement exactly once")
        for item in self.items:
            if item.requirement != facts[item.requirement.skill_id]:
                raise ValueError("gap item does not match structured requirement")
            if item.reason_code not in self.reason_codes:
                raise ValueError("item reason is missing from decision")
        coverage_reason = {
            SkillRequirementCoverage.MISSING: SkillGapReasonCode.REQUIREMENT_DATA_MISSING,
            SkillRequirementCoverage.PARTIAL: SkillGapReasonCode.PARTIAL_REQUIREMENT_COVERAGE,
        }.get(self.requirements.coverage)
        if coverage_reason is not None and coverage_reason not in self.reason_codes:
            raise ValueError("coverage reason is missing from decision")
        expected_reasons = {item.reason_code for item in self.items}
        if coverage_reason is not None:
            expected_reasons.add(coverage_reason)
        if (
            len(self.reason_codes) != len(set(self.reason_codes))
            or set(self.reason_codes) != expected_reasons
        ):
            raise ValueError("decision reasons must match item and coverage audit")
        if any(e.source is not None for e in self.audit_evidence):
            raise ValueError("system analysis audit must not impersonate source evidence")
        has_gap = any(i.status is SkillGapItemStatus.GAP for i in self.items)
        fully_satisfied = (
            self.requirements.coverage is SkillRequirementCoverage.COMPLETE
            and bool(self.items)
            and all(i.status is SkillGapItemStatus.SATISFIED for i in self.items)
        )
        if (self.gap_status is SkillGapStatus.GAP_IDENTIFIED) != has_gap:
            raise ValueError("GAP_IDENTIFIED requires an audited known skill gap")
        if (self.gap_status is SkillGapStatus.NO_GAP) != fully_satisfied:
            raise ValueError("NO_GAP requires complete known satisfied requirements")
        return self
