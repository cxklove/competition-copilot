"""Explicit immutable exposure policy. No SDK, IO, Graph or execution dispatch."""

import json
import re
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel

from competition_copilot.agents.capabilities import (
    AgentCapabilityFacade,
    BuildSnapshotInput,
    CapabilityAccess,
    CapabilityArguments,
    CheckEligibilityInput,
)
from competition_copilot.agents.contracts import CapabilityId
from competition_copilot.integrations.mcp.contracts import (
    McpToolInput,
    McpToolResult,
    canonical_schema,
)
from competition_copilot.tools.competition import (
    GetCompetitionEditionInput,
    GetCompetitionInput,
    GetCompetitionTrackInput,
    ListCompetitionEditionsInput,
    ListCompetitionsInput,
    ListEditionTracksInput,
)


class MutationPolicy(StrEnum):
    NON_MUTATING = "NON_MUTATING"
    MUTATING_NOT_EXPOSED = "MUTATING_NOT_EXPOSED"


class ExposureReason(StrEnum):
    APPROVED = "APPROVED"
    TRUSTED_ARTIFACT_BOUNDARY_REQUIRED = "TRUSTED_ARTIFACT_BOUNDARY_REQUIRED"
    MUTATING_REQUIRES_HUMAN_FLOW = "MUTATING_REQUIRES_HUMAN_FLOW"
    UPSTREAM_CAPABILITY_NOT_EXPOSED = "UPSTREAM_CAPABILITY_NOT_EXPOSED"


@dataclass(frozen=True)
class McpToolDefinition:
    tool_name: str
    capability_id: CapabilityId
    description: str
    access_type: CapabilityAccess
    payload_model: type[BaseModel]
    authority_source: str
    requires_explicit_approval: bool = False
    mcp_exposed: bool = True
    mutation_policy: MutationPolicy = MutationPolicy.NON_MUTATING

    @property
    def input_model(self) -> type[BaseModel]:
        return McpToolInput[self.payload_model]

    @property
    def result_model(self) -> type[McpToolResult]:
        return McpToolResult

    @property
    def input_schema(self) -> dict:
        return canonical_schema(self.input_model)

    @property
    def output_schema(self) -> dict:
        return canonical_schema(self.result_model, mode="serialization")


@dataclass(frozen=True)
class McpExposureDecision:
    capability_id: CapabilityId
    reason: ExposureReason

    @property
    def mcp_exposed(self) -> bool:
        return False

    @property
    def mutation_policy(self) -> MutationPolicy:
        return (MutationPolicy.MUTATING_NOT_EXPOSED
                if self.reason == ExposureReason.MUTATING_REQUIRES_HUMAN_FLOW
                else MutationPolicy.NON_MUTATING)


@dataclass(frozen=True)
class McpToolRegistry:
    """Read-only ordered catalog, checked against public Facade metadata.

    This object cannot authorize execution. P13.3 must enforce lookup before any
    invocation; no arbitrary definitions may be supplied by a remote caller.
    """

    tools: tuple[McpToolDefinition, ...]
    exclusions: tuple[McpExposureDecision, ...]

    def __post_init__(self):
        if not isinstance(self.tools, tuple) or not isinstance(self.exclusions, tuple):
            raise ValueError("Registry requires immutable tuples")
        names = [item.tool_name for item in self.tools]
        if len(names) != len(set(names)):
            raise ValueError("DUPLICATE_TOOL_NAME")
        ids = [item.capability_id for item in self.tools]
        ids.extend(item.capability_id for item in self.exclusions)
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_CAPABILITY_MAPPING")
        if set(ids) != set(CapabilityId):
            raise ValueError("INCOMPLETE_EXPOSURE_POLICY")
        if names != sorted(names):
            raise ValueError("UNORDERED_TOOL_CATALOG")
        if [x.capability_id.value for x in self.exclusions] != sorted(
            x.capability_id.value for x in self.exclusions
        ):
            raise ValueError("UNORDERED_EXCLUSIONS")
        approved = {x.capability: x for x in AgentCapabilityFacade().list_capabilities()}
        for item in self.exclusions:
            meta = approved.get(item.capability_id)
            expected_reason = (
                ExposureReason.UPSTREAM_CAPABILITY_NOT_EXPOSED if meta is None else
                ExposureReason.MUTATING_REQUIRES_HUMAN_FLOW
                if meta.access == CapabilityAccess.MUTATING else
                ExposureReason.TRUSTED_ARTIFACT_BOUNDARY_REQUIRED
            )
            if item.reason != expected_reason:
                raise ValueError("EXCLUSION_REASON_MISMATCH")
        for item in self.tools:
            meta = approved.get(item.capability_id)
            if meta is None:
                raise ValueError("UPSTREAM_CAPABILITY_NOT_EXPOSED")
            if (not item.mcp_exposed or meta.access == CapabilityAccess.MUTATING
                    or meta.requires_explicit_approval or item.requires_explicit_approval
                    or item.mutation_policy != MutationPolicy.NON_MUTATING):
                raise ValueError("MUTATION_NOT_EXPOSED")
            if item.access_type != meta.access:
                raise ValueError("CAPABILITY_ACCESS_MISMATCH")
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", item.tool_name):
                raise ValueError("INVALID_TOOL_NAME")
            if not item.description.strip() or not item.authority_source.strip():
                raise ValueError("MISSING_TOOL_METADATA")
            # Compare the declared payload against the public upstream schema.
            expected = canonical_schema(CapabilityArguments[item.payload_model])
            if expected != json.loads(meta.input_schema_json):
                raise ValueError("CAPABILITY_INPUT_MISMATCH")

    def get(self, tool_name: str) -> McpToolDefinition:
        for item in self.tools:
            if item.tool_name == tool_name:
                return item
        raise ValueError("UNKNOWN_TOOL")


