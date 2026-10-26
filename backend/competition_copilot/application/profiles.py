"""Authorized profile read/edit use cases. No LLM, analysis or plan mutation."""

from pydantic import ValidationError, model_serializer, model_validator

from competition_copilot.domain.digital_twin import StableId
from competition_copilot.domain.student import EducationLevel, StudentProfile
from competition_copilot.repositories.student import (
    ProfileError,
    ProfileReference,
    ProfileValue,
    StudentProfileProjection,
    StudentProfileRepository,
    StudentProfileSnapshot,
)


class ProfilePatch(ProfileValue):
    education_level: EducationLevel | None = None
    grade: str | None = None
    school: str | None = None
    major: str | None = None
    interests: tuple[str, ...] = ()
    goals: tuple[str, ...] = ()
    weekly_available_hours: float | None = None

    @model_serializer(mode="wrap")
    def supplied_fields(self, handler):
        return {key: value for key, value in handler(self).items() if key in self.model_fields_set}

    @model_validator(mode="after")
    def domain_fields(self):
        StudentProfile(id="patch-validation", **self.model_dump(exclude_unset=True))
        return self


class ProfileUpdate(ProfileValue):
    expected_profile_ref: ProfileReference
    patch: ProfilePatch


class GetProfileQuery(ProfileValue):
    student_id: StableId


class UpdateProfileInput(GetProfileQuery):
    update: ProfileUpdate
    request_id: StableId


class ProfileMutationResult(ProfileValue):
    profile: StudentProfileProjection
    changed_fields: tuple[str, ...]
    request_id: StableId


class ProfileActorBinding(ProfileValue):
    actor_id: StableId
    permitted_student_ids: tuple[StableId, ...]


class StudentProfileReader:
    def __init__(self, repository: StudentProfileRepository, actor: ProfileActorBinding):
        self.repository, self.actor = repository, actor

    def read(self, query: GetProfileQuery) -> StudentProfileProjection:
        result = self.repository.get(query.student_id)
        if result is None:
            raise ProfileError("PROFILE_NOT_FOUND")
        if query.student_id not in self.actor.permitted_student_ids:
            raise ProfileError("PROFILE_EDIT_FORBIDDEN")
        return result


class StudentProfileEditor(StudentProfileReader):
    def __init__(self, repository: StudentProfileRepository, actor: ProfileActorBinding, *, clock):
        super().__init__(repository, actor)
        self.clock = clock

    def edit(self, command: UpdateProfileInput) -> ProfileMutationResult:
        current = self.read(GetProfileQuery(student_id=command.student_id))
        if current.profile_ref != command.update.expected_profile_ref:
            raise ProfileError("PROFILE_VERSION_CONFLICT")
        before = current.domain_profile().model_dump()
        patch = command.update.patch.model_dump(exclude_unset=True)
        try:
            content = StudentProfileSnapshot.model_validate({**before, **patch})
        except ValidationError as exc:
            raise ProfileError("INVALID_PROFILE_FIELD") from exc
        changed = tuple(sorted(key for key in patch
                               if before[key] != content.model_dump()[key]))
        result = self.repository.replace(content, expected=command.update.expected_profile_ref,
            actor=self.actor.actor_id, updated_at=self.clock())
        return ProfileMutationResult(profile=result, changed_fields=changed,
                                     request_id=command.request_id)
