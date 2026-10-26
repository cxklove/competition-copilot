"""Versioned profile storage boundary; no competition decision authority."""

import hashlib
import json
from typing import Literal, Protocol

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.digital_twin import StableId
from competition_copilot.domain.skill import StudentSkill
from competition_copilot.domain.student import StudentProfile


class ProfileValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    @model_validator(mode="before")
    @classmethod
    def detach(cls, value):
        return value.model_dump() if isinstance(value, BaseModel) else value

    def model_copy(self, *, update=None, deep=False):
        if update is not None:
            raise TypeError("Construct a validated profile snapshot")
        return super().model_copy(deep=deep)


class StudentSkillSnapshot(StudentSkill, ProfileValue):
    pass


class StudentProfileSnapshot(StudentProfile, ProfileValue):
    interests: tuple[str, ...] = ()
    goals: tuple[str, ...] = ()
    skills: tuple[StudentSkillSnapshot, ...] = ()

    @field_validator("interests", "goals")
    @classmethod
    def normalize_strings(cls, values):
        return tuple(StudentProfile.normalize_strings(list(values)))

    @model_validator(mode="before")
    @classmethod
    def validate_domain(cls, value):
        raw = value.model_dump() if isinstance(value, BaseModel) else value
        return StudentProfile.model_validate(raw).model_dump()


def profile_digest(profile: StudentProfileSnapshot) -> str:
    content = json.dumps(profile.model_dump(mode="json"), sort_keys=True,
                         separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ProfileReference(ProfileValue):
    student_id: StableId
    version: int = Field(ge=1, strict=True)
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    host_scope: StableId


class StudentProfileProjection(StudentProfileSnapshot):
    profile_ref: ProfileReference
    student_id: StableId
    updated_at: AwareDatetime
    persistence_boundary: Literal["HOST_MEMORY"] = "HOST_MEMORY"
    updated_by: StableId

    # This projection includes envelope fields; validate only the Domain content.
    @model_validator(mode="before")
    @classmethod
    def validate_domain(cls, value):
        raw = value.model_dump() if isinstance(value, BaseModel) else dict(value)
        names = StudentProfile.model_fields
        profile = StudentProfile.model_validate({k: v for k, v in raw.items() if k in names})
        return {**raw, **profile.model_dump()}

    @model_validator(mode="after")
    def exact_reference(self):
        content = StudentProfileSnapshot.model_validate({
            key: getattr(self, key) for key in StudentProfile.model_fields})
        if (self.id != self.student_id or self.profile_ref.student_id != self.student_id
                or self.profile_ref.content_digest != profile_digest(content)):
            raise ValueError("Profile snapshot/reference mismatch")
        return self

    def domain_profile(self) -> StudentProfile:
        return StudentProfile.model_validate({
            key: getattr(self, key) for key in StudentProfile.model_fields})


class ProfileError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ProfileInputBinding(ProfileValue):
    result_ref_id: StableId
    input_profile_ref: ProfileReference
    plan_id: StableId | None = None
    plan_version: int | None = Field(default=None, ge=1)


class StudentEvidenceSnapshot(Evidence, ProfileValue):
    source: None = None


class StudentProfileRecord(ProfileValue):
    profile: StudentProfileProjection
    evidence: tuple[StudentEvidenceSnapshot, ...] = ()


class StudentProfileRepository(Protocol):
    def get_record(self, student_id: str) -> StudentProfileRecord | None: ...

    def replace_skill_state(self, profile: StudentProfileSnapshot, *, evidence: tuple,
                           expected: ProfileReference, updated_at: AwareDatetime,
                           actor: str) -> StudentProfileProjection: ...

    def get(self, student_id: str) -> StudentProfileProjection | None: ...

    def replace(self, profile: StudentProfileSnapshot, *, expected: ProfileReference,
                updated_at: AwareDatetime, actor: str) -> StudentProfileProjection: ...