def build_mcp_tool_registry() -> McpToolRegistry:
    """Explicit server policy, independent of user/session/repository contents."""
    return McpToolRegistry(tools=(
        McpToolDefinition(
            "competition_edition_get", CapabilityId.GET_EDITION,
            "Read a verified edition; does not infer eligibility or modify data.",
            CapabilityAccess.READ, GetCompetitionEditionInput, "P4 GetCompetitionEditionTool"),
        McpToolDefinition(
            "competition_editions_list", CapabilityId.LIST_EDITIONS,
            "List verified editions of a competition; does not predict future editions.",
            CapabilityAccess.READ, ListCompetitionEditionsInput, "P4 ListCompetitionEditionsTool"),
        McpToolDefinition(
            "competition_get", CapabilityId.GET_COMPETITION,
            "Read a verified competition; does not assess student eligibility.",
            CapabilityAccess.READ, GetCompetitionInput, "P4 GetCompetitionTool"),
        McpToolDefinition(
            "competition_list", CapabilityId.LIST_COMPETITIONS,
            "List verified competitions; does not rank recommendations or search the web.",
            CapabilityAccess.READ, ListCompetitionsInput, "P4 ListCompetitionsTool"),
        McpToolDefinition(
            "competition_snapshot_build", CapabilityId.BUILD_COMPETITION_SNAPSHOT,
            "Build a read-only snapshot at the supplied observation time; does not persist changes.",
            CapabilityAccess.READ, BuildSnapshotInput, "P9 CompetitionSnapshotBuilder"),
        McpToolDefinition(
            "competition_track_get", CapabilityId.GET_TRACK,
            "Read a verified track; does not infer unobserved facts or modify data.",
            CapabilityAccess.READ, GetCompetitionTrackInput, "P4 GetCompetitionTrackTool"),
        McpToolDefinition(
            "competition_tracks_list", CapabilityId.LIST_TRACKS,
            "List verified edition tracks; does not infer removal from missing observations.",
            CapabilityAccess.READ, ListEditionTracksInput, "P4 ListEditionTracksTool"),
        McpToolDefinition(
            "eligibility_check", CapabilityId.CHECK_ELIGIBILITY,
            "Evaluate supplied student facts under existing P5 rules; does not override status or infer missing facts.",
            CapabilityAccess.DECISION, CheckEligibilityInput, "P5 CompetitionEligibilityEvaluator"),
    ), exclusions=(
        McpExposureDecision(CapabilityId.ANALYZE_EVENT_IMPACT,
                            ExposureReason.TRUSTED_ARTIFACT_BOUNDARY_REQUIRED),
        McpExposureDecision(CapabilityId.ANALYZE_SKILL_GAP,
                            ExposureReason.TRUSTED_ARTIFACT_BOUNDARY_REQUIRED),
        McpExposureDecision(CapabilityId.BUILD_PLAN,
                            ExposureReason.TRUSTED_ARTIFACT_BOUNDARY_REQUIRED),
        McpExposureDecision(CapabilityId.CHECK_COMPETITION_CHANGES,
                            ExposureReason.UPSTREAM_CAPABILITY_NOT_EXPOSED),
        McpExposureDecision(CapabilityId.DECIDE_REPLANNING,
                            ExposureReason.TRUSTED_ARTIFACT_BOUNDARY_REQUIRED),
        McpExposureDecision(CapabilityId.DERIVE_COMPETITION_EVENTS,
                            ExposureReason.TRUSTED_ARTIFACT_BOUNDARY_REQUIRED),
        McpExposureDecision(CapabilityId.DIFF_COMPETITION_SNAPSHOT,
                            ExposureReason.TRUSTED_ARTIFACT_BOUNDARY_REQUIRED),
        McpExposureDecision(CapabilityId.EXPLAIN_REPLANNING,
                            ExposureReason.UPSTREAM_CAPABILITY_NOT_EXPOSED),
        McpExposureDecision(CapabilityId.GET_RECOMMENDATIONS,
                            ExposureReason.TRUSTED_ARTIFACT_BOUNDARY_REQUIRED),
        McpExposureDecision(CapabilityId.REVISE_PLAN,
                            ExposureReason.MUTATING_REQUIRES_HUMAN_FLOW),
    ))
