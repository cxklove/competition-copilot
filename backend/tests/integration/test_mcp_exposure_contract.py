"""P13.1 contracts only: no MCP SDK, RPC, server, transport or network."""

import ast
import json
import socket
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from competition_copilot.agents.capabilities import (
    AgentCapabilityFacade,
    CapabilityAccess,
    CapabilityStatus,
)
from competition_copilot.agents.contracts import (
    AgentIntent,
    CapabilityId,
    CapabilityInvocationRequest,
    ReferenceKind,
    ResultReference,
)
from competition_copilot.application.eligibility import CompetitionEligibilityEvaluator
from competition_copilot.infrastructure.eligibility_policy_json import (
    JsonEligibilityPolicyProvider,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.integrations.mcp.contracts import (
    McpToolError,
    McpToolErrorCode,
    McpToolResult,
)
from competition_copilot.integrations.mcp.registry import (
    ExposureReason,
    MutationPolicy,
    build_mcp_tool_registry,
)
from competition_copilot.tools.competition import ListCompetitionsInput

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = build_mcp_tool_registry()
PAYLOADS = {
    "competition_edition_get": {"edition_id": "edition"},
    "competition_editions_list": {"competition_id": "competition"},
    "competition_get": {"competition_id": "competition"},
    "competition_list": {},
    "competition_snapshot_build": {
        "target": {"competition_id": "competition", "edition_id": "edition"},
        "observed_at": "2026-10-19T08:00:00+08:00",
    },
    "competition_track_get": {"track_id": "track"},
    "competition_tracks_list": {"edition_id": "edition"},
    "eligibility_check": {
        "student": {"id": "student"},
        "competition_id": "competition", "edition_id": "edition",
    },
}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def reject(*args, **kwargs):
        pytest.fail("MCP contracts must not access network")
    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)


def arguments(name):
    return {
        "invocation_id": "invocation", "source_request_id": "request",
        "arguments_ref": {"kind": "CAPABILITY_ARGUMENTS", "ref_id": "args"},
        "result_ref": {"kind": "TOOL_RESULT", "ref_id": "result"},
        "payload": PAYLOADS[name],
    }


def test_explicit_catalog_and_exclusions_cover_real_upstream():
    assert len(REGISTRY.tools) == 8
    approved = {m.capability: m for m in AgentCapabilityFacade().list_capabilities()}
    assert len(approved) == 16
    assert len(REGISTRY.exclusions) == 10
    assert set(x.capability_id for x in REGISTRY.tools) <= approved.keys()
    assert len({x.tool_name for x in REGISTRY.tools}) == len(REGISTRY.tools)
    for tool in REGISTRY.tools:
        assert tool.access_type == approved[tool.capability_id].access
        assert not tool.requires_explicit_approval
        assert tool.mutation_policy == MutationPolicy.NON_MUTATING
    for exclusion in REGISTRY.exclusions:
        assert not exclusion.mcp_exposed
        if exclusion.capability_id == CapabilityId.REVISE_PLAN:
            assert exclusion.mutation_policy == MutationPolicy.MUTATING_NOT_EXPOSED
    assert all(t.access_type != CapabilityAccess.MUTATING for t in REGISTRY.tools)


def test_registry_is_immutable_and_schemas_detached():
    with pytest.raises(FrozenInstanceError):
        REGISTRY.tools = ()
    with pytest.raises(FrozenInstanceError):
        REGISTRY.tools[0].tool_name = "changed"
    schema = REGISTRY.tools[0].input_schema
    schema.clear()
    assert REGISTRY.tools[0].input_schema
    with pytest.raises(ValueError, match="immutable"):
        replace(REGISTRY, tools=list(REGISTRY.tools))


def test_duplicate_names_capabilities_and_aliases_rejected():
    first, second, *rest = REGISTRY.tools
    with pytest.raises(ValueError, match="DUPLICATE_TOOL_NAME"):
        replace(REGISTRY, tools=(first, replace(second, tool_name=first.tool_name), *rest))
    with pytest.raises(ValueError, match="DUPLICATE_CAPABILITY_MAPPING"):
        replace(REGISTRY, tools=(first, replace(second, capability_id=first.capability_id), *rest))


