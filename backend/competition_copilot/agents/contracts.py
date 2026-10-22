"""Interaction and audit envelopes, never a source of Domain business truth.

All IDs are caller-owned stable references; this package generates no identities.
Referenced artifacts must be resolved/verified by a later authorized boundary.
"""

from collections.abc import Mapping
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from competition_copilot.domain.digital_twin import StableId
from competition_copilot.domain.replanning import PlanReference
from competition_copilot.tools.contracts import ToolResult


class AgentContract(BaseModel):
    """Immutable values replaced through constructors, including future state."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    @model_validator(mode="before")
    @classmethod
    def detach(cls, value: Any) -> Any:
        return value.model_dump() if isinstance(value, BaseModel) else value

    @field_validator("*", mode="before")
    @classmethod
    def reject_unordered_input(cls, value: Any) -> Any:
        if isinstance(value, (set, frozenset)):
            raise ValueError("Use explicit JSON sequences, not sets")
        return value

    @field_validator("*", mode="after")
    @classmethod
    def normalize_time(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        return value

    def model_copy(
        self, *, update: Mapping[str, Any] | None = None, deep: bool = False
    ) -> Self:
        if update is not None:
            raise TypeError("Construct a new validated Agent contract instead")
        return super().model_copy(deep=deep)


class AgentIntent(StrEnum):
    DISCOVER_COMPETITIONS = "DISCOVER_COMPETITIONS"
    GET_COMPETITION_DETAILS = "GET_COMPETITION_DETAILS"
    CHECK_ELIGIBILITY = "CHECK_ELIGIBILITY"
    GET_RECOMMENDATIONS = "GET_RECOMMENDATIONS"
    ANALYZE_SKILL_GAP = "ANALYZE_SKILL_GAP"
    BUILD_PLAN = "BUILD_PLAN"
    CHECK_COMPETITION_CHANGES = "CHECK_COMPETITION_CHANGES"
    EXPLAIN_REPLANNING = "EXPLAIN_REPLANNING"
    REQUEST_PLAN_REVISION = "REQUEST_PLAN_REVISION"
    APPROVE_PLAN_REVISION = "APPROVE_PLAN_REVISION"
    REJECT_PLAN_REVISION = "REJECT_PLAN_REVISION"
    UNKNOWN = "UNKNOWN"


class WorkflowStatus(StrEnum):
    RECEIVED = "RECEIVED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    READY_TO_ROUTE = "READY_TO_ROUTE"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    READY_TO_EXECUTE = "READY_TO_EXECUTE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ReferenceKind(StrEnum):
    PROFILE = "PROFILE"
    CAPABILITY_ARGUMENTS = "CAPABILITY_ARGUMENTS"
    TOOL_RESULT = "TOOL_RESULT"
    ELIGIBILITY_RESULT = "ELIGIBILITY_RESULT"
    RECOMMENDATION_RESULT = "RECOMMENDATION_RESULT"
    SKILL_GAP_RESULT = "SKILL_GAP_RESULT"
    COMPETITION_RESULT = "COMPETITION_RESULT"
    EVENT = "EVENT"
    IMPACT_ANALYSIS = "IMPACT_ANALYSIS"
    REPLANNING_DECISION = "REPLANNING_DECISION"
    AFFECTED_SCOPE = "AFFECTED_SCOPE"
    SCOPE_RESOLUTION = "SCOPE_RESOLUTION"
    REPLANNING_INPUT = "REPLANNING_INPUT"
    REVISION_INSTRUCTION = "REVISION_INSTRUCTION"
    PLAN_DIFF = "PLAN_DIFF"
    EVIDENCE = "EVIDENCE"
    SOURCE = "SOURCE"
    AUTHORITY = "AUTHORITY"
    APPROVAL_REQUEST = "APPROVAL_REQUEST"
    APPROVAL_RESPONSE = "APPROVAL_RESPONSE"
    CLARIFICATION_RESPONSE = "CLARIFICATION_RESPONSE"


class ResultReference(AgentContract):
    """Reference to an existing artifact, not a duplicated Domain result.

    ref_id may be a producer's canonical fingerprint when it has no native ID.
    This contract validates shape, not artifact existence or factual truth.
    """

    kind: ReferenceKind
    ref_id: StableId


class ReasonReference(AgentContract):
    result: ResultReference
    reason_code: StableId


class AuditReferences(AgentContract):
    """Unordered reference sets with canonical JSON order; no evidence invention."""

    results: tuple[ResultReference, ...] = ()
    reasons: tuple[ReasonReference, ...] = ()

    @field_validator("results")
    @classmethod
    def order_results(cls, values: tuple[ResultReference, ...]):
        keys = [(item.kind.value, item.ref_id) for item in values]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate result reference")
        return tuple(sorted(values, key=lambda item: (item.kind.value, item.ref_id)))

    @field_validator("reasons")
    @classmethod
    def order_reasons(cls, values: tuple[ReasonReference, ...]):
        keys = [(r.result.kind.value, r.result.ref_id, r.reason_code) for r in values]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate reason reference")
        return tuple(sorted(values, key=lambda r: (
            r.result.kind.value, r.result.ref_id, r.reason_code
        )))

    @model_validator(mode="after")
    def bind_reasons(self) -> Self:
        if any(reason.result not in self.results for reason in self.reasons):
            raise ValueError("Reason must reference a retained result")
        return self


class AgentContext(AgentContract):
    student_id: StableId | None = None
    profile_ref: ResultReference | None = None
    competition_id: StableId | None = None
    edition_id: StableId | None = None
    track_id: StableId | None = None
    plan_ref: PlanReference | None = None

    @model_validator(mode="after")
    def consistent_context(self) -> Self:
        if self.profile_ref and self.profile_ref.kind != ReferenceKind.PROFILE:
            raise ValueError("profile_ref must be PROFILE")
        if self.edition_id and not self.competition_id:
            raise ValueError("edition_id requires competition_id")
        if self.track_id and not self.edition_id:
            raise ValueError("track_id requires edition_id")
        if self.plan_ref:
            pairs = (
                (self.student_id, self.plan_ref.student_id),
                (self.competition_id, self.plan_ref.target.competition_id),
                (self.edition_id, self.plan_ref.target.edition_id),
                (self.track_id, self.plan_ref.target.track_id),
            )
            if any(given is not None and given != actual for given, actual in pairs):
                raise ValueError("Context conflicts with exact Plan reference")
        return self


class AgentRequest(AgentContract):
    request_id: StableId
    user_message: StableId
    # User-selected operation only; never capability arguments or authorization.
    intent: AgentIntent | None = None
    conversation_id: StableId | None = None
    context: AgentContext = Field(default_factory=AgentContext)


class ContextField(StrEnum):
    INTENT = "INTENT"
    STUDENT_PROFILE = "STUDENT_PROFILE"
    COMPETITION = "COMPETITION"
    EDITION = "EDITION"
    TRACK = "TRACK"
    PLAN = "PLAN"
    APPROVAL_CONTEXT = "APPROVAL_CONTEXT"
    CAPABILITY_INVOCATION = "CAPABILITY_INVOCATION"
    CAPABILITY_ARGUMENTS = "CAPABILITY_ARGUMENTS"


class ClarificationReason(StrEnum):
    MISSING_REQUIRED_CONTEXT = "MISSING_REQUIRED_CONTEXT"
    AMBIGUOUS_INTENT = "AMBIGUOUS_INTENT"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
    MISSING_STUDENT_PROFILE = "MISSING_STUDENT_PROFILE"
    MISSING_APPROVAL_CONTEXT = "MISSING_APPROVAL_CONTEXT"


class ClarificationRequest(AgentContract):
    clarification_id: StableId
    source_request_id: StableId
    reason: ClarificationReason
    fields: tuple[ContextField, ...] = Field(min_length=1)
    question: StableId

    @field_validator("fields")
    @classmethod
    def unique_fields(cls, values: tuple[ContextField, ...]):
        if len(set(values)) != len(values):
            raise ValueError("Duplicate clarification field")
        return tuple(sorted(values, key=lambda value: value.value))


class ApprovalAction(StrEnum):
    PLAN_REVISION = "PLAN_REVISION"


class ApprovalRequest(AgentContract):
    """A proposal, never HUMAN_APPROVED authority or semantic coverage proof."""

    approval_request_id: StableId
    source_request_id: StableId
    invocation_id: StableId
    action: ApprovalAction
    summary: StableId
    before_plan: PlanReference
    proposed_after_plan: PlanReference | None = None
    decision_ref: ResultReference
    affected_scope_ref: ResultReference
    resolution_ref: ResultReference | None = None
    proposed_input_ref: ResultReference
    instruction_refs: tuple[ResultReference, ...] = Field(min_length=1)
    audit: AuditReferences
    created_at: AwareDatetime

    @model_validator(mode="after")
    def typed_proposal(self) -> Self:
        for ref, kind in (
            (self.decision_ref, ReferenceKind.REPLANNING_DECISION),
            (self.affected_scope_ref, ReferenceKind.AFFECTED_SCOPE),
            (self.resolution_ref, ReferenceKind.SCOPE_RESOLUTION),
            (self.proposed_input_ref, ReferenceKind.REPLANNING_INPUT),
        ):
            if ref is not None and ref.kind != kind:
                raise ValueError("Wrong approval artifact type")
        if any(r.kind != ReferenceKind.REVISION_INSTRUCTION
               for r in self.instruction_refs):
            raise ValueError("Approval scope must name revision instructions")
        if not self.audit.reasons or not any(
            r.kind == ReferenceKind.EVIDENCE for r in self.audit.results
        ):
            raise ValueError("Approval proposal requires reason and evidence references")
        if self.decision_ref not in self.audit.results or not any(
            r.result == self.decision_ref for r in self.audit.reasons
        ):
            raise ValueError("Approval reasons must bind its source decision")
        return self

    @field_validator("instruction_refs")
    @classmethod
    def canonical_instructions(cls, values: tuple[ResultReference, ...]):
        if len({r.ref_id for r in values}) != len(values):
            raise ValueError("Duplicate instruction reference")
        return tuple(sorted(values, key=lambda ref: ref.ref_id))


class ApprovalDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class ApprovalResponse(AgentContract):
    """Explicit caller submission; later authorized boundary verifies provenance."""

    approval_request_id: StableId
    source_request_id: StableId
    decision: ApprovalDecision
    submitted_at: AwareDatetime
    comment: StableId | None = None


class CapabilityId(StrEnum):
    """Existing capabilities, not an executable registry or routing policy."""

    LIST_COMPETITIONS = "list_competitions"
    GET_COMPETITION = "get_competition"
    GET_COMPETITION_DETAILS = "get_competition_details"
    LIST_EDITIONS = "list_competition_editions"
    GET_EDITION = "get_competition_edition"
    LIST_TRACKS = "list_edition_tracks"
    GET_TRACK = "get_competition_track"
    CHECK_ELIGIBILITY = "check_eligibility"
    GET_RECOMMENDATIONS = "get_recommendations"
    ANALYZE_SKILL_GAP = "analyze_skill_gap"
    BUILD_PLAN = "build_plan"
    CHECK_COMPETITION_CHANGES = "check_competition_changes"
    EXPLAIN_REPLANNING = "explain_replanning"
    REVISE_PLAN = "revise_plan"
    DIFF_COMPETITION_SNAPSHOT = "diff_competition_snapshot"
    BUILD_COMPETITION_SNAPSHOT = "build_competition_snapshot"
    DERIVE_COMPETITION_EVENTS = "derive_competition_events"
    ANALYZE_EVENT_IMPACT = "analyze_event_impact"
    DECIDE_REPLANNING = "decide_replanning"


class CapabilityInvocationRequest(AgentContract):
    """Proposal only; argument artifact is validated by future capability facade."""

    invocation_id: StableId
    source_request_id: StableId
    intent: AgentIntent
    capability: CapabilityId
    arguments_ref: ResultReference
    requires_approval: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def invocation_shape(self) -> Self:
        if self.intent == AgentIntent.UNKNOWN:
            raise ValueError("Unknown intent cannot propose an invocation")
        if self.arguments_ref.kind != ReferenceKind.CAPABILITY_ARGUMENTS:
            raise ValueError("Expected typed argument artifact reference")
        if self.capability == CapabilityId.REVISE_PLAN and not self.requires_approval:
            raise ValueError("Plan revision requires explicit approval")
        return self


class ToolResultReference(AgentContract):
    """Reuse P4 ToolResult for success/error; retain only the payload reference."""

    invocation_id: StableId
    result: ToolResult[ResultReference]


class AgentErrorCode(StrEnum):
    UNSUPPORTED_INTENT = "UNSUPPORTED_INTENT"
    MISSING_CONTEXT = "MISSING_CONTEXT"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    INVALID_WORKFLOW_TRANSITION = "INVALID_WORKFLOW_TRANSITION"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    SERIALIZATION_ERROR = "SERIALIZATION_ERROR"
    CAPABILITY_EXECUTION_FAILED = "CAPABILITY_EXECUTION_FAILED"


class AgentError(AgentContract):
    code: AgentErrorCode
    message: StableId


class AgentResponse(AgentContract):
    request_id: StableId
    intent: AgentIntent
    outcome: WorkflowStatus
    message: StableId
    clarification: ClarificationRequest | None = None
    approval_request: ApprovalRequest | None = None
    audit: AuditReferences = Field(default_factory=AuditReferences)
    plan_refs: tuple[PlanReference, ...] = ()
    error: AgentError | None = None

    @field_validator("plan_refs")
    @classmethod
    def canonical_plans(cls, values: tuple[PlanReference, ...]):
        keys = [(p.plan_id, p.version, p.content_digest) for p in values]
        if len(set(keys)) != len(values):
            raise ValueError("Duplicate Plan reference")
        return tuple(sorted(values, key=lambda p: (
            p.plan_id, p.version, p.content_digest
        )))

    @model_validator(mode="after")
    def response_shape(self) -> Self:
        expected = (
            self.outcome == WorkflowStatus.NEEDS_CLARIFICATION,
            self.outcome == WorkflowStatus.WAITING_FOR_APPROVAL,
            self.outcome == WorkflowStatus.FAILED,
        )
        actual = (self.clarification is not None,
                  self.approval_request is not None, self.error is not None)
        if self.outcome not in (
            WorkflowStatus.NEEDS_CLARIFICATION, WorkflowStatus.WAITING_FOR_APPROVAL,
            WorkflowStatus.COMPLETED, WorkflowStatus.FAILED,
        ) or expected != actual:
            raise ValueError("Response must have exactly its workflow outcome payload")
        for interaction in (self.clarification, self.approval_request):
            if interaction and interaction.source_request_id != self.request_id:
                raise ValueError("Response interaction belongs to another request")
        return self
