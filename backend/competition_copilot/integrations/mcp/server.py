"""SDK edge: catalog projection and guarded Facade execution, no transport app."""

import json

from mcp import MCPError
from mcp.server import Server, ServerRequestContext
from mcp.types import (
    INVALID_PARAMS,
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from competition_copilot.agents.capabilities import (
    AgentCapabilityFacade,
    CapabilityStatus,
)
from competition_copilot.integrations.mcp.contracts import (
    McpToolErrorCode,
    McpToolResult,
)
from competition_copilot.integrations.mcp.execution import (
    McpToolDispatcher,
    execution_error,
)
from competition_copilot.integrations.mcp.registry import (
    McpToolDefinition,
    McpToolRegistry,
    build_mcp_tool_registry,
)


def to_sdk_tool(definition: McpToolDefinition) -> Tool:
    """Project existing metadata, with fresh schemas and no inferred hints."""
    return Tool(
        name=definition.tool_name,
        description=definition.description,
        input_schema=definition.input_schema,
        output_schema=definition.output_schema,
    )


def map_tool_result_to_mcp(result: McpToolResult) -> CallToolResult:
    """Lossless JSON projection. Business outcome is never reclassified."""
    document = result.model_dump(mode="json")
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(
            document, sort_keys=True, allow_nan=False))],
        structured_content=document,
        is_error=(result.error is not None
                  or result.result.status == CapabilityStatus.ERROR),
    )


def build_mcp_server(
    registry: McpToolRegistry | None = None, *,
    facade: AgentCapabilityFacade | None = None,
) -> Server:
    """Construct without IO, business dependencies, session state or startup.

    Only the SDK owns protocol transport state. No context/meta becomes business
    input. Missing composition dependencies fail closed; no data paths are guessed.
    """
    registry = registry if registry is not None else build_mcp_tool_registry()
    dispatcher = McpToolDispatcher(registry, facade)

    async def list_tools(
        context: ServerRequestContext, params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        return ListToolsResult(tools=[to_sdk_tool(item) for item in registry.tools])

    async def call_tool(
        context: ServerRequestContext, params: CallToolRequestParams,
    ) -> CallToolResult:
        result = dispatcher.dispatch(params.name, params.arguments)
        if result.error and result.error.code == McpToolErrorCode.UNKNOWN_TOOL:
            raise MCPError(INVALID_PARAMS, "UNKNOWN_TOOL")
        try:
            return map_tool_result_to_mcp(result)
        except Exception:
            # Mapping failure never replays a capability or exposes the exception.
            fallback = execution_error(McpToolErrorCode.EXECUTION_FAILURE)
            return CallToolResult(
                content=[TextContent(type="text", text="EXECUTION_FAILURE")],
                structured_content=fallback.model_dump(mode="json"), is_error=True,
            )

    return Server(
        "competition-copilot", version="0.1.0",
        on_list_tools=list_tools, on_call_tool=call_tool,
    )
