"""Read-side profile lineage. Stale is neither invalid nor a business decision."""

from collections.abc import Mapping
from typing import Literal

from pydantic import model_validator

from competition_copilot.application.profiles import (
    GetProfileQuery,
    ProfileActorBinding,
)
from competition_copilot.domain.digital_twin import StableId
from competition_copilot.domain.replanning import PlanReference
from competition_copilot.repositories.student import (
    ProfileError,
    ProfileInputBinding,
    ProfileReference,
    ProfileValue,
    StudentProfileRepository,
)


class ProfileFreshness(ProfileValue):
    status: Literal["CURRENT", "STALE", "UNKNOWN"]
    input_profile_ref: ProfileReference | None
    current_profile_ref: ProfileReference | None
    reason: Literal["EXACT_REFERENCE_MATCH", "PROFILE_REFERENCE_CHANGED",
        "RESULT_PROFILE_REFERENCE_UNKNOWN", "CURRENT_PROFILE_NOT_FOUND",
        "HOST_SCOPE_INCOMPARABLE", "RESULT_PROFILE_IDENTITY_MISMATCH"]

    @model_validator(mode="after")
    def validated_comparison(self):
        before, current = self.input_profile_ref, self.current_profile_ref
        if self.status != "UNKNOWN":
            if before is None or current is None or before.student_id != current.student_id or before.host_scope != current.host_scope:
                raise ValueError("Freshness requires comparable formal references")
            if (self.status == "CURRENT") != (before == current):
                raise ValueError("Freshness status must match exact reference equality")
            expected = "EXACT_REFERENCE_MATCH" if self.status == "CURRENT" else "PROFILE_REFERENCE_CHANGED"
            if self.reason != expected:
                raise ValueError("Freshness reason mismatch")
        elif self.reason in ("EXACT_REFERENCE_MATCH", "PROFILE_REFERENCE_CHANGED"):
            raise ValueError("Unknown freshness needs an uncertainty reason")
        return self


def resolve_profile_freshness(input_ref: ProfileReference | None,
                              current_ref: ProfileReference | None, *, student_id: str) -> ProfileFreshness:
    status = "UNKNOWN"
    if any(ref is not None and ref.student_id != student_id for ref in (input_ref, current_ref)):
        reason = "RESULT_PROFILE_IDENTITY_MISMATCH"
    elif input_ref is None:
        reason = "RESULT_PROFILE_REFERENCE_UNKNOWN"
    elif current_ref is None:
        reason = "CURRENT_PROFILE_NOT_FOUND"
    elif input_ref.host_scope != current_ref.host_scope:
        reason = "HOST_SCOPE_INCOMPARABLE"
    elif input_ref == current_ref:
        status, reason = "CURRENT", "EXACT_REFERENCE_MATCH"
    else:
        status, reason = "STALE", "PROFILE_REFERENCE_CHANGED"
    return ProfileFreshness(status=status, input_profile_ref=input_ref,
        current_profile_ref=current_ref, reason=reason)


class DerivedProfileBinding(ProfileInputBinding):
    kind: Literal["RecommendationRankingResult", "SkillGapDecision", "CompetitionPlan"]
    competition_id: StableId | None = None
    edition_id: StableId | None = None
    track_id: StableId | None = None
    plan_ref: PlanReference | None = None


class ProfileAnalysesQuery(GetProfileQuery):
    result_ref_ids: tuple[StableId, ...] = ()
    competition_id: StableId | None = None
    edition_id: StableId | None = None
    track_id: StableId | None = None
    plan_ref: PlanReference | None = None


class ProfileAnalysis(ProfileValue):
    result_ref_id: StableId
    binding: DerivedProfileBinding | None
    profile_freshness: ProfileFreshness


class ProfileAnalysesProjection(ProfileValue):
    student_id: StableId
    analyses: tuple[ProfileAnalysis, ...]


class ProfileAnalysesReader:
    def __init__(self, profiles: StudentProfileRepository, actor: ProfileActorBinding,
                 bindings: Mapping[str, DerivedProfileBinding]):
        self.profiles, self.actor, self.bindings = profiles, actor, bindings

    def read(self, query: ProfileAnalysesQuery) -> ProfileAnalysesProjection:
        if query.student_id not in self.actor.permitted_student_ids:
            raise ProfileError("PROFILE_EDIT_FORBIDDEN")
        profile = self.profiles.get(query.student_id)
        current = profile.profile_ref if profile else None
        entries = []
        for identity in dict.fromkeys(query.result_ref_ids):
            binding = self.bindings.get(identity)
            # Never disclose another student's input reference or call it stale.
            if binding and binding.input_profile_ref.student_id != query.student_id:
                continue
            if binding and binding.kind != "RecommendationRankingResult":
                if (binding.competition_id, binding.edition_id, binding.track_id) != (
                        query.competition_id, query.edition_id, query.track_id):
                    continue
                if binding.kind == "CompetitionPlan" and query.plan_ref is not None and binding.plan_ref != query.plan_ref:
                    continue
            entries.append(ProfileAnalysis(result_ref_id=identity, binding=binding,
                profile_freshness=resolve_profile_freshness(
                    binding.input_profile_ref if binding else None, current, student_id=query.student_id)))
        return ProfileAnalysesProjection(student_id=query.student_id, analyses=tuple(entries))