@pytest.mark.parametrize("changes,error", [
    ({"tool_name": "competition.edition.get"}, "INVALID_TOOL_NAME"),
    ({"payload_model": ListCompetitionsInput}, "CAPABILITY_INPUT_MISMATCH"),
    ({"access_type": CapabilityAccess.DECISION}, "CAPABILITY_ACCESS_MISMATCH"),
    ({"requires_explicit_approval": True}, "MUTATION_NOT_EXPOSED"),
    ({"mutation_policy": MutationPolicy.MUTATING_NOT_EXPOSED}, "MUTATION_NOT_EXPOSED"),
])
def test_metadata_drift_rejected(changes, error):
    with pytest.raises(ValueError, match=error):
        replace(REGISTRY, tools=(replace(REGISTRY.tools[0], **changes), *REGISTRY.tools[1:]))


@pytest.mark.parametrize("capability", [CapabilityId.REVISE_PLAN,
                                      CapabilityId.CHECK_COMPETITION_CHANGES])
def test_mutation_and_unapproved_admission_rejected(capability):
    # Replace one admitted ID and balance the exclusion set to reach subset checks.
    first, *rest = REGISTRY.tools
    exclusions = tuple(replace(x, capability_id=first.capability_id,
                               reason=ExposureReason.TRUSTED_ARTIFACT_BOUNDARY_REQUIRED)
                       if x.capability_id == capability else x for x in REGISTRY.exclusions)
    exclusions = tuple(sorted(exclusions, key=lambda x: x.capability_id.value))
    with pytest.raises(ValueError, match="MUTATION_NOT_EXPOSED|UPSTREAM_CAPABILITY_NOT_EXPOSED"):
        replace(REGISTRY, tools=(replace(first, capability_id=capability), *rest),
                exclusions=exclusions)


@pytest.mark.parametrize("tool", REGISTRY.tools, ids=lambda x: x.tool_name)
def test_each_input_output_schema_and_roundtrip(tool):
    raw = arguments(tool.tool_name)
    parsed = tool.input_model.model_validate(raw)
    assert tool.input_model.model_validate_json(parsed.model_dump_json()) == parsed
    assert json.loads(json.dumps(tool.input_schema, allow_nan=False)) == tool.input_schema
    assert json.loads(json.dumps(tool.output_schema, allow_nan=False)) == tool.output_schema
    assert tool.input_schema["additionalProperties"] is False
    required = tool.payload_model.model_json_schema().get("required", [])
    for field in required:
        missing = {**raw, "payload": {k: v for k, v in raw["payload"].items() if k != field}}
        with pytest.raises(ValidationError):
            tool.input_model.model_validate(missing)
    for field in ("invocation_id", "source_request_id", "arguments_ref", "result_ref", "payload"):
        with pytest.raises(ValidationError):
            tool.input_model.model_validate({k: v for k, v in raw.items() if k != field})
    with pytest.raises(ValidationError):
        tool.input_model.model_validate({**raw, "handler": "module.call"})
    with pytest.raises(ValidationError):
        tool.input_model.model_validate({**raw, "payload": {**raw["payload"], "admin_override": True}})


def test_no_session_or_approval_or_internal_tools():
    forbidden = {"approve", "approved", "human_approved", "admin_override", "mcp_session_id"}
    for tool in REGISTRY.tools:
        schema = tool.input_schema
        properties = set(schema["properties"])
        for definition in schema.get("$defs", {}).values():
            properties.update(definition.get("properties", {}))
        assert not properties & forbidden
    for name in ("approve_plan_revision", "reject_plan_revision", "explain_replanning",
                 "clarification_interpret", "intent_interpret", "revise_plan"):
        with pytest.raises(ValueError, match="UNKNOWN_TOOL"):
            REGISTRY.get(name)


