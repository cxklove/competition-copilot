"""Student-owned intent and result read storage contracts; no decision authority."""

import hashlib
import json
from typing import Literal, Protocol

from pydantic import AwareDatetime, Field, model_validator

from competition_copilot.domain.digital_twin import StableId
from competition_copilot.domain.eligibility import EligibilityDecision
from competition_copilot.domain.replanning import PlanReference
from competition_copilot.domain.skill_gap import SkillGapDecision
from competition_copilot.repositories.student import ProfileReference, ProfileValue

RelationshipState = Literal["SAVED", "PREPARING"]
DerivedResultKind = Literal["ELIGIBILITY", "SKILL_GAP", "PLAN_REFERENCE"]


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def content_digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class MyCompetitionTarget(ProfileValue):
    competition_id: StableId
    edition_id: StableId
    track_id: StableId | None = None


class StudentCompetitionRelationship(MyCompetitionTarget):
    relationship_id: StableId
    student_id: StableId
    state: RelationshipState
    version: int = Field(strict=True, ge=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime

    def target(self) -> MyCompetitionTarget:
        return MyCompetitionTarget(**{k: getattr(self, k) for k in MyCompetitionTarget.model_fields})


class RelationshipReference(ProfileValue):
    relationship_id: StableId
    student_id: StableId
    target: MyCompetitionTarget
    version: int = Field(strict=True, ge=1)
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    host_scope: StableId


class RelationshipSnapshot(ProfileValue):
    relationship: StudentCompetitionRelationship
    relationship_ref: RelationshipReference

    @model_validator(mode="after")
    def exact(self):
        r, ref = self.relationship, self.relationship_ref
        if (r.relationship_id, r.student_id, r.target(), r.version, content_digest(r.model_dump(mode="json"))) != (
                ref.relationship_id, ref.student_id, ref.target, ref.version, ref.content_digest):
            raise ValueError("Relationship reference mismatch")
        return self


class StudentCompetitionRepository(Protocol):
    def add(self, student_id: str, target: MyCompetitionTarget, state: RelationshipState,
            *, now: AwareDatetime) -> RelationshipSnapshot: ...
    def get_exact(self, student_id: str, target: MyCompetitionTarget) -> RelationshipSnapshot | None: ...
    def list_for_student(self, student_id: str) -> tuple[RelationshipSnapshot, ...]: ...
    def replace_state(self, expected: RelationshipReference, state: RelationshipState,
                      *, now: AwareDatetime) -> RelationshipSnapshot: ...
    def remove(self, expected: RelationshipReference) -> None: ...


class DerivedResultReference(ProfileValue):
    result_ref_id: StableId
    student_id: StableId
    target: MyCompetitionTarget
    kind: DerivedResultKind
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class RetainedDerivedResult(ProfileValue):
    reference: DerivedResultReference
    payload_json: str
    input_profile_ref: ProfileReference | None
    execution_sequence: int = Field(strict=True, ge=1)

    @model_validator(mode="after")
    def validate_binding(self):
        ref = self.reference
        model = {"ELIGIBILITY": EligibilityDecision, "SKILL_GAP": SkillGapDecision,
                 "PLAN_REFERENCE": PlanReference}[ref.kind]
        body = model.model_validate_json(self.payload_json)
        target = body.target if ref.kind != "ELIGIBILITY" else body
        if (target.competition_id, target.edition_id, target.track_id) != (
                ref.target.competition_id, ref.target.edition_id, ref.target.track_id):
            raise ValueError("Result target mismatch")
        if ref.kind == "PLAN_REFERENCE" and body.student_id != ref.student_id:
            raise ValueError("Plan student mismatch")
        if self.input_profile_ref and self.input_profile_ref.student_id != ref.student_id:
            raise ValueError("Result profile identity mismatch")
        if content_digest(body.model_dump(mode="json")) != ref.content_digest:
            raise ValueError("Result digest mismatch")
        return self


class DerivedResultReadStore(Protocol):
    def next_sequence(self) -> int: ...
    def retain_and_select(self, result: RetainedDerivedResult) -> None: ...
    def selected(self, student_id: str, target: MyCompetitionTarget,
                 kind: DerivedResultKind) -> DerivedResultReference | None: ...
    def resolve(self, reference: DerivedResultReference) -> RetainedDerivedResult | None: ...
