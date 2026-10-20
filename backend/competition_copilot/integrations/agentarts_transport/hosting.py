"""Public hosting projection around the existing SDK/pure invocation boundary."""


def create_hosted_app(host):
    # Optional SDK import stays here; no SDK/cloud is needed by bridge or Local.
    # Reuse P12.7's registered entrypoint. host.invoke calls the original pure
    # adapter and retains GraphInput privately, returning only opaque handles/data.
    from competition_copilot.integrations.agentarts.app import create_app

    return create_app(host)
