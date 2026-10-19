"""Authority boundaries and the precise end-to-end parity exclusion policy."""

import ast

import pytest

pytest.importorskip("langgraph", reason="Install optional agent extra")

from agent_e2e_support import PARITY_EXCLUSIONS, ROOT, Harness, frame, parity, semantic
from agent_e2e_support import offline as offline

from competition_copilot.agents.explanation import ExplanationDraft
from competition_copilot.agents.human_contracts import ClarificationResolutionProposal
from competition_copilot.agents.routing import IntentRoutingProposal


def imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            yield node.module or ""
        elif isinstance(node, ast.Import):
            yield from (n.name for n in node.names)


@pytest.mark.parametrize("area,banned", [
    ("domain", ("competition_copilot.agents", "agentarts", "langgraph", "langchain")),
    ("agents", ("competition_copilot.infrastructure", "agentarts")),
    ("application", ("competition_copilot.agents", "agentarts")),
    ("tools", ("competition_copilot.infrastructure", "agentarts")),
])
def test_dependency_directions_preserve_frozen_authorities(area, banned):
    for path in (ROOT / "backend/competition_copilot" / area).rglob("*.py"):
        assert not any(name.startswith(banned) for name in imports(path)), path


def test_runtime_adapter_does_not_execute_domain_authorities_or_read_files():
    directory = ROOT / "backend/competition_copilot/integrations/agentarts"
    for path in directory.glob("*.py"):
        assert not any(n.startswith("competition_copilot.infrastructure") for n in imports(path))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {
                    "evaluate", "decide", "analyze", "build", "rank", "revise", "read_text", "read_bytes"}


@pytest.mark.parametrize("contract", [IntentRoutingProposal, ExplanationDraft, ClarificationResolutionProposal])
def test_model_outputs_cannot_construct_approval_or_revision_authority(contract):
    assert not {"authority", "approval", "approval_response", "plan_diff", "replanning_input"} & set(contract.model_fields)
    assert "HUMAN_APPROVED" not in str(contract.model_json_schema())


def test_shared_composition_does_not_execute_on_construction_and_preserves_state_minimality():
    h = Harness(frame({}, "有哪些比赛？"), "DISCOVER_COMPETITIONS", "list_competitions")
    assert h.calls == [] and not h.routing.calls and not h.explanation.contexts
    value = h.agent.start(h.prepared.state.request)
    raw = value.continuation.state.model_dump(mode="json")
    assert not {"repository", "history", "conversation", "transcript", "sessions", "plan_history"} & raw.keys()
    assert h.agent.graph.compiled.checkpointer is None and h.agent.graph.compiled.store is None


def test_parity_excludes_only_transport_metadata_and_compares_every_core_field():
    h = Harness(frame({}, "有哪些比赛？"), "DISCOVER_COMPETITIONS", "list_competitions")
    response = h.agent.invoke(h.prepared.state.request)
    raw = response.model_dump(mode="json")
    wrapper = {"response": raw, "continuation": None, "error": None,
        "transport": {"request_id": "different-platform-id", "session_id": "platform-session"}}
    parity(response, wrapper)
    assert PARITY_EXCLUSIONS == ("transport wrapper", "continuation", "transport correlation metadata")
    for key, changed in (("message", "invented explanation"), ("intent", "UNKNOWN"),
                          ("request_id", "other-request"), ("audit", {"results": [], "reasons": []})):
        with pytest.raises(AssertionError):
            parity(response, {**raw, key: changed})
    with pytest.raises(AssertionError):
        semantic({**wrapper, "transport": {"approval": "APPROVE"}})