def test_aware_datetime_required_and_reference_kinds_preserved():
    tool = REGISTRY.get("competition_snapshot_build")
    raw = arguments(tool.tool_name)
    parsed = tool.input_model.model_validate(raw)
    assert parsed.payload.observed_at.utcoffset() is not None
    assert json.loads(parsed.model_dump_json())["payload"]["observed_at"] == "2026-10-19T00:00:00Z"
    with pytest.raises(ValidationError):
        tool.input_model.model_validate({**raw, "payload": {
            **raw["payload"], "observed_at": "2026-10-19T08:00:00"}})
    for field in ("arguments_ref", "result_ref"):
        with pytest.raises(ValidationError):
            tool.input_model.model_validate({**raw, field: {"kind": "AUTHORITY", "ref_id": "fake"}})


@pytest.mark.parametrize("education,expected", [("graduate", "ineligible"),
                                                  ("undergraduate", "unknown")])
def test_canonical_negative_receipt_preserves_full_evidence_and_sources(education, expected):
    # Canonical producer fixture only; no MCP execution implementation.
    facade = AgentCapabilityFacade(eligibility=CompetitionEligibilityEvaluator(
        JsonSeedCompetitionRepository(ROOT / "data/seed"),
        JsonEligibilityPolicyProvider(ROOT / "data/eligibility")))
    args_ref = ResultReference(kind=ReferenceKind.CAPABILITY_ARGUMENTS, ref_id="args")
    receipt = facade.execute(CapabilityInvocationRequest(
        invocation_id="invocation", source_request_id="request",
        intent=AgentIntent.CHECK_ELIGIBILITY, capability=CapabilityId.CHECK_ELIGIBILITY,
        arguments_ref=args_ref,
    ), {"artifact_ref": args_ref.model_dump(mode="json"), "payload": {
        "student": {"id": "student", "education_level": education},
        "competition_id": "gcxl-engineering-practice-innovation",
        "edition_id": "gcxl-engineering-practice-innovation-2027",
    }}, result_ref=ResultReference(kind=ReferenceKind.TOOL_RESULT, ref_id="result"))
    assert receipt.status == CapabilityStatus.SUCCESS
    assert receipt.data.status.value == expected
    envelope = McpToolResult(result=receipt)
    restored = McpToolResult.model_validate_json(envelope.model_dump_json())
    assert restored.result.model_dump(mode="json") == receipt.model_dump(mode="json")
    assert restored.result.audit == receipt.audit
    assert receipt.audit.reasons
    assert {ReferenceKind.EVIDENCE, ReferenceKind.SOURCE} <= {
        ref.kind for ref in receipt.audit.results}
    source = restored.result.data.evidence[0].source
    assert str(source.source_url) == str(receipt.data.evidence[0].source.source_url)
    assert source.observed_at.tzinfo is not None
    assert source.verification_status.value == "verified"
    document = envelope.model_dump(mode="json")
    assert document["result"]["data"]["evidence"][0]["source"] == source.model_dump(mode="json")


def test_safe_error_contract_distinct_from_domain_receipt():
    for code in McpToolErrorCode:
        error = McpToolResult(error=McpToolError(code=code))
        assert McpToolResult.model_validate_json(error.model_dump_json()) == error
    with pytest.raises(ValidationError):
        McpToolError(code="INELIGIBLE")
    with pytest.raises(ValidationError):
        McpToolError(code="EXECUTION_FAILURE", message="secret C:/private")
    with pytest.raises(ValidationError):
        McpToolResult()


def test_deterministic_catalog_names_and_schema_order():
    second = build_mcp_tool_registry()
    assert REGISTRY == second
    assert [t.tool_name for t in second.tools] == sorted(t.tool_name for t in second.tools)
    assert [(t.tool_name, t.input_schema, t.output_schema) for t in REGISTRY.tools] == [
        (t.tool_name, t.input_schema, t.output_schema) for t in second.tools]
    with pytest.raises(ValueError, match="UNORDERED_TOOL_CATALOG"):
        replace(REGISTRY, tools=tuple(reversed(REGISTRY.tools)))


def test_contract_package_has_no_server_io_or_authority_execution():
    folder = ROOT / "backend/competition_copilot/integrations/mcp"
    for path in folder.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith(("mcp", "agentarts", "competition_copilot.infrastructure",
                                               "competition_copilot.agents.graph"))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"execute", "evaluate", "revise", "invoke", "ainvoke"}
