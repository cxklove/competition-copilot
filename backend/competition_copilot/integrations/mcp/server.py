"""SDK catalog edge only. Business tool execution is deferred to P13.3."""

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


def build_mcp_server(registry: McpToolRegistry | None = None) -> Server:
    """Construct without IO, business dependencies, session state or startup.

    Only the SDK owns protocol transport state. No context/meta becomes business
    input. An explicit P13.3 change is required to admit capability execution.
    """
    registry = registry if registry is not None else build_mcp_tool_registry()

    async def list_tools(
        context: ServerRequestContext, params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        return ListToolsResult(tools=[to_sdk_tool(item) for item in registry.tools])

    async def execution_disabled(
        context: ServerRequestContext, params: CallToolRequestParams,
    ) -> CallToolResult:
        try:
            registry.get(params.name)
        except ValueError:
            raise MCPError(INVALID_PARAMS, "UNKNOWN_TOOL") from None
        return CallToolResult(
            content=[TextContent(type="text", text="NOT_IMPLEMENTED_P13_3")],
            is_error=True,
        )

    return Server(
        "competition-copilot", version="0.1.0",
        on_list_tools=list_tools, on_call_tool=execution_disabled,
    )
