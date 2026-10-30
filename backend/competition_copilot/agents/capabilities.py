"""Explicit invocation boundary, not routing, approval collection or business logic.

Caller composition supplies Tools/Application and prepared deterministic Domain
dependencies. No concrete Repository, provider, SDK, IO or global service locator.
"""

import json
from collections.abc import Mapping
from enum import StrEnum
from functools import lru_cache
from types import MappingProxyType
from typing import Generic, Self, TypeVar

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from competition_copilot.agents.contracts import (
    AgentContract,
    AuditReferences,
    CapabilityId,
    CapabilityInvocationRequest,
    ReasonReference,
    ReferenceKind,
    ResultReference,
)
from competition_copilot.application.competition_detail import (
    CompetitionDetailProjection,
    CompetitionDetailQuery,
)
from competition_copilot.application.competition_snapshots import (
    CompetitionSnapshotBuilder,
)
from competition_copilot.application.eligibility import (
    CompetitionEligibilityEvaluator,
    EligibilityTargetError,
)
from competition_copilot.application.my_competitions import (
    MyCompetitionCommand,
    MyCompetitionEditor,
    MyCompetitionMutationResult,
    MyCompetitionProjection,
    MyCompetitionQuery,
    MyCompetitionsProjection,
    MyCompetitionsReader,
    MyPlanSelection,
    MyPlanSelectionResult,
    MyPlanSelector,
)
from competition_copilot.application.planning_workspace import (
    PlanningWorkspaceProjection,
    PlanningWorkspaceQuery,
    PlanningWorkspaceReader,
)
from competition_copilot.application.profile_freshness import (
    ProfileAnalysesProjection,
    ProfileAnalysesQuery,
    ProfileAnalysesReader,
)
from competition_copilot.application.profile_skills import (
    SkillCatalogProjection,
    SkillCatalogQuery,
    SkillCatalogReader,
    SkillMutationInput,
    StudentSkillEditor,
)
from competition_copilot.application.profiles import (
    GetProfileQuery,
    ProfileMutationResult,
    StudentProfileEditor,
    StudentProfileReader,
    UpdateProfileInput,
)
from competition_copilot.domain.baseline_plan_builder import (
    BaselineCompetitionPlanBuilder,
)
from competition_copilot.domain.digital_twin import (
    CompetitionSnapshot,
    CompetitionTarget,
    SnapshotDiff,
    StableId,
)
from competition_copilot.domain.eligibility import EligibilityDecision
from competition_copilot.domain.event import CompetitionEvent
from competition_copilot.domain.event_aggregation import CompetitionEventAggregator
from competition_copilot.domain.event_engine import CompetitionEventEngine
from competition_copilot.domain.event_impact_analyzer import (
    CompetitionEventImpactAnalyzer,
)
from competition_copilot.domain.plan import CompetitionPlan
from competition_copilot.domain.plan_revision_service import (
    PlanRevisionResult,
    PlanRevisionService,
)
from competition_copilot.domain.planning_inputs import PlanningInputDeriver
from competition_copilot.domain.recommendation import RecommendationContext
from competition_copilot.domain.recommendation_ranking import (
    RecommendationRankingEngine,
    RecommendationRankingResult,
)
from competition_copilot.domain.recommendation_scoring import (
    RecommendationScoringEngine,
)
from competition_copilot.domain.replanning import (
    EventImpactAnalysis,
    ReplanningDecision,
)
from competition_copilot.domain.replanning_decision_service import (
    ReplanningDecisionService,
)
from competition_copilot.domain.replanning_input import ReplanningInput
from competition_copilot.domain.skill_gap import SkillGapContext, SkillGapDecision
from competition_copilot.domain.skill_gap_engine import SkillGapEngine
from competition_copilot.domain.snapshot_diff_engine import SnapshotDiffEngine
from competition_copilot.domain.student import StudentProfile
from competition_copilot.domain.temporal import TimeWindow
from competition_copilot.repositories.student import (
    ProfileError,
    StudentProfileProjection,
)
from competition_copilot.tools.competition import (
    GetCompetitionEditionInput,
    GetCompetitionEditionOutput,
    GetCompetitionInput,
    GetCompetitionOutput,
    GetCompetitionTrackInput,
    GetCompetitionTrackOutput,
    ListCompetitionEditionsInput,
    ListCompetitionEditionsOutput,
    ListCompetitionsInput,
    ListCompetitionsOutput,
    ListEditionTracksInput,
    ListEditionTracksOutput,
)
from competition_copilot.tools.contracts import Tool, ToolErrorCode

