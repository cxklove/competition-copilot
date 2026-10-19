"""P12 owns generated frontend contracts; parity check is offline and read-only."""

import json
import runpy
from pathlib import Path

import pytest
from pydantic import ValidationError

pytest.importorskip("langgraph", reason="Install optional agent extra for P12 runtime contract export")

from competition_copilot.agents.contracts import AgentRequest, AgentResponse
from competition_copilot.integrations.agentarts.contracts import (
    AgentArtsInvocationEnvelope,
)

ROOT = Path(__file__).resolve().parents[3]
EXPORT = runpy.run_path(str(ROOT / "scripts/export_frontend_contracts.py"))


def test_checked_in_frontend_contracts_match_pydantic():
    for name, text in EXPORT["artifacts"]().items():
        assert (ROOT / "frontend/src/runtime/generated" / name).read_text(encoding="utf-8") == text
    assert (ROOT / "frontend/tests/fixtures/runtime.json").read_text(encoding="utf-8") == EXPORT["fixtures"]()


def test_public_fixtures_use_actual_p12_contracts_and_no_internal_state():
    import json
    values = json.loads(EXPORT["fixtures"]())
    AgentRequest.model_validate(values["request"])
    for name in ("completed", "ineligible", "unknown", "clarification", "approval", "reject", "agent_error"):
        AgentResponse.model_validate(values[name]["response"])
        EXPORT["PublicRuntimeResult"].model_validate(values[name])
    for name in ("clarification_reply", "approve_reply", "reject_reply"):
        AgentArtsInvocationEnvelope.model_validate(values[name])
    assert not {"GraphInput", "AgentState", "HumanResume"} & set(EXPORT["artifacts"]()["contracts.ts"].split())


@pytest.mark.parametrize("case", json.loads(EXPORT["fixtures"]())["behavior"], ids=lambda case: case["name"])
def test_behavioral_fixture_is_defined_by_p12_public_validators(case):
    model = AgentArtsInvocationEnvelope if case["kind"] == "input" else EXPORT["PublicRuntimeResult"]
    if case["expected"] is None:
        with pytest.raises(ValidationError):
            model.model_validate(case["raw"])
    else:
        assert model.model_validate(case["raw"]).model_dump(mode="json", exclude_unset=True) == case["expected"]
