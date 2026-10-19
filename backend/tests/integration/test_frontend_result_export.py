"""Offline readonly artifact projection parity; never a business authority."""

import json
import runpy
from pathlib import Path

import pytest

pytest.importorskip("langgraph", reason="Install agent extra for P12 consumer parity")

from competition_copilot.agents.contracts import AgentResponse

ROOT = Path(__file__).resolve().parents[3]
EXPORT = runpy.run_path(str(ROOT / "scripts/export_frontend_results.py"))
CASES = json.loads(EXPORT["fixtures"]())


def test_readonly_artifact_projection_matches_existing_pydantic_models():
    for name, content in EXPORT["artifacts"]().items():
        assert (ROOT / "frontend/src/results/generated" / name).read_text(encoding="utf-8") == content
    assert (ROOT / "frontend/src/demo/result-fixtures.json").read_text(encoding="utf-8") == EXPORT["fixtures"]()


@pytest.mark.parametrize("name", CASES)
def test_fixture_artifacts_are_canonical_domain_data_bound_to_public_response(name):
    case = CASES[name]
    response = AgentResponse.model_validate(case["runtime"]["response"])
    assert response.request_id == case["bundle"]["request_id"]
    refs = [ref.model_dump() for ref in response.audit.results]
    for entry in case["bundle"]["artifacts"]:
        assert entry["ref"] in refs
        canonical = EXPORT["MODEL_BY_NAME"][entry["model"]].model_validate(entry["value"])
        assert canonical.model_dump(mode="json") == entry["value"]
