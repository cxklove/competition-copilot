"""Approved WHAT-to-change contracts; no Plan application or Diff computation."""

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from competition_copilot.domain.digital_twin import StableId
from competition_copilot.domain.plan import CompetitionPlan, PlanMilestone, PlanStatus
from competition_copilot.domain.replanning import (
    AffectedPlanScope,
    ImpactOutcome,
    PlanReference,
    ReplanningDecision,
    ReplanningOutcome,
    ReplanningReasonCode,
    ScopeState,
)


class _InputContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    @model_validator(mode="before")
    @classmethod
    def detach(cls, value: Any) -> Any:
        return value.model_dump() if isinstance(value, BaseModel) else value

    def model_copy(
        self, *, update: Mapping[str, Any] | None = None, deep: bool = False
    ) -> Self:
        if update is not None:
            raise TypeError("Construct a new validated replanning input")
        return super().model_copy(deep=deep)


def _canonical(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def _identity(prefix: str, value: BaseModel) -> str:
    payload = value.model_dump()
    for name in ("plan_status_instruction", "scope_resolution"):
        if name in payload and payload[name] is None:
            del payload[name]
    fields = TypeAdapter(Any).dump_python(_canonical(payload), mode="json")
    data = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return prefix + sha256(data.encode()).hexdigest()


def replanning_decision_fingerprint(decision: ReplanningDecision) -> str:
    """Approval binding to exact supplied Decision; not a new Decision identity."""
    return _identity("", ReplanningDecision.model_validate(decision))


class RevisionAuthority(_InputContract):
    """Declared trusted-caller approval references, not an approval workflow.

    No fictional deterministic rule is introduced. An external boundary must
    supply authentic approvals; this Domain contract never authenticates/fetches them.
    """

    kind: Literal["human_approved"]
    approval_ref: StableId
    approved_by_ref: StableId
    instruction_source_ref: StableId
    approved_at: AwareDatetime


class UpdateMilestoneInstruction(_InputContract):
    """First-version operation: explicit due_at only, same milestone identity.

    All other fields are supplied unchanged. No date arithmetic/content generation.
    Expected PlanReference binds identity, version, target and complete content.
    """

    operation: Literal["update_milestone"]
    source_decision_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_plan: PlanReference
    expected_before: PlanMilestone
    after: PlanMilestone
    authority: RevisionAuthority

    @property
    def id(self) -> str:
        return _identity("replanning-instruction-v1:", self)

    @property
    def target_milestone_id(self) -> str:
        return self.expected_before.id

    @model_validator(mode="after")
    def validate_explicit_update(self) -> Self:
        if self.expected_before.id != self.after.id:
            raise ValueError("Update must preserve milestone identity")
        if self.expected_before.id not in self.expected_plan.milestone_ids:
            raise ValueError("Instruction must reference an existing milestone")
        if any(
            getattr(self.expected_before, name) != getattr(self.after, name)
            for name in PlanMilestone.model_fields if name != "due_at"
        ):
            raise ValueError("First-version update permits only explicit due_at change")
        if self.expected_before.due_at == self.after.due_at:
            raise ValueError("Executable instruction requires an actual authorized change")
        if self.authority.approved_at < self.expected_plan.updated_at:
            raise ValueError("Approval cannot precede expected Plan context")
        return self


class ReplanningInputStatus(str, Enum):
    EXECUTABLE = "executable"
    PARTIALLY_EXECUTABLE = "partially_executable"
    UNRESOLVED = "unresolved"
    NO_REVISION_REQUIRED = "no_revision_required"


class UpdatePlanStatusInstruction(_InputContract):
    operation: Literal["update_plan_status"]
    source_decision_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_plan: PlanReference
    original_scope: AffectedPlanScope
    expected_before_status: PlanStatus
    desired_after_status: Literal[PlanStatus.CANCELLED]
    authority: RevisionAuthority

    @property
    def id(self) -> str:
        return _identity("replanning-instruction-v1:", self)

    @model_validator(mode="after")
    def allowed_transition(self) -> Self:
        if self.expected_before_status not in (PlanStatus.DRAFT, PlanStatus.ACTIVE):
            raise ValueError("Cancellation only permits draft/active; terminal/no-op transitions reject")
        if self.original_scope.plan_id != self.expected_plan.plan_id or not self.original_scope.whole_plan:
            raise ValueError("Cancellation instruction requires original whole-plan scope")
        if self.authority.approved_at < self.expected_plan.updated_at:
            raise ValueError("Approval cannot precede expected Plan")
        return self


class ScopeResolutionStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"


class AuthorizedScopeResolution(_InputContract):
    """Explicit coverage assertion; COMPLETE still needs batch semantic validation."""

    expected_plan: PlanReference
    source_decision_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    original_scope: AffectedPlanScope
    status: ScopeResolutionStatus
    coverage: Literal["cancel_target_removed_plan", "partial_milestone_revision", "unresolved"]
    executable_milestone_ids: tuple[StableId, ...] = ()
    instruction_ids: tuple[StableId, ...] = ()
    authority: RevisionAuthority

    @property
    def id(self) -> str:
        return _identity("scope-resolution-v1:", self)

    @property
    def has_unresolved_remainder(self) -> bool:
        return self.status != ScopeResolutionStatus.COMPLETE

    @field_validator("executable_milestone_ids", "instruction_ids")
    @classmethod
    def canonical_refs(cls, value: tuple[str, ...]) -> tuple:
        if len(set(value)) != len(value):
            raise ValueError("Duplicate resolution reference")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def coverage_shape(self) -> Self:
        if self.original_scope.plan_id != self.expected_plan.plan_id:
            raise ValueError("Resolution scope must bind expected Plan")
        if not set(self.executable_milestone_ids).issubset(self.expected_plan.milestone_ids):
            raise ValueError("Resolution contains unknown milestone")
        expected = {
            ScopeResolutionStatus.COMPLETE: "cancel_target_removed_plan",
            ScopeResolutionStatus.PARTIAL: "partial_milestone_revision",
            ScopeResolutionStatus.UNRESOLVED: "unresolved",
        }[self.status]
        if self.coverage != expected:
            raise ValueError("Coverage assertion must match resolution state")
        if self.status == ScopeResolutionStatus.COMPLETE:
            if not self.original_scope.whole_plan or self.executable_milestone_ids or len(self.instruction_ids) != 1:
                raise ValueError("Complete cancellation requires one explicit plan-level instruction")
        elif self.status == ScopeResolutionStatus.UNRESOLVED:
            if self.instruction_ids or self.executable_milestone_ids:
                raise ValueError("Unresolved resolution has no executable scope")
        elif not self.instruction_ids or not self.executable_milestone_ids:
            raise ValueError("Partial resolution must retain its approved known subset")
        return self


class ReplanningInput(_InputContract):
    """One atomic desired-after update batch, validated but never applied.

    WHERE is Decision.scope; WHAT is explicit instructions. One update per target.
    Partial means known operations are authorized, not a partial transaction.
    Whole-plan milestone edits remain partial. Only explicit compatible
    cancellation coverage can establish plan-level operational completeness.
    """

    before: CompetitionPlan
    decision: ReplanningDecision
    supplied_at: AwareDatetime
    status: ReplanningInputStatus
    instructions: tuple[UpdateMilestoneInstruction, ...] = ()
    plan_status_instruction: UpdatePlanStatusInstruction | None = None
    scope_resolution: AuthorizedScopeResolution | None = None

    @property
    def id(self) -> str:
        return _identity("replanning-input-v1:", self)

    @property
    def has_unresolved_remainder(self) -> bool:
        return self.status in (
            ReplanningInputStatus.PARTIALLY_EXECUTABLE, ReplanningInputStatus.UNRESOLVED,
        )

    @field_validator("instructions")
    @classmethod
    def canonical_instructions(cls, value: tuple[UpdateMilestoneInstruction, ...]) -> tuple:
        if len({item.target_milestone_id for item in value}) != len(value):
            raise ValueError("One atomic update per milestone; duplicate/conflicting targets reject")
        return tuple(sorted(value, key=lambda item: item.target_milestone_id))

    @model_validator(mode="after")
    def validate_authorized_batch(self) -> Self:
        reference = PlanReference.from_plan(self.before)
        if any(item.plan != reference for item in self.decision.impacts):
            raise ValueError("Decision must bind exact before Plan context")
        if self.supplied_at < self.decision.evaluated_at:
            raise ValueError("Input supply cannot precede Decision")
        resolution = self.scope_resolution
        fingerprint = replanning_decision_fingerprint(self.decision)
        if resolution is not None:
            if (resolution.expected_plan != reference
                or resolution.source_decision_fingerprint != fingerprint
                or resolution.original_scope != self.decision.scope):
                raise ValueError("Resolution must bind same Plan/version/Decision/original scope")
            if not self.decision.evaluated_at <= resolution.authority.approved_at <= self.supplied_at:
                raise ValueError("Resolution approval time must follow Decision and precede supply")
        status_instruction = self.plan_status_instruction
        outcome = self.decision.outcome
        if outcome == ReplanningOutcome.KEEP_CURRENT_PLAN:
            if self.instructions or status_instruction or resolution or self.status != ReplanningInputStatus.NO_REVISION_REQUIRED:
                raise ValueError("Keep permits only empty no-revision input")
            return self
        if outcome == ReplanningOutcome.UNDETERMINED:
            if self.instructions or status_instruction or self.status != ReplanningInputStatus.UNRESOLVED:
                raise ValueError("Undetermined permits unresolved input, not executable operations")
            if resolution is not None and resolution.status != ScopeResolutionStatus.UNRESOLVED:
                raise ValueError("Undetermined may only retain unresolved resolution")
            return self
        if status_instruction is not None:
            if self.instructions:
                raise ValueError("Cancellation batch cannot also modify historical milestones")
            if (resolution is None or resolution.status != ScopeResolutionStatus.COMPLETE
                or resolution.coverage != "cancel_target_removed_plan"):
                raise ValueError("Plan cancellation requires explicit COMPLETE coverage resolution")
            if (status_instruction.expected_plan != reference
                or status_instruction.source_decision_fingerprint != fingerprint
                or status_instruction.original_scope != self.decision.scope
                or status_instruction.expected_before_status != self.before.status):
                raise ValueError("Cancellation preconditions must bind exact Plan/status/scope/Decision")
            if (resolution.instruction_ids != (status_instruction.id,)
                or resolution.authority != status_instruction.authority):
                raise ValueError("Complete coverage must bind exact instruction and authority")
            impacts = self.decision.impacts
            confirmed = tuple(item for item in impacts if item.outcome == ImpactOutcome.AFFECTS_PLAN)
            # Normal impact constructors already verify typed removal evidence.
            # Do not reinterpret EventType/source changes here.
            if (not self.decision.scope.whole_plan or self.decision.scope.has_unresolved_remainder
                or any(item.outcome == ImpactOutcome.UNDETERMINED for item in impacts)
                or not confirmed
                or any(ReplanningReasonCode.TARGET_TRACK_REMOVED not in item.reason_codes for item in confirmed)):
                raise ValueError("Complete cancellation requires verified target removal only, no unresolved impact")
            if self.status != ReplanningInputStatus.EXECUTABLE:
                raise ValueError("Complete authorized cancellation must be EXECUTABLE")
            return self
        if not self.instructions:
            if self.status != ReplanningInputStatus.UNRESOLVED:
                raise ValueError("Replan without instructions remains unresolved")
            if resolution is not None and resolution.status != ScopeResolutionStatus.UNRESOLVED:
                raise ValueError("Missing instructions cannot assert resolved coverage")
            return self
        if resolution is not None:
            if (resolution.status != ScopeResolutionStatus.PARTIAL
                or set(resolution.instruction_ids) != {item.id for item in self.instructions}
                or set(resolution.executable_milestone_ids) != {item.target_milestone_id for item in self.instructions}
                or any(item.authority != resolution.authority for item in self.instructions)):
                raise ValueError("Milestone-only resolution must retain exact partial subset/authority; fake COMPLETE rejects")
        scope = self.decision.scope
        if scope.state == ScopeState.UNRESOLVED:
            raise ValueError("Pure unresolved scope cannot authorize an executable target")
        existing = {item.id: item for item in self.before.milestones}
        needs = {item.id for item in self.before.planning_needs}
        for instruction in self.instructions:
            if instruction.source_decision_fingerprint != replanning_decision_fingerprint(self.decision):
                raise ValueError("Instruction approval must bind this exact source Decision")
            if instruction.expected_plan != reference:
                raise ValueError("Instruction precondition must match exact Plan/version/content")
            mid = instruction.target_milestone_id
            if existing.get(mid) != instruction.expected_before:
                raise ValueError("Expected-before milestone must match current content")
            if not scope.whole_plan and mid not in scope.milestone_ids:
                raise ValueError("Instruction target is outside known affected references")
            approval = instruction.authority.approved_at
            if not self.decision.evaluated_at <= approval <= self.supplied_at:
                raise ValueError("Approval must bind Decision context and precede input supply")
            after = instruction.after
            if after.source_need_id is not None and after.source_need_id not in needs:
                raise ValueError("Instruction cannot introduce an unknown PlanningNeed")
            if not set(after.dependency_ids).issubset(existing):
                raise ValueError("Dependency reference must exist in unchanged milestone inventory")
            horizon = self.before.planning_horizon
            if horizon is not None:
                for instant in (after.start_at, after.due_at):
                    if instant is not None and (
                        (horizon.start_at is not None and instant < horizon.start_at)
                        or (horizon.end_at is not None and instant > horizon.end_at)
                    ):
                        raise ValueError("Explicit update must respect existing planning horizon")
        targeted = {item.target_milestone_id for item in self.instructions}
        # Whole-plan scope says WHERE, not that these explicit operations settle
        # every impact. Preserve that resolution limit even if all IDs are targeted.
        partial = (resolution is not None or scope.has_unresolved_remainder or scope.whole_plan
                   or targeted != set(scope.milestone_ids))
        expected = (ReplanningInputStatus.PARTIALLY_EXECUTABLE
                    if partial else ReplanningInputStatus.EXECUTABLE)
        if self.status != expected:
            raise ValueError("Input status must preserve missing coverage/unresolved remainder")
        return self
