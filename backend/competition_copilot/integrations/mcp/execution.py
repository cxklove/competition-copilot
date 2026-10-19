"""Stateless MCP projection into the existing Facade; no SDK or business logic."""

import json
from dataclasses import dataclass
from types import MappingProxyType

from pydantic import ValidationError

from competition_copilot.agents.capabilities import (
    AgentCapabilityFacade,
    AgentCapabilityResult,
    CapabilityAccess,
    CapabilityArguments,
    CapabilityError,
    CapabilityStatus,
)
from competition_copilot.agents.contracts import (
    AgentIntent,
    CapabilityId,
    CapabilityInvocationRequest,
)
from competition_copilot.integrations.mcp.contracts import (
    McpToolError,
    McpToolErrorCode,
    McpToolResult,
    canonical_schema,
)
from competition_copilot.integrations.mcp.registry import (
    McpToolDefinition,
    McpToolRegistry,
    MutationPolicy,
)

# Required legacy invocation labels only. They do not select the capability,
# interpret user text or run an Agent workflow. Names/exposure remain in registry.
_INVOCATION_LABELS = MappingProxyType({
    CapabilityId.LIST_COMPETITIONS: AgentIntent.DISCOVER_COMPETITIONS,
    CapabilityId.GET_COMPETITION: AgentIntent.GET_COMPETITION_DETAILS,
    CapabilityId.LIST_EDITIONS: AgentIntent.GET_COMPETITION_DETAILS,
    CapabilityId.GET_EDITION: AgentIntent.GET_COMPETITION_DETAILS,
    CapabilityId.LIST_TRACKS: AgentIntent.GET_COMPETITION_DETAILS,
    CapabilityId.GET_TRACK: AgentIntent.GET_COMPETITION_DETAILS,
    CapabilityId.BUILD_COMPETITION_SNAPSHOT: AgentIntent.CHECK_COMPETITION_CHANGES,
    CapabilityId.CHECK_ELIGIBILITY: AgentIntent.CHECK_ELIGIBILITY,
})


def execution_error(code: McpToolErrorCode) -> McpToolResult:
    return McpToolResult(error=McpToolError(code=code))


def validate_execution_policy(
    definition: McpToolDefinition, facade: AgentCapabilityFacade,
) -> McpToolErrorCode | None:
    """Check current public metadata on every call, including corrupted policy."""
    if (definition.access_type == CapabilityAccess.MUTATING
            or definition.requires_explicit_approval
            or definition.mutation_policy != MutationPolicy.NON_MUTATING):
        return McpToolErrorCode.CAPABILITY_NOT_EXPOSED
    if definition.mcp_exposed is not True:
        return McpToolErrorCode.CAPABILITY_NOT_EXPOSED
    metadata = {item.capability: item for item in facade.list_capabilities()}
    meta = metadata.get(definition.capability_id)
    if meta is None:
        return McpToolErrorCode.CAPABILITY_NOT_EXPOSED
    if meta.access == CapabilityAccess.MUTATING or meta.requires_explicit_approval:
        return McpToolErrorCode.CAPABILITY_NOT_EXPOSED
    if (meta.access != definition.access_type
            or definition.capability_id not in _INVOCATION_LABELS
            or json.loads(meta.input_schema_json) != canonical_schema(
                CapabilityArguments[definition.payload_model])):
        return McpToolErrorCode.CAPABILITY_NOT_EXPOSED
    return None


@dataclass(frozen=True)
class McpToolDispatcher:
    registry: McpToolRegistry
    facade: AgentCapabilityFacade | None

    def dispatch(self, tool_name: str, arguments: object) -> McpToolResult:
        """Validate/project/delegate once; never retry or retain call context."""
        try:
            definition = self.registry.get(tool_name)
        except ValueError:
            return execution_error(McpToolErrorCode.UNKNOWN_TOOL)
        except Exception:
            return execution_error(McpToolErrorCode.EXECUTION_FAILURE)
        try:
            # Formal upstream guard is independent of the injected dependency.
            rejection = validate_execution_policy(definition, AgentCapabilityFacade())
            if rejection:
                return execution_error(rejection)
            try:
                if not isinstance(arguments, dict):
                    return execution_error(McpToolErrorCode.INVALID_ARGUMENTS)
                value = definition.input_model.model_validate(arguments)
                value = definition.input_model.model_validate_json(value.model_dump_json())
            except (ValidationError, ValueError, TypeError):
                return execution_error(McpToolErrorCode.INVALID_ARGUMENTS)
            if self.facade is None:
                return execution_error(McpToolErrorCode.CAPABILITY_NOT_EXPOSED)
            rejection = validate_execution_policy(definition, self.facade)
            if rejection:
                return execution_error(rejection)
            invocation = CapabilityInvocationRequest(
                invocation_id=value.invocation_id,
                source_request_id=value.source_request_id,
                intent=_INVOCATION_LABELS[definition.capability_id],
                capability=definition.capability_id,
                arguments_ref=value.arguments_ref, requires_approval=False,
            )
            arguments = CapabilityArguments[definition.payload_model](
                artifact_ref=value.arguments_ref, payload=value.payload,
            )
            # Sole business entry. There is deliberately no retry around this call.
            receipt = self.facade.execute(invocation, arguments, result_ref=value.result_ref)
            receipt = AgentCapabilityResult.model_validate(receipt)
            if (receipt.invocation_id != invocation.invocation_id
                    or receipt.source_request_id != invocation.source_request_id
                    or receipt.capability != invocation.capability
                    or receipt.result_ref != value.result_ref):
                return execution_error(McpToolErrorCode.EXECUTION_FAILURE)
            if receipt.status == CapabilityStatus.ERROR:
                # Preserve canonical error category/refs, never injected prose.
                receipt = AgentCapabilityResult(**{
                    **receipt.model_dump(),
                    "error": CapabilityError(code=receipt.error.code,
                                             message=receipt.error.code.value),
                })
            return McpToolResult(result=receipt)
        except Exception:
            return execution_error(McpToolErrorCode.EXECUTION_FAILURE)
