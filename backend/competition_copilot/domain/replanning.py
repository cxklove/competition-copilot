"""P11 result contracts only: no impact evaluation, revision or Diff engine."""

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Literal, Self

from pydantic import (
    AnyUrl,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from competition_copilot.domain.digital_twin import (
    CompetitionTarget,
    ObservationState,
    StableId,
)
from competition_copilot.domain.event import (
    CompetitionEvent,
    CompetitionEventCategory,
    CompetitionEventType,
)
from competition_copilot.domain.plan import CompetitionPlan, PlanMilestone, PlanStatus


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    @model_validator(mode="before")
    @classmethod
    def detach(cls, value: Any) -> Any:
        return value.model_dump() if isinstance(value, BaseModel) else value

    def model_copy(
        self, *, update: Mapping[str, Any] | None = None, deep: bool = False
    ) -> Self:
        if update is not None:
            raise TypeError("Construct a new validated P11 result instead")
        return super().model_copy(deep=deep)


_URL_JSON = TypeAdapter(AnyUrl)


def _canonical(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, AnyUrl):
        # HttpUrl/AnyHttpUrl inherit AnyUrl. Serialize only this explicit typed
        # family; unknown objects still fail at the existing JSON boundary.
        return _URL_JSON.dump_python(value, mode="json")
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def _digest(value: Any) -> str:
    return sha256(json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()).hexdigest()


class PlanReference(_Contract):
    """Exact immutable P8 context reference, without student profile contents."""

    plan_id: StableId
    student_id: StableId
    target: CompetitionTarget
    version: int = Field(strict=True, ge=1)
    updated_at: AwareDatetime
    milestone_ids: tuple[StableId, ...] = ()
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("milestone_ids")
    @classmethod
    def canonical_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Duplicate milestone reference")
        return tuple(sorted(value))

    @classmethod
    def from_plan(cls, plan: CompetitionPlan) -> Self:
        """Projection/serialization only, not an impact or planning service."""
        plan = CompetitionPlan.model_validate(plan)
        return cls(
            plan_id=plan.id, student_id=plan.student_id, version=plan.version,
            updated_at=plan.updated_at,
            target=CompetitionTarget(
                competition_id=plan.competition_id, edition_id=plan.edition_id,
                track_id=plan.track_id,
            ),
            milestone_ids=tuple(item.id for item in plan.milestones),
            content_digest=_digest(plan.model_dump()),
        )


class ScopeState(str, Enum):
    KNOWN = "known"
    UNRESOLVED = "unresolved"
    PARTIALLY_RESOLVED = "partially_resolved"


class AffectedPlanScope(_Contract):
    plan_id: StableId
    state: ScopeState
    whole_plan: bool = False
    milestone_ids: tuple[StableId, ...] = ()

    @field_validator("milestone_ids")
    @classmethod
    def canonical_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return PlanReference.canonical_ids(value)

    @model_validator(mode="after")
    def unresolved_is_not_empty(self) -> Self:
        if self.state == ScopeState.UNRESOLVED and (self.whole_plan or self.milestone_ids):
            raise ValueError("Unresolved scope cannot assert affected elements")
        if self.state == ScopeState.PARTIALLY_RESOLVED and not (self.whole_plan or self.milestone_ids):
            raise ValueError("Partial scope needs known affected references and unresolved remainder")
        return self

    @property
    def has_unresolved_remainder(self) -> bool:
        """Derived from state; no second overlapping serialized uncertainty flag."""
        return self.state != ScopeState.KNOWN


class ImpactOutcome(str, Enum):
    AFFECTS_PLAN = "affects_plan"
    NO_PLAN_IMPACT = "no_plan_impact"
    UNDETERMINED = "undetermined"


class ReplanningOutcome(str, Enum):
    REPLAN = "replan"
    KEEP_CURRENT_PLAN = "keep_current_plan"
    UNDETERMINED = "undetermined"


class ReplanningReasonCode(str, Enum):
    TARGET_MISMATCH = "target_mismatch"
    RELEVANT_PLAN_TARGET = "relevant_plan_target"
    PLAN_DEPENDENCY_MATCHED = "plan_dependency_matched"
    PLAN_DEPENDENCY_NOT_REPRESENTED = "plan_dependency_not_represented"
    OBSERVATION_ONLY_EVENT = "observation_only_event"
    TARGET_TRACK_REMOVED = "target_track_removed"
    NO_RELEVANT_PLAN_ELEMENT = "no_relevant_plan_element"
    UNRELATED_TRACK_CHANGE = "unrelated_track_change"
    NO_PLAN_IMPACT = "no_plan_impact"
    STRUCTURAL_REVISION_SUPPORTED = "structural_revision_supported"
    REVISION_NOT_REPRESENTABLE = "revision_not_representable"
    IMPACT_UNDETERMINED = "impact_undetermined"
    CONFIRMED_PLAN_IMPACT = "confirmed_plan_impact"
    CONFIRMED_IMPACT_WITH_UNRESOLVED_REMAINDER = "confirmed_impact_with_unresolved_remainder"


class ReplanningEvidence(_Contract):
    """Structured references; full source lineage stays in the supplied Event."""

    event_id: StableId
    plan_id: StableId
    milestone_ids: tuple[StableId, ...] = ()
    source_change_fields: tuple[StableId, ...] = ()

    @field_validator("milestone_ids", "source_change_fields")
    @classmethod
    def unique_ordered(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Evidence references must be unique")
        return tuple(sorted(value))


class EventImpactAnalysis(_Contract):
    """Supplied outcome against exact Plan context; validators do not infer impact.

    Edition-level Event / track Plan and track Event / edition Plan share context,
    but relevance alone proves no dependency. Different explicit tracks are disjoint.
    Student context has no independent competition target: it binds plan.student_id.
    """

    event: CompetitionEvent
    plan: PlanReference
    student_id: StableId
    evaluated_at: AwareDatetime
    outcome: ImpactOutcome
    scope: AffectedPlanScope
    reason_codes: tuple[ReplanningReasonCode, ...] = Field(min_length=1)
    evidence: tuple[ReplanningEvidence, ...] = Field(min_length=1)

    @field_validator("reason_codes")
    @classmethod
    def canonical_reasons(cls, value: tuple[ReplanningReasonCode, ...]) -> tuple:
        if len(set(value)) != len(value):
            raise ValueError("Reason codes must be unique")
        return tuple(sorted(value, key=lambda code: code.value))

    @field_validator("evidence")
    @classmethod
    def canonical_evidence(cls, value: tuple[ReplanningEvidence, ...]) -> tuple:
        keys = [item.model_dump_json() for item in value]
        if len(set(keys)) != len(keys):
            raise ValueError("Evidence must be unique")
        return tuple(sorted(value, key=lambda item: item.model_dump_json()))

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        if self.event.source_diff is None:
            raise ValueError("P11 requires P10 Diff-backed Event lineage")
        if self.student_id != self.plan.student_id or self.scope.plan_id != self.plan.plan_id:
            raise ValueError("Student/scope must bind the supplied Plan")
        if self.evaluated_at < max(self.event.observed_at, self.plan.updated_at):
            raise ValueError("Evaluation cannot precede Event/Plan context")
        if not set(self.scope.milestone_ids).issubset(self.plan.milestone_ids):
            raise ValueError("Scope references unknown milestone")
        for item in self.evidence:
            if item.event_id != self.event.id or item.plan_id != self.plan.plan_id:
                raise ValueError("Evidence must bind exact Event and Plan")
            if not set(item.milestone_ids).issubset(self.plan.milestone_ids):
                raise ValueError("Evidence references unknown milestone")
            if not set(item.source_change_fields).issubset(self.event.source_change_fields):
                raise ValueError("Evidence field must come from Event lineage")
        event_target, plan_target = self.event.target, self.plan.target
        mismatch = (
            event_target.competition_id != plan_target.competition_id
            or event_target.edition_id != plan_target.edition_id
            or (event_target.track_id is not None and plan_target.track_id is not None
                and event_target.track_id != plan_target.track_id)
        )
        reasons = set(self.reason_codes)
        if reasons - {
            ReplanningReasonCode.TARGET_MISMATCH,
            ReplanningReasonCode.RELEVANT_PLAN_TARGET,
            ReplanningReasonCode.PLAN_DEPENDENCY_MATCHED,
            ReplanningReasonCode.PLAN_DEPENDENCY_NOT_REPRESENTED,
            ReplanningReasonCode.OBSERVATION_ONLY_EVENT,
            ReplanningReasonCode.TARGET_TRACK_REMOVED,
            ReplanningReasonCode.NO_RELEVANT_PLAN_ELEMENT,
            ReplanningReasonCode.UNRELATED_TRACK_CHANGE,
        }:
            raise ValueError("Impact reasons cannot assert a replanning decision")
        if mismatch != (ReplanningReasonCode.TARGET_MISMATCH in reasons):
            raise ValueError("Target mismatch reason must reflect target references")
        if mismatch and self.outcome != ImpactOutcome.NO_PLAN_IMPACT:
            raise ValueError("Disjoint targets cannot affect the Plan")

        # Verify supplied conclusions against existing typed lineage. These
        # predicates validate claims only; no outcome/result is generated here.
        track_changed = track_removed = track_preserved = False
        if self.event.event_type == CompetitionEventType.TRACK_MEMBERSHIP_CHANGED:
            membership = self.event.source_changes[0]
            track = plan_target.track_id
            before_tracks = membership.before.value or ()
            after_tracks = membership.after.value or ()
            if track is not None and not mismatch:
                track_changed = (track in before_tracks) != (track in after_tracks)
                track_removed = track in before_tracks and track not in after_tracks
                track_preserved = (
                    membership.before.state == ObservationState.KNOWN_VALUE
                    and membership.after.state == ObservationState.KNOWN_VALUE
                    and track in before_tracks and track in after_tracks
                )
        membership_evidence = any(
            "track_membership" in item.source_change_fields for item in self.evidence
        )
        negative_basis = mismatch or (track_preserved and membership_evidence)
        positive_basis = track_changed and membership_evidence
        positive_reasons = {
            ReplanningReasonCode.PLAN_DEPENDENCY_MATCHED,
            ReplanningReasonCode.TARGET_TRACK_REMOVED,
        }
        negative_reasons = {
            ReplanningReasonCode.TARGET_MISMATCH,
            ReplanningReasonCode.NO_RELEVANT_PLAN_ELEMENT,
            ReplanningReasonCode.UNRELATED_TRACK_CHANGE,
        }
        if reasons & positive_reasons and (
            not positive_basis or self.outcome != ImpactOutcome.AFFECTS_PLAN
        ):
            raise ValueError("Positive reason must match typed impact evidence and outcome")
        if ReplanningReasonCode.TARGET_TRACK_REMOVED in reasons and not track_removed:
            raise ValueError("Track removed reason must match factual lineage")
        if reasons & negative_reasons and (
            not negative_basis or self.outcome != ImpactOutcome.NO_PLAN_IMPACT
        ):
            raise ValueError("Negative reason requires verified negative basis and no-impact outcome")
        if ReplanningReasonCode.UNRELATED_TRACK_CHANGE in reasons and not (
            track_preserved and membership_evidence
        ):
            raise ValueError("Unrelated track reason requires known preserved target membership")
        if track_changed and self.outcome != ImpactOutcome.AFFECTS_PLAN:
            raise ValueError("Typed target membership change cannot be declared no-impact/uncertain")
        if negative_basis and self.outcome != ImpactOutcome.NO_PLAN_IMPACT:
            raise ValueError("Proven negative basis cannot be declared affected/uncertain")
        uncertain = {
            ReplanningReasonCode.PLAN_DEPENDENCY_NOT_REPRESENTED,
            ReplanningReasonCode.OBSERVATION_ONLY_EVENT,
        }
        if reasons & uncertain and self.outcome != ImpactOutcome.UNDETERMINED:
            raise ValueError("Missing dependency/observation uncertainty is not no impact")
        if (ReplanningReasonCode.OBSERVATION_ONLY_EVENT in reasons
            and self.event.category != CompetitionEventCategory.OBSERVATION_CHANGE):
            raise ValueError("Observation uncertainty reason requires observation Event")
        if self.outcome == ImpactOutcome.UNDETERMINED:
            if self.scope.state != ScopeState.UNRESOLVED or not reasons & uncertain:
                raise ValueError("Undetermined impact needs unresolved scope and evidence reason")
        elif self.outcome == ImpactOutcome.NO_PLAN_IMPACT and self.scope.state != ScopeState.KNOWN:
            raise ValueError("No impact requires fully known scope")
        elif self.outcome == ImpactOutcome.AFFECTS_PLAN and self.scope.state == ScopeState.UNRESOLVED:
            raise ValueError("Confirmed impact must retain known affected references")
        if self.outcome == ImpactOutcome.NO_PLAN_IMPACT:
            if self.scope.whole_plan or self.scope.milestone_ids:
                raise ValueError("No impact requires known-empty scope")
            if not negative_basis or not reasons & negative_reasons:
                raise ValueError("No impact requires structured negative evidence, not reason/scope alone")
        if self.outcome == ImpactOutcome.AFFECTS_PLAN:
            if not (self.scope.whole_plan or self.scope.milestone_ids):
                raise ValueError("Affected Plan requires determined nonempty scope")
            if not positive_basis or not reasons & positive_reasons:
                raise ValueError("Affected Plan requires supplied dependency evidence")
            if self.event.category == CompetitionEventCategory.OBSERVATION_CHANGE:
                raise ValueError("Coverage change alone cannot assert factual Plan impact")
            cited_milestones = {mid for item in self.evidence for mid in item.milestone_ids}
            if not set(self.scope.milestone_ids).issubset(cited_milestones):
                raise ValueError("Known affected milestones require explicit reference evidence")
        return self


class ReplanningDecision(_Contract):
    """Validate supplied action: confirmed > uncertain > proven no-impact.

    Multiple analyses and unresolved evidence stay intact. This Contract neither
    generates a decision nor promises that a Plan revision is representable.
    """

    impacts: tuple[EventImpactAnalysis, ...] = Field(min_length=1)
    evaluated_at: AwareDatetime
    outcome: ReplanningOutcome
    scope: AffectedPlanScope
    reason_codes: tuple[ReplanningReasonCode, ...] = Field(min_length=1)

    @field_validator("reason_codes")
    @classmethod
    def reasons(cls, value: tuple[ReplanningReasonCode, ...]) -> tuple:
        return EventImpactAnalysis.canonical_reasons(value)

    @field_validator("impacts")
    @classmethod
    def canonical_events(cls, value: tuple[EventImpactAnalysis, ...]) -> tuple:
        if len({item.event.id for item in value}) != len(value):
            raise ValueError("Duplicate trigger Event")
        return tuple(sorted(value, key=lambda item: item.event.id))

    @property
    def trigger_event_ids(self) -> tuple[str, ...]:
        return tuple(item.event.id for item in self.impacts)

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        reference = self.impacts[0].plan
        if any(item.plan != reference for item in self.impacts):
            raise ValueError("Decision must bind one exact Plan context")
        if self.evaluated_at < max(item.evaluated_at for item in self.impacts):
            raise ValueError("Decision cannot precede supplied analyses")
        if self.scope.plan_id != reference.plan_id:
            raise ValueError("Decision scope must bind Plan")
        if not set(self.scope.milestone_ids).issubset(reference.milestone_ids):
            raise ValueError("Decision scope references unknown milestone")
        outcomes = {item.outcome for item in self.impacts}
        reasons = set(self.reason_codes)
        if reasons - {
            ReplanningReasonCode.NO_PLAN_IMPACT,
            ReplanningReasonCode.STRUCTURAL_REVISION_SUPPORTED,
            ReplanningReasonCode.REVISION_NOT_REPRESENTABLE,
            ReplanningReasonCode.IMPACT_UNDETERMINED,
            ReplanningReasonCode.CONFIRMED_PLAN_IMPACT,
            ReplanningReasonCode.CONFIRMED_IMPACT_WITH_UNRESOLVED_REMAINDER,
        }:
            raise ValueError("Decision requires action reason codes")
        if self.outcome == ReplanningOutcome.KEEP_CURRENT_PLAN:
            if outcomes != {ImpactOutcome.NO_PLAN_IMPACT}:
                raise ValueError("Keep requires determined no-impact analyses")
            if self.scope.state != ScopeState.KNOWN or self.scope.whole_plan or self.scope.milestone_ids:
                raise ValueError("Keep requires known-empty scope")
            if reasons != {ReplanningReasonCode.NO_PLAN_IMPACT}:
                raise ValueError("Keep requires no-impact reason")
        elif self.outcome == ReplanningOutcome.REPLAN:
            if ImpactOutcome.AFFECTS_PLAN not in outcomes:
                raise ValueError("Replan requires at least one confirmed impact")
            confirmed = tuple(item for item in self.impacts if item.outcome == ImpactOutcome.AFFECTS_PLAN)
            unresolved = (ImpactOutcome.UNDETERMINED in outcomes
                          or any(item.scope.has_unresolved_remainder for item in confirmed))
            expected_ids = {mid for item in confirmed for mid in item.scope.milestone_ids}
            expected_whole = any(item.scope.whole_plan for item in confirmed)
            expected_state = ScopeState.PARTIALLY_RESOLVED if unresolved else ScopeState.KNOWN
            if (self.scope.state != expected_state
                or set(self.scope.milestone_ids) != expected_ids
                or self.scope.whole_plan != expected_whole):
                raise ValueError("Replan scope must preserve known references and all uncertainty")
            supported_reasons = {
                ReplanningReasonCode.STRUCTURAL_REVISION_SUPPORTED,
                ReplanningReasonCode.CONFIRMED_PLAN_IMPACT,
            }
            if unresolved:
                mixed = ReplanningReasonCode.CONFIRMED_IMPACT_WITH_UNRESOLVED_REMAINDER
                if mixed not in reasons or reasons - (supported_reasons | {mixed}):
                    raise ValueError("Mixed Replan needs explicit confirmed/unresolved reason")
            elif not reasons or reasons - supported_reasons:
                raise ValueError("Resolved Replan requires confirmed-impact reason")
        else:
            if ImpactOutcome.AFFECTS_PLAN in outcomes or ImpactOutcome.UNDETERMINED not in outcomes:
                raise ValueError("Undetermined requires uncertainty without confirmed impact")
            if self.scope.state != ScopeState.UNRESOLVED or not reasons or reasons - {
                ReplanningReasonCode.REVISION_NOT_REPRESENTABLE,
                ReplanningReasonCode.IMPACT_UNDETERMINED,
            }:
                raise ValueError("Undetermined decision requires unresolved scope/reason")
        return self


class PlanMilestonesChange(_Contract):
    """Supplied whole-collection structural change; preserves P8 milestone order."""

    field: Literal["milestones"] = "milestones"
    before: tuple[PlanMilestone, ...]
    after: tuple[PlanMilestone, ...]

    @model_validator(mode="after")
    def different_values(self) -> Self:
        if self.before == self.after:
            raise ValueError("Change must describe different milestone collections")
        return self


class PlanStatusChange(_Contract):
    """Controlled operational cancellation, not a general status machine."""

    field: Literal["status"] = "status"
    before_status: PlanStatus
    after_status: PlanStatus

    @model_validator(mode="after")
    def cancellation_only(self) -> Self:
        if self.before_status not in (PlanStatus.DRAFT, PlanStatus.ACTIVE) or self.after_status != PlanStatus.CANCELLED:
            raise ValueError("Only draft/active to cancelled is supported")
        return self


def revised_plan_identity(
    before: CompetitionPlan, milestones: tuple[PlanMilestone, ...],
    *, after_status: PlanStatus | None = None,
) -> str:
    """Contract identity only: never builds/revises a Plan or computes changes."""
    before = CompetitionPlan.model_validate(before)
    values = tuple(PlanMilestone.model_validate(item) for item in milestones)
    content = {
        "before": PlanReference.from_plan(before).model_dump(),
        "milestones": [item.model_dump() for item in values],
    }
    # Preserve existing milestone revision identities byte-for-byte.
    if after_status is not None and after_status != before.status:
        content["status"] = PlanStatus(after_status).value
    return "revised-plan-v1:" + _digest(content)


class PlanDiff(_Contract):
    """Auditable supplied before/after Plans, not a Diff computation engine.

    Structural scope is milestones or controlled target-removal cancellation.
    Target/student/needs/audit/horizon stay the same. Revised identity is
    lineage-sensitive; no-op reuses the exact old Plan, including metadata.
    """

    before: CompetitionPlan
    after: CompetitionPlan
    decision: ReplanningDecision
    evaluated_at: AwareDatetime
    changes: tuple[PlanMilestonesChange, ...] = Field(default=(), max_length=1)
    status_change: PlanStatusChange | None = None

    @property
    def before_plan_id(self) -> str:
        return self.before.id

    @property
    def after_plan_id(self) -> str:
        return self.after.id

    @property
    def trigger_event_ids(self) -> tuple[str, ...]:
        return self.decision.trigger_event_ids

    @model_validator(mode="after")
    def validate_audit(self) -> Self:
        if self.decision.impacts[0].plan != PlanReference.from_plan(self.before):
            raise ValueError("Decision must reference exact before Plan")
        if self.evaluated_at < self.decision.evaluated_at:
            raise ValueError("Diff evaluation cannot precede decision")
        if not self.changes and self.status_change is None:
            if self.before != self.after:
                raise ValueError("Empty Diff must reuse unchanged Plan")
            if self.decision.outcome == ReplanningOutcome.REPLAN:
                raise ValueError("Replan decision requires actual supplied structural change")
            return self
        if self.decision.outcome != ReplanningOutcome.REPLAN:
            raise ValueError("Changed Plan requires approved Replan decision")
        if self.changes:
            change = self.changes[0]
            if change.before != self.before.milestones or change.after != self.after.milestones:
                raise ValueError("Supplied change must match actual before/after milestones")
        elif self.before.milestones != self.after.milestones:
            raise ValueError("Actual milestone difference requires a collection change")
        if self.status_change is not None:
            if (self.status_change.before_status != self.before.status
                or self.status_change.after_status != self.after.status):
                raise ValueError("Status change must match actual before/after")
            if (not self.decision.scope.whole_plan or self.decision.scope.has_unresolved_remainder
                or any(item.outcome == ImpactOutcome.UNDETERMINED for item in self.decision.impacts)
                or any(ReplanningReasonCode.TARGET_TRACK_REMOVED not in item.reason_codes
                       for item in self.decision.impacts if item.outcome == ImpactOutcome.AFFECTS_PLAN)):
                raise ValueError("Cancellation requires verified target removal without unresolved impacts")
            if self.changes or self.before.milestones != self.after.milestones:
                raise ValueError("Cancellation preserves historical milestones")
        elif self.before.status != self.after.status:
            raise ValueError("Actual status difference requires typed status change")
        unchanged = set(CompetitionPlan.model_fields) - {"id", "version", "updated_at", "milestones", "status"}
        if any(getattr(self.before, name) != getattr(self.after, name) for name in unchanged):
            raise ValueError("Revision cannot change unsupported Plan fields")
        if self.after.version != self.before.version + 1 or self.after.updated_at < self.before.updated_at:
            raise ValueError("Revision requires next version and non-reversed update time")
        if not self.decision.evaluated_at <= self.after.updated_at <= self.evaluated_at:
            raise ValueError("Revision update time must follow decision and precede Diff evaluation")
        if self.after.id != revised_plan_identity(self.before, self.after.milestones, after_status=self.after.status):
            raise ValueError("Revised Plan ID must match deterministic lineage identity")
        if not self.decision.scope.whole_plan:
            scoped = set(self.decision.scope.milestone_ids)
            before = {item.id: item for item in self.before.milestones}
            after = {item.id: item for item in self.after.milestones}
            if any(before.get(mid) != after.get(mid) for mid in (before.keys() | after.keys()) - scoped):
                raise ValueError("Revision outside declared affected scope")
        return self
