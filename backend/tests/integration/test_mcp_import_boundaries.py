"""MCP package isolation and dependency consistency, without SDK imports."""

import ast
import subprocess
import sys
import textwrap
import tomllib
from importlib.metadata import distribution
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "backend/competition_copilot"


def imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            yield node.module or ""
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)


def test_sdk_imports_only_in_isolated_server_and_http_modules():
    for path in PACKAGE.rglob("*.py"):
        sdk_imports = [name for name in imports(path)
                       if name.split(".")[0] in {"mcp", "mcp_types"}]
        if path not in {PACKAGE / "integrations/mcp/server.py", PACKAGE / "integrations/mcp/http.py"}:
            assert not sdk_imports, path
        else:
            assert sdk_imports


def test_server_has_no_graph_domain_repository_or_dynamic_execution():
    path = PACKAGE / "integrations/mcp/server.py"
    assert not any(name.startswith((
                                    "competition_copilot.domain",
                                    "competition_copilot.application",
                                    "competition_copilot.infrastructure",
                                    "langgraph", "agentarts")) for name in imports(path))
    assert {name for name in imports(path) if name.startswith("competition_copilot.agents")} <= {
        "competition_copilot.agents.capabilities"}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "getattr", "open", "import_module"}
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {
                    "execute", "evaluate", "rank", "revise", "invoke", "ainvoke",
                    "read_text", "read_bytes", "streamable_http_app", "run", "bind", "listen"}


def test_execution_uses_only_facade_contracts_and_one_explicit_business_entry():
    path = PACKAGE / "integrations/mcp/execution.py"
    allowed_agent_imports = {"competition_copilot.agents.capabilities",
                             "competition_copilot.agents.contracts"}
    for name in imports(path):
        assert not name.startswith(("competition_copilot.domain", "competition_copilot.application",
                                    "competition_copilot.infrastructure", "competition_copilot.tools",
                                    "langgraph", "agentarts", "mcp"))
        if name.startswith("competition_copilot.agents"):
            assert name in allowed_agent_imports
    calls = [node for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
             if isinstance(node, ast.Call)]
    execution = [node for node in calls if isinstance(node.func, ast.Attribute)
                 and node.func.attr == "execute"]
    assert len(execution) == 1
    assert ast.unparse(execution[0].func) == "self.facade.execute"
    assert not any(isinstance(node.func, ast.Name)
                   and node.func.id in {"eval", "exec", "getattr", "open", "import_module"}
                   for node in calls)


def test_http_is_sdk_hosting_only_and_versions_stay_at_protocol_edge():
    path = PACKAGE / "integrations/mcp/http.py"
    assert set(imports(path)) == {"typing", "mcp.server", "starlette.applications"}
    calls = [node for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
             if isinstance(node, ast.Call)]
    assert len(calls) == 1
    assert ast.unparse(calls[0].func) == "server.streamable_http_app"
    for area in ("domain", "application", "tools", "agents"):
        for source in (PACKAGE / area).rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            assert "2025-11-25" not in text and "2026-07-28" not in text, source


def test_core_import_and_local_graph_work_with_sdk_imports_blocked():
    code = textwrap.dedent('''
        import sys
        import importlib.abc
        import importlib.util
        class BlockSdk(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split('.')[0] in {'mcp', 'mcp_types', 'agentarts'}:
                    raise ImportError('Optional platform SDK blocked')
        sys.meta_path.insert(0, BlockSdk())
        import competition_copilot.agents
        from competition_copilot.agents.capabilities import AgentCapabilityFacade
        from competition_copilot.agents.contracts import AgentRequest, ResultReference, ReferenceKind
        from competition_copilot.agents.state import AgentState
        from competition_copilot.integrations.mcp.registry import build_mcp_tool_registry
        assert build_mcp_tool_registry().tools
        # A standalone MCP install need not install the optional Agent framework.
        if importlib.util.find_spec('langgraph') is not None:
            from competition_copilot.agents.graph import GraphInput, build_competition_copilot_graph
            graph = build_competition_copilot_graph(AgentCapabilityFacade())
            response = graph.invoke(GraphInput(
                state=AgentState(request=AgentRequest(request_id='core', user_message='request')),
                clarification_id='clarification',
                result_ref=ResultReference(kind=ReferenceKind.TOOL_RESULT, ref_id='result')))
            assert response.outcome.value == 'NEEDS_CLARIFICATION'
        assert not {'mcp', 'mcp_types', 'agentarts'} & sys.modules.keys()
        try:
            import competition_copilot.integrations.mcp.server
        except ImportError:
            pass
        else:
            raise AssertionError('Only explicit server import requires SDK')
        print('CORE_INDEPENDENCE_PASS')
    ''')
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "CORE_INDEPENDENCE_PASS" in result.stdout


def lock_pins(path):
    pins = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("-r "):
            inherited = lock_pins(path.parent / line[3:])
            for name, req in inherited.items():
                if name in pins:
                    assert pins[name].specifier == req.specifier
                pins[name] = req
        elif line and not line.startswith("#"):
            req = Requirement(line)
            name = canonicalize_name(req.name)
            if name in pins:
                assert pins[name].specifier == req.specifier
            pins[name] = req
    return pins


def test_optional_sdk_pin_and_overlay_are_consistent():
    backend = ROOT / "backend"
    project = tomllib.loads((backend / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["optional-dependencies"]["mcp"] == ["mcp==2.3.0"]
    assert not any(Requirement(item).name in {"mcp", "mcp-types"}
                   for item in project["dependencies"])
    mcp = lock_pins(backend / "requirements-mcp.lock")
    agentarts = lock_pins(backend / "requirements-agentarts.lock")
    assert str(mcp["mcp"].specifier) == str(agentarts["mcp"].specifier) == "==2.3.0"
    assert str(mcp["mcp-types"].specifier) == "==2.3.0"
    assert "agentarts-sdk" not in mcp and "langgraph" not in mcp
    assert "mcp" not in lock_pins(backend / "requirements-agent.lock")
    # Confirm installed resolution satisfies every active locked requirement.
    pytest.importorskip("mcp", reason="Install optional MCP SDK to verify resolution")
    for name, req in mcp.items():
        if req.marker is None or req.marker.evaluate():
            assert distribution(name).version in req.specifier
