"""Host-scoped profile storage. Fixtures bootstrap once; edits never touch files."""

import secrets
from threading import RLock

from competition_copilot.repositories.student import (
    ProfileError,
    ProfileReference,
    StudentProfileProjection,
    StudentProfileRecord,
    StudentProfileSnapshot,
    profile_digest,
)


class InMemoryStudentProfileRepository:
    def __init__(self, profiles, *, created_at, evidence=None):
        self._scope = secrets.token_hex(24)
        self._lock = RLock()
        self._records = {}
        for profile in profiles:
            snapshot = StudentProfileSnapshot.model_validate(profile)
            if snapshot.id in self._records:
                raise ValueError("Duplicate bootstrap profile")
            self._records[snapshot.id] = StudentProfileRecord(
                profile=self._envelope(snapshot, 1, created_at, "fixture-bootstrap"),
                evidence=(evidence or {}).get(snapshot.id, ()))

    def _envelope(self, profile, version, updated_at, actor):
        return StudentProfileProjection(**profile.model_dump(), student_id=profile.id,
            profile_ref=ProfileReference(student_id=profile.id, version=version,
                content_digest=profile_digest(profile), host_scope=self._scope),
            updated_at=updated_at, updated_by=actor)

    def get_record(self, student_id):
        with self._lock:
            return self._records.get(student_id)

    def get(self, student_id):
        record = self.get_record(student_id)
        return record.profile if record else None

    def replace(self, profile, *, expected, updated_at, actor):
        return self._replace(profile, expected=expected, updated_at=updated_at, actor=actor)

    def replace_skill_state(self, profile, *, evidence, expected, updated_at, actor):
        return self._replace(profile, evidence=evidence, expected=expected,
                             updated_at=updated_at, actor=actor)

    def _replace(self, profile, *, expected, updated_at, actor, evidence=None):
        profile = StudentProfileSnapshot.model_validate(profile)
        with self._lock:
            current = self._records.get(profile.id)
            if current is None:
                raise ProfileError("PROFILE_NOT_FOUND")
            record = current
            current = record.profile
            if current.profile_ref != expected:
                raise ProfileError("PROFILE_VERSION_CONFLICT")
            if evidence is None and profile.skills != current.skills:
                raise ProfileError("SKILL_EVIDENCE_INCONSISTENT")
            if current.profile_ref.content_digest == profile_digest(profile):
                return current
            result = self._envelope(profile, current.profile_ref.version + 1, updated_at, actor)
            replacement = StudentProfileRecord(profile=result,
                evidence=record.evidence if evidence is None else evidence)
            self._records[profile.id] = replacement
            return result