InputT = TypeVar("InputT", bound=BaseModel)


class CapabilityArguments(AgentContract, Generic[InputT]):
    """Typed artifact payload binding the existing P12.1 arguments_ref.

    Model-specific schema is selected by the static capability set, not by LLM.
    artifact_ref and result_ref are caller-owned, invocation-scoped references.
    """

    artifact_ref: ResultReference
    payload: InputT

    @field_validator("payload", mode="before")
    @classmethod
    def detach_payload(cls, value):
        return value.model_dump() if isinstance(value, BaseModel) else value

    @model_validator(mode="after")
    def argument_reference(self) -> Self:
        if self.artifact_ref.kind != ReferenceKind.CAPABILITY_ARGUMENTS:
            raise ValueError("Expected CAPABILITY_ARGUMENTS artifact")
        return self


@lru_cache(maxsize=None)
def _input_schema_json(model: type[BaseModel]) -> str:
    """Approved model schemas are static; retain only their immutable JSON text."""
    return json.dumps(CapabilityArguments[model].model_json_schema(), sort_keys=True)


class CheckEligibilityInput(AgentContract):
    student: StudentProfile
    competition_id: StableId
    edition_id: StableId
    track_id: StableId | None = None


class RecommendCompetitionsInput(AgentContract):
    """Explicit caller-prepared eligibility; scorer policy comes from injected P6."""

    contexts: tuple[RecommendationContext, ...]


class AnalyzeSkillGapInput(AgentContract):
    context: SkillGapContext


class BuildPlanInput(AgentContract):
    source_decision: SkillGapDecision
    student_id: StableId
    created_at: AwareDatetime
    planning_horizon: TimeWindow | None = None


class DiffSnapshotsInput(AgentContract):
    before: CompetitionSnapshot
    after: CompetitionSnapshot


class BuildSnapshotInput(AgentContract):
    target: CompetitionTarget
    observed_at: AwareDatetime


class DeriveEventsInput(AgentContract):
    source_diff: SnapshotDiff
    detected_at: AwareDatetime


class EventBatch(AgentContract):
    """Collection envelope only; each Event is the frozen P10 contract."""

    events: tuple[CompetitionEvent, ...]


class AnalyzeEventImpactInput(AgentContract):
    event: CompetitionEvent
    student: StudentProfile
    plan: CompetitionPlan
    evaluated_at: AwareDatetime


class DecideReplanningInput(AgentContract):
    impacts: tuple[EventImpactAnalysis, ...] = Field(min_length=1)
    plan: CompetitionPlan
    evaluated_at: AwareDatetime


class ApplyApprovedRevisionInput(AgentContract):
    before: CompetitionPlan
    replanning_input: ReplanningInput
    executed_at: AwareDatetime


class CapabilityAccess(StrEnum):
    READ = "READ"
    DECISION = "DECISION"
    MUTATING = "MUTATING"


