"""Host-memory relationship CAS and immutable selected result snapshots."""

from threading import RLock
from uuid import uuid4

from competition_copilot.repositories.student import ProfileError
from competition_copilot.repositories.student_competition import (
    DerivedResultReference,
    MyCompetitionTarget,
    RelationshipReference,
    RelationshipSnapshot,
    RetainedDerivedResult,
    StudentCompetitionRelationship,
    content_digest,
)


def _key(student_id, target):
    return student_id, target.competition_id, target.edition_id, target.track_id


class InMemoryStudentCompetitionRepository:
    def __init__(self):
        self.host_scope = "relationships-" + uuid4().hex
        self._lock = RLock()
        self._values = {}
        self._identity = 0

    def _snapshot(self, relationship):
        return RelationshipSnapshot(relationship=relationship, relationship_ref=RelationshipReference(
            relationship_id=relationship.relationship_id, student_id=relationship.student_id,
            target=relationship.target(), version=relationship.version, host_scope=self.host_scope,
            content_digest=content_digest(relationship.model_dump(mode="json"))))

    def add(self, student_id, target, state, *, now):
        target = MyCompetitionTarget.model_validate(target)
        with self._lock:
            key = _key(student_id, target)
            if key in self._values:
                raise ProfileError("MY_COMPETITION_ALREADY_EXISTS")
            self._identity += 1
            value = StudentCompetitionRelationship(**target.model_dump(),
                relationship_id=f"{self.host_scope}:{self._identity}", student_id=student_id,
                state=state, version=1, created_at=now, updated_at=now)
            snapshot = self._snapshot(value)
            self._values[key] = snapshot
            return snapshot

    def get_exact(self, student_id, target):
        with self._lock:
            return self._values.get(_key(student_id, target))

    def list_for_student(self, student_id):
        with self._lock:
            return tuple(sorted((s for k, s in self._values.items() if k[0] == student_id),
                key=lambda s: (s.relationship.state != "PREPARING", s.relationship.competition_id,
                    s.relationship.edition_id, s.relationship.track_id or "", s.relationship.relationship_id)))

    def _expected(self, expected):
        expected = RelationshipReference.model_validate(expected)
        current = self._values.get(_key(expected.student_id, expected.target))
        if current is None:
            raise ProfileError("MY_COMPETITION_NOT_FOUND")
        if current.relationship_ref != expected:
            raise ProfileError("MY_COMPETITION_VERSION_CONFLICT")
        return current

    def replace_state(self, expected, state, *, now):
        with self._lock:
            before = self._expected(expected).relationship
            value = StudentCompetitionRelationship(**{**before.model_dump(), "state": state,
                "version": before.version + 1, "updated_at": now})
            snapshot = self._snapshot(value)
            self._values[_key(value.student_id, value.target())] = snapshot
            return snapshot

    def remove(self, expected):
        with self._lock:
            value = self._expected(expected).relationship
            del self._values[_key(value.student_id, value.target())]


class InMemoryDerivedResultReadStore:
    def __init__(self):
        self._lock = RLock()
        self._sequence = 0
        self._bodies = {}
        self._selected = {}
        self._selection_sequences = {}

    def next_sequence(self):
        with self._lock:
            self._sequence += 1
            return self._sequence

    def retain_and_select(self, result):
        result = RetainedDerivedResult.model_validate_json(result.model_dump_json())
        with self._lock:
            ref = result.reference
            existing = self._bodies.get(ref.result_ref_id)
            if existing is not None and existing != result:
                raise ValueError("Result reference collision")
            key = (*_key(ref.student_id, ref.target), ref.kind)
            previous = self._selection_sequences.get(key, 0)
            if result.execution_sequence == previous and self._selected.get(key) != ref:
                raise ValueError("Conflicting selection sequence")
            self._bodies[ref.result_ref_id] = result
            if result.execution_sequence > previous:
                self._selected[key] = ref
                self._selection_sequences[key] = result.execution_sequence

    def selected(self, student_id, target, kind):
        with self._lock:
            return self._selected.get((*_key(student_id, target), kind))

    def resolve(self, reference):
        reference = DerivedResultReference.model_validate(reference)
        with self._lock:
            body = self._bodies.get(reference.result_ref_id)
            if body is not None and body.reference != reference:
                raise ProfileError("MY_COMPETITION_INVALID_REFERENCE")
            return body
