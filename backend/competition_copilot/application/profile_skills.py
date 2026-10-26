"""Catalog queries and authorized atomic skill self-report mutations. No decisions."""

from typing import Literal

from pydantic import field_validator, model_serializer, model_validator

from competition_copilot.application.profiles import (
    GetProfileQuery,
    ProfileMutationResult,
    StudentProfileEditor,
)
from competition_copilot.application.skill_requirements import SkillRequirementProvider
from competition_copilot.application.student_skill_evidence import (
    StudentSkillEvidenceDeclaration,
    prepare_student_skill_evidence,
)
from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.digital_twin import StableId
from competition_copilot.domain.skill import Skill, SkillLevel, StudentSkill
from competition_copilot.domain.skill_gap import (
    SkillFactRole,
    skill_fact_field,
    skill_fact_value,
)
from competition_copilot.domain.student import StudentProfile
from competition_copilot.repositories.student import (
    ProfileError,
    ProfileReference,
    ProfileValue,
    StudentProfileSnapshot,
)


class CatalogSkill(ProfileValue):
    skill_id: StableId
    name: str
    description: str | None = None
    aliases: tuple[str, ...] = ()


class SkillCatalogQuery(ProfileValue):
    pass


class SkillCatalogProjection(ProfileValue):
    skills: tuple[CatalogSkill, ...]


class SkillCatalogReader:
    def __init__(self, requirements: SkillRequirementProvider):
        self.requirements = requirements

    def read(self, query: SkillCatalogQuery) -> SkillCatalogProjection:
        skills = {}
        for artifact in self.requirements.list_artifacts():
            for definition in artifact.skills:
                skill = Skill.model_validate(definition.model_dump())
                snapshot = CatalogSkill(skill_id=skill.id, name=skill.name,
                    description=skill.description, aliases=tuple(skill.aliases))
                if skill.id in skills and skills[skill.id] != snapshot:
                    raise ProfileError("SKILL_CATALOG_CONFLICT")
                skills[skill.id] = snapshot
        return SkillCatalogProjection(skills=tuple(skills[key] for key in sorted(skills)))


class SkillCommand(ProfileValue):
    operation: Literal["add", "update", "remove"]
    expected_profile_ref: ProfileReference
    skill_id: StableId
    level: SkillLevel = SkillLevel.UNKNOWN
    note: str | None = None

    @model_validator(mode="after")
    def operation_fields(self):
        if self.operation == "remove" and self.model_fields_set.intersection(("level", "note")):
            raise ValueError("Remove accepts only skill identity and expected reference")
        return self

    @field_validator("note")
    @classmethod
    def valid_note(cls, value):
        return StudentSkill(skill_id="validation", note=value).note

    @model_serializer(mode="wrap")
    def supplied_fields(self, handler):
        return {k: v for k, v in handler(self).items() if k in self.model_fields_set}


class SkillMutationInput(GetProfileQuery):
    command: SkillCommand
    request_id: StableId


class StudentSkillEditor(StudentProfileEditor):
    def __init__(self, repository, actor, *, clock, catalog: SkillCatalogReader):
        super().__init__(repository, actor, clock=clock)
        self.catalog = catalog

    def mutate(self, invocation: SkillMutationInput) -> ProfileMutationResult:
        # Authorization is server-bound, never inferred from the student identity.
        self.read(GetProfileQuery(student_id=invocation.student_id))
        record = self.repository.get_record(invocation.student_id)
        if record is None:
            raise ProfileError("PROFILE_NOT_FOUND")
        current, command = record.profile, invocation.command
        if current.profile_ref != command.expected_profile_ref:
            raise ProfileError("PROFILE_VERSION_CONFLICT")
        skills = {s.skill_id: s for s in current.skills}
        old = skills.get(command.skill_id)
        if command.operation == "add":
            if old is not None:
                raise ProfileError("SKILL_ALREADY_EXISTS")
            if command.skill_id not in {s.skill_id for s in self.catalog.read(SkillCatalogQuery()).skills}:
                raise ProfileError("SKILL_NOT_IN_CATALOG")
            skills[command.skill_id] = StudentSkill(skill_id=command.skill_id,
                level=command.level, note=command.note, self_assessed=True)
        elif old is None:
            raise ProfileError("SKILL_NOT_FOUND")
        elif command.operation == "remove":
            del skills[command.skill_id]
        else:
            patch = {k: getattr(command, k) for k in ("level", "note")
                     if k in command.model_fields_set}
            skills[command.skill_id] = StudentSkill(**{**old.model_dump(), **patch})
        content = StudentProfileSnapshot.model_validate({
            **current.domain_profile().model_dump(), "skills": tuple(skills.values())})
        # Replace only this skill's fact. All other declared evidence is retained.
        field = skill_fact_field(SkillFactRole.STUDENT_SKILL, command.skill_id)
        facts = [fact for fact in record.evidence if fact.field != field]
        new_skill = skills.get(command.skill_id)
        if new_skill is not None and new_skill.level is not SkillLevel.UNKNOWN:
            facts.append(Evidence(code="STUDENT_SELF_REPORT", field=field, value=skill_fact_value(new_skill.level),
                message=f"User declaration: student_id={current.id}; skill_id={new_skill.skill_id}; "
                        f"self_assessed={str(new_skill.self_assessed).lower()};"))
        try:
            by_field = {skill_fact_field(SkillFactRole.STUDENT_SKILL, s.skill_id): s
                        for s in content.skills}
            declarations = tuple(StudentSkillEvidenceDeclaration(student_id=current.id,
                skill_id=by_field[fact.field].skill_id,
                self_assessed=by_field[fact.field].self_assessed, evidence=fact)
                for fact in facts)
            evidence = prepare_student_skill_evidence(StudentProfile.model_validate(
                content.model_dump()), declarations)
        except (ValueError, KeyError) as exc:
            raise ProfileError("SKILL_EVIDENCE_INCONSISTENT") from exc
        result = self.repository.replace_skill_state(content, evidence=evidence,
            expected=command.expected_profile_ref, updated_at=self.clock(), actor=self.actor.actor_id)
        return ProfileMutationResult(profile=result,
            changed_fields=("skills",) if result.profile_ref != current.profile_ref else (),
            request_id=invocation.request_id)