class CapabilityStatus(StrEnum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class CapabilityErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    MY_COMPETITION_ALREADY_EXISTS = "MY_COMPETITION_ALREADY_EXISTS"
    MY_COMPETITION_NOT_FOUND = "MY_COMPETITION_NOT_FOUND"
    MY_COMPETITION_VERSION_CONFLICT = "MY_COMPETITION_VERSION_CONFLICT"
    MY_COMPETITION_FORBIDDEN = "MY_COMPETITION_FORBIDDEN"
    MY_COMPETITION_INVALID_TARGET = "MY_COMPETITION_INVALID_TARGET"
    MY_COMPETITION_INVALID_REFERENCE = "MY_COMPETITION_INVALID_REFERENCE"
    MY_COMPETITION_REPOSITORY_UNAVAILABLE = "MY_COMPETITION_REPOSITORY_UNAVAILABLE"

    PLAN_REFERENCE_UNAVAILABLE = "PLAN_REFERENCE_UNAVAILABLE"
    PLANNING_IDENTITY_MISMATCH = "PLANNING_IDENTITY_MISMATCH"
    PROFILE_NOT_FOUND = "PROFILE_NOT_FOUND"
    PROFILE_VERSION_CONFLICT = "PROFILE_VERSION_CONFLICT"
    PROFILE_EDIT_FORBIDDEN = "PROFILE_EDIT_FORBIDDEN"
    INVALID_PROFILE_FIELD = "INVALID_PROFILE_FIELD"
    SKILL_ALREADY_EXISTS = "SKILL_ALREADY_EXISTS"
    SKILL_NOT_FOUND = "SKILL_NOT_FOUND"
    SKILL_NOT_IN_CATALOG = "SKILL_NOT_IN_CATALOG"
    INVALID_SKILL_LEVEL = "INVALID_SKILL_LEVEL"
    SKILL_EVIDENCE_INCONSISTENT = "SKILL_EVIDENCE_INCONSISTENT"
    SKILL_CATALOG_CONFLICT = "SKILL_CATALOG_CONFLICT"

    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    NOT_FOUND = "NOT_FOUND"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    EXECUTION_REJECTED = "EXECUTION_REJECTED"


class CapabilityError(AgentContract):
    code: CapabilityErrorCode
    message: StableId


class CapabilityMetadata(AgentContract):
    capability: CapabilityId
    description: StableId
    input_schema_json: StableId
    output_type: StableId
    access: CapabilityAccess
    requires_explicit_approval: bool = Field(strict=True)


# Static schemas/dispatch set. IDs present in P12.1 but absent here are deferred.

_READ = MappingProxyType({
    CapabilityId.GET_COMPETITION_DETAILS: (CompetitionDetailQuery, CompetitionDetailProjection),
    CapabilityId.LIST_COMPETITIONS: (ListCompetitionsInput, ListCompetitionsOutput),
    CapabilityId.GET_COMPETITION: (GetCompetitionInput, GetCompetitionOutput),
    CapabilityId.LIST_EDITIONS: (ListCompetitionEditionsInput, ListCompetitionEditionsOutput),
    CapabilityId.GET_EDITION: (GetCompetitionEditionInput, GetCompetitionEditionOutput),
    CapabilityId.LIST_TRACKS: (ListEditionTracksInput, ListEditionTracksOutput),
    CapabilityId.GET_TRACK: (GetCompetitionTrackInput, GetCompetitionTrackOutput),
})
_SPECS = MappingProxyType({
    **_READ,
    CapabilityId.GET_MY_COMPETITIONS: (GetProfileQuery, MyCompetitionsProjection),
    CapabilityId.GET_MY_COMPETITION: (MyCompetitionQuery, MyCompetitionProjection),
    CapabilityId.ADD_MY_COMPETITION: (MyCompetitionCommand, MyCompetitionMutationResult),
    CapabilityId.UPDATE_MY_COMPETITION: (MyCompetitionCommand, MyCompetitionMutationResult),
    CapabilityId.REMOVE_MY_COMPETITION: (MyCompetitionCommand, MyCompetitionMutationResult),
    CapabilityId.SELECT_MY_COMPETITION_PLAN: (MyPlanSelection, MyPlanSelectionResult),

    CapabilityId.GET_PLANNING_WORKSPACE: (PlanningWorkspaceQuery, PlanningWorkspaceProjection),
    CapabilityId.GET_PROFILE_ANALYSES: (ProfileAnalysesQuery, ProfileAnalysesProjection),
    CapabilityId.GET_PROFILE: (GetProfileQuery, StudentProfileProjection),
    CapabilityId.GET_SKILL_CATALOG: (SkillCatalogQuery, SkillCatalogProjection),
    CapabilityId.ADD_PROFILE_SKILL: (SkillMutationInput, ProfileMutationResult),
    CapabilityId.UPDATE_PROFILE_SKILL: (SkillMutationInput, ProfileMutationResult),
    CapabilityId.REMOVE_PROFILE_SKILL: (SkillMutationInput, ProfileMutationResult),

    CapabilityId.UPDATE_PROFILE: (UpdateProfileInput, ProfileMutationResult),
    CapabilityId.CHECK_ELIGIBILITY: (CheckEligibilityInput, EligibilityDecision),
    CapabilityId.GET_RECOMMENDATIONS: (RecommendCompetitionsInput, RecommendationRankingResult),
    CapabilityId.ANALYZE_SKILL_GAP: (AnalyzeSkillGapInput, SkillGapDecision),
    CapabilityId.BUILD_PLAN: (BuildPlanInput, CompetitionPlan),
    CapabilityId.DIFF_COMPETITION_SNAPSHOT: (DiffSnapshotsInput, SnapshotDiff),
    CapabilityId.BUILD_COMPETITION_SNAPSHOT: (BuildSnapshotInput, CompetitionSnapshot),
    CapabilityId.DERIVE_COMPETITION_EVENTS: (DeriveEventsInput, EventBatch),
    CapabilityId.ANALYZE_EVENT_IMPACT: (AnalyzeEventImpactInput, EventImpactAnalysis),
    CapabilityId.DECIDE_REPLANNING: (DecideReplanningInput, ReplanningDecision),
    CapabilityId.REVISE_PLAN: (ApplyApprovedRevisionInput, PlanRevisionResult),
})

CapabilityOutput = (
    MyCompetitionsProjection | MyCompetitionProjection | MyCompetitionMutationResult | MyPlanSelectionResult |
    PlanningWorkspaceProjection | ProfileAnalysesProjection | SkillCatalogProjection | StudentProfileProjection | ProfileMutationResult | CompetitionDetailProjection | ListCompetitionsOutput | GetCompetitionOutput | ListCompetitionEditionsOutput
    | GetCompetitionEditionOutput | ListEditionTracksOutput | GetCompetitionTrackOutput
    | EligibilityDecision | RecommendationRankingResult | SkillGapDecision
    | CompetitionPlan | CompetitionSnapshot | SnapshotDiff | EventBatch | EventImpactAnalysis
    | ReplanningDecision | PlanRevisionResult
)


class AgentCapabilityResult(AgentContract):
    """Invocation receipt retains original typed result, not a Domain replica."""

    invocation_id: StableId
    source_request_id: StableId
    capability: CapabilityId | None
    status: CapabilityStatus
    result_ref: ResultReference
    data: CapabilityOutput | None = None
    audit: AuditReferences = Field(default_factory=AuditReferences)
    error: CapabilityError | None = None

    @model_validator(mode="after")
    def exclusive_outcome(self) -> Self:
        if self.result_ref.kind != ReferenceKind.TOOL_RESULT:
            raise ValueError("Invocation result reference must be TOOL_RESULT")
        if self.status == CapabilityStatus.SUCCESS:
            if self.error is not None or self.data is None or self.capability not in _SPECS:
                raise ValueError("Success requires exposed capability and typed data only")
            if not isinstance(self.data, _SPECS[self.capability][1]):
                raise ValueError("Result type must match capability")
            if self.result_ref not in self.audit.results:
                raise ValueError("Success must retain its result artifact reference")
        elif self.data is not None or self.error is None:
            raise ValueError("Error requires error only")
        return self


def _audit(data: BaseModel, result_ref: ResultReference) -> AuditReferences:
    """JSON Pointer projection only: retain producer codes/evidence/source locations.

    No fact, impact, score or coverage interpretation. Nested formal payload remains
    intact. Qualified refs point into caller-owned result artifact, not stored history.
    """
    refs = {(result_ref.kind, result_ref.ref_id): result_ref}
    reasons = {}

    def visit(value, path):
        if isinstance(value, dict):
            owner = ResultReference(kind=ReferenceKind.TOOL_RESULT,
                                    ref_id=result_ref.ref_id + "#/data" + path)
            for key, item in value.items():
                child = path + "/" + key.replace("~", "~0").replace("/", "~1")
                if key in ("reason_code", "reason_codes"):
                    codes = item if isinstance(item, list) else [item]
                    for code in codes:
                        if isinstance(code, str) and code.strip():
                            refs[(owner.kind, owner.ref_id)] = owner
                            reasons[(owner.ref_id, code)] = ReasonReference(
                                result=owner, reason_code=code)
                if key in ("source", "sources", "evidence", "presence_evidence",
                           "student_evidence", "coverage_evidence") and item:
                    kind = ReferenceKind.SOURCE if key in ("source", "sources") else ReferenceKind.EVIDENCE
                    locations = [child + "/" + str(i) for i in range(len(item))] if isinstance(item, list) else [child]
                    for location in locations:
                        reference = ResultReference(kind=kind, ref_id=result_ref.ref_id + "#/data" + location)
                        refs[(kind, reference.ref_id)] = reference
                visit(item, child)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                visit(item, path + "/" + str(i))

    visit(data.model_dump(mode="json"), "")
    return AuditReferences(results=tuple(refs.values()), reasons=tuple(reasons.values()))


class _InvocationRejected(Exception):
    def __init__(self, code: CapabilityErrorCode):
        self.code = code


class AgentCapabilityFacade:
    """Explicit dispatch with injected authorities, no infrastructure composition."""

    def __init__(
        self, *, read_tools: Mapping[CapabilityId, Tool] | None = None,
        eligibility: CompetitionEligibilityEvaluator | None = None,
        scoring: RecommendationScoringEngine | None = None,
        ranking: RecommendationRankingEngine | None = None,
        skill_gap: SkillGapEngine | None = None,
        planning_inputs: PlanningInputDeriver | None = None,
        planner: BaselineCompetitionPlanBuilder | None = None,
        snapshot_diff: SnapshotDiffEngine | None = None,
        snapshot_builder: CompetitionSnapshotBuilder | None = None,
        event_engine: CompetitionEventEngine | None = None,
        event_aggregator: CompetitionEventAggregator | None = None,
        impact: CompetitionEventImpactAnalyzer | None = None,
        replanning: ReplanningDecisionService | None = None,
        revision: PlanRevisionService | None = None,
        skill_catalog: SkillCatalogReader | None = None,
        skill_editor: StudentSkillEditor | None = None,
        profile_analyses: ProfileAnalysesReader | None = None,
        my_competitions: MyCompetitionsReader | None = None,
        my_competition_editor: MyCompetitionEditor | None = None,
        my_plan_selector: MyPlanSelector | None = None,
        planning_workspace: PlanningWorkspaceReader | None = None,
        profile_reader: StudentProfileReader | None = None,
        profile_editor: StudentProfileEditor | None = None,
    ):
        self._my_competitions, self._my_competition_editor, self._my_plan_selector = my_competitions, my_competition_editor, my_plan_selector
        self._planning_workspace = planning_workspace
        self._profile_analyses = profile_analyses
        self._skill_catalog, self._skill_editor = skill_catalog, skill_editor
        self._profile_reader, self._profile_editor = profile_reader, profile_editor
        tools = dict(read_tools or {})
        for capability, tool in tools.items():
            if capability not in _READ or (
                tool.metadata.name != capability.value
                or tool.metadata.input_model != _READ[capability][0]
            ):
                raise ValueError("Read Tool must match its approved capability schema")
        self._read_tools = MappingProxyType(tools)
        self._eligibility, self._scoring, self._ranking = eligibility, scoring, ranking
        self._skill_gap, self._planning_inputs, self._planner = skill_gap, planning_inputs, planner
        self._snapshot_diff = snapshot_diff
        self._snapshot_builder = snapshot_builder
        self._event_engine, self._event_aggregator = event_engine, event_aggregator
        self._impact, self._replanning, self._revision = impact, replanning, revision

    def list_capabilities(self) -> tuple[CapabilityMetadata, ...]:
        return tuple(CapabilityMetadata(
            capability=capability,
            description=f"Delegate {capability.value} to the existing deterministic authority.",
            input_schema_json=_input_schema_json(models[0]),
            output_type=models[1].__name__,
            access=(CapabilityAccess.READ if capability in _READ or capability in (CapabilityId.GET_MY_COMPETITIONS, CapabilityId.GET_MY_COMPETITION, CapabilityId.GET_PLANNING_WORKSPACE, CapabilityId.BUILD_COMPETITION_SNAPSHOT, CapabilityId.GET_PROFILE, CapabilityId.GET_PROFILE_ANALYSES, CapabilityId.GET_SKILL_CATALOG) else
                    CapabilityAccess.MUTATING if capability in (CapabilityId.ADD_MY_COMPETITION, CapabilityId.UPDATE_MY_COMPETITION, CapabilityId.REMOVE_MY_COMPETITION, CapabilityId.SELECT_MY_COMPETITION_PLAN, CapabilityId.REVISE_PLAN, CapabilityId.UPDATE_PROFILE, CapabilityId.ADD_PROFILE_SKILL, CapabilityId.UPDATE_PROFILE_SKILL, CapabilityId.REMOVE_PROFILE_SKILL)
                    else CapabilityAccess.DECISION),
            requires_explicit_approval=capability == CapabilityId.REVISE_PLAN,
        ) for capability, models in sorted(_SPECS.items(), key=lambda pair: pair[0].value))

    @staticmethod
    def _require(*dependencies):
        if any(item is None for item in dependencies):
            raise _InvocationRejected(CapabilityErrorCode.DEPENDENCY_UNAVAILABLE)

    @staticmethod
    def validate_arguments(invocation: CapabilityInvocationRequest, arguments: object):
        """Syntax-only validation, with no delegation or dependency access."""
        if invocation.capability not in _SPECS:
            raise ValueError("Unsupported capability")
        schema = CapabilityArguments[_SPECS[invocation.capability][0]]
        args = schema.model_validate(arguments)
        if args.artifact_ref != invocation.arguments_ref:
            raise ValueError("Argument artifact must match invocation reference")
        return schema.model_validate_json(args.model_dump_json())

    def execute(
        self, invocation: CapabilityInvocationRequest | dict,
        arguments: object, *, result_ref: ResultReference,
    ) -> AgentCapabilityResult:
        result_ref = ResultReference.model_validate(result_ref)
        if result_ref.kind != ReferenceKind.TOOL_RESULT:
            raise ValueError("Provide a caller-owned TOOL_RESULT artifact reference")
        raw = invocation.model_dump() if isinstance(invocation, BaseModel) else invocation
        if not isinstance(raw, dict):
            raise TypeError("Provide a typed invocation or JSON object")
        # Missing/invalid correlation identity rejects at the syntax boundary; no ID invention.
        invocation_id = TypeAdapter(StableId).validate_python(raw.get("invocation_id"))
        source_request_id = TypeAdapter(StableId).validate_python(raw.get("source_request_id"))
        capability = None

        def error(code):
            return AgentCapabilityResult(
                invocation_id=invocation_id, source_request_id=source_request_id,
                capability=capability, status=CapabilityStatus.ERROR, result_ref=result_ref,
                error=CapabilityError(code=code, message=code.value),
            )

        try:
            capability = CapabilityId(raw.get("capability"))
        except (ValueError, TypeError):
            return error(CapabilityErrorCode.UNSUPPORTED_CAPABILITY)
        if capability not in _SPECS:
            return error(CapabilityErrorCode.UNSUPPORTED_CAPABILITY)
        try:
            invocation = CapabilityInvocationRequest.model_validate(raw)
            args = self.validate_arguments(invocation, arguments)
        except (ValidationError, ValueError, TypeError):
            return error(CapabilityErrorCode.INVALID_INPUT)
        try:
            data = self._delegate(capability, args.payload)
            return AgentCapabilityResult(
                invocation_id=invocation_id, source_request_id=source_request_id,
                capability=capability, status=CapabilityStatus.SUCCESS,
                result_ref=result_ref, data=data, audit=_audit(data, result_ref),
            )
        except ProfileError as exc:
            return error(CapabilityErrorCode(exc.code))
        except _InvocationRejected as exc:
            return error(exc.code)
        except EligibilityTargetError as exc:
            return error(CapabilityErrorCode.NOT_FOUND if exc.reason == "target_not_found"
                         else CapabilityErrorCode.EXECUTION_REJECTED)
        except Exception:
            # No exception prose/private provider details or speculative fallback result.
            return error(CapabilityErrorCode.EXECUTION_REJECTED)

    def _delegate(self, capability, value):
        if capability in (CapabilityId.GET_MY_COMPETITIONS, CapabilityId.GET_MY_COMPETITION):
            self._require(self._my_competitions)
            return self._my_competitions.read(value) if capability == CapabilityId.GET_MY_COMPETITIONS else self._my_competitions.get(value)
        if capability == CapabilityId.SELECT_MY_COMPETITION_PLAN:
            self._require(self._my_plan_selector)
            return self._my_plan_selector.select(value)
        if capability in (CapabilityId.ADD_MY_COMPETITION, CapabilityId.UPDATE_MY_COMPETITION, CapabilityId.REMOVE_MY_COMPETITION):
            self._require(self._my_competition_editor)
            if capability.value != value.operation + "_my_competition":
                raise _InvocationRejected(CapabilityErrorCode.INVALID_INPUT)
            return self._my_competition_editor.mutate(value)
        if capability == CapabilityId.GET_PLANNING_WORKSPACE:
            self._require(self._planning_workspace)
            return self._planning_workspace.read(value)
        if capability == CapabilityId.GET_PROFILE_ANALYSES:
            self._require(self._profile_analyses)
            return self._profile_analyses.read(value)
        if capability == CapabilityId.GET_SKILL_CATALOG:
            self._require(self._skill_catalog)
            return self._skill_catalog.read(value)
        if capability in (CapabilityId.ADD_PROFILE_SKILL, CapabilityId.UPDATE_PROFILE_SKILL, CapabilityId.REMOVE_PROFILE_SKILL):
            self._require(self._skill_editor)
            if capability.value != value.command.operation + "_profile_skill":
                raise _InvocationRejected(CapabilityErrorCode.INVALID_INPUT)
            return self._skill_editor.mutate(value)
        if capability == CapabilityId.GET_PROFILE:
            self._require(self._profile_reader)
            return self._profile_reader.read(value)
        if capability == CapabilityId.UPDATE_PROFILE:
            self._require(self._profile_editor)
            return self._profile_editor.edit(value)
        if capability in _READ:
            tool = self._read_tools.get(capability)
            self._require(tool)
            output = tool.execute(value.model_dump())
            if not output.success:
                code = {
                    ToolErrorCode.INVALID_INPUT: CapabilityErrorCode.INVALID_INPUT,
                    ToolErrorCode.NOT_FOUND: CapabilityErrorCode.NOT_FOUND,
                    ToolErrorCode.INTERNAL_ERROR: CapabilityErrorCode.DEPENDENCY_UNAVAILABLE,
                }[output.error.code]
                raise _InvocationRejected(code)
            return output.data
        if capability == CapabilityId.CHECK_ELIGIBILITY:
            self._require(self._eligibility)
            return self._eligibility.evaluate(value.student, value.competition_id,
                                              value.edition_id, value.track_id)
        if capability == CapabilityId.GET_RECOMMENDATIONS:
            self._require(self._scoring, self._ranking)
            return self._ranking.rank(tuple(self._scoring.evaluate(c) for c in value.contexts))
        if capability == CapabilityId.ANALYZE_SKILL_GAP:
            self._require(self._skill_gap)
            return self._skill_gap.evaluate(value.context)
        if capability == CapabilityId.BUILD_PLAN:
            self._require(self._planning_inputs, self._planner)
            return self._planner.build(
                target=value.source_decision.target,
                planning_needs=self._planning_inputs.derive(value.source_decision),
                source_audit=self._planning_inputs.source_audit(value.source_decision),
                student_id=value.student_id, created_at=value.created_at,
                planning_horizon=value.planning_horizon,
            )
        if capability == CapabilityId.DIFF_COMPETITION_SNAPSHOT:
            self._require(self._snapshot_diff)
            return self._snapshot_diff.compare(value.before, value.after)
        if capability == CapabilityId.BUILD_COMPETITION_SNAPSHOT:
            self._require(self._snapshot_builder)
            return self._snapshot_builder.build(value.target, value.observed_at)
        if capability == CapabilityId.DERIVE_COMPETITION_EVENTS:
            self._require(self._event_engine, self._event_aggregator)
            return EventBatch(events=self._event_aggregator.normalize(
                self._event_engine.interpret(value.source_diff, detected_at=value.detected_at)))
        if capability == CapabilityId.ANALYZE_EVENT_IMPACT:
            self._require(self._impact)
            return self._impact.analyze(value.event, value.student, value.plan,
                                        evaluated_at=value.evaluated_at)
        if capability == CapabilityId.DECIDE_REPLANNING:
            self._require(self._replanning)
            return self._replanning.decide(value.impacts, value.plan,
                                           evaluated_at=value.evaluated_at)
        if capability == CapabilityId.REVISE_PLAN:
            self._require(self._revision)
            return self._revision.revise(value.before, value.replanning_input,
                                          executed_at=value.executed_at)
        raise _InvocationRejected(CapabilityErrorCode.UNSUPPORTED_CAPABILITY)
