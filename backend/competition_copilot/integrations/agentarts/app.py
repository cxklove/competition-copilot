"""Official SDK wiring only. Import this module only in the optional runtime env."""

from agentarts.sdk import AgentArtsRuntimeApp, RequestContext

from competition_copilot.integrations.agentarts.runtime import AgentArtsRuntimeAdapter


def create_app(adapter: AgentArtsRuntimeAdapter) -> AgentArtsRuntimeApp:
    """Explicit composition: no global core/session, secrets or import-time IO."""
    app = AgentArtsRuntimeApp()

    @app.entrypoint
    async def handler(payload: dict, context: RequestContext = None) -> dict:
        # Platform identity/roles/tokens are not business context or consent.
        return await adapter.invoke(payload)

    return app
