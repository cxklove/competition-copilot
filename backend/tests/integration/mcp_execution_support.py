"""Offline fixture composition for P13.3; real P4/P5/P9, no runtime wiring."""

from pathlib import Path

from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.agents.contracts import CapabilityId
from competition_copilot.application.competition_snapshots import (
    CompetitionSnapshotBuilder,
)
from competition_copilot.application.eligibility import CompetitionEligibilityEvaluator
from competition_copilot.infrastructure.eligibility_policy_json import (
    JsonEligibilityPolicyProvider,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.tools.competition import (
    GetCompetitionEditionTool,
    GetCompetitionTool,
    GetCompetitionTrackTool,
    ListCompetitionEditionsTool,
    ListCompetitionsTool,
    ListEditionTracksTool,
)

ROOT = Path(__file__).resolve().parents[3]
COMPETITION = "gcxl-engineering-practice-innovation"
EDITION = "gcxl-engineering-practice-innovation-2027"


class RecordingFacade(AgentCapabilityFacade):
    def __init__(self, **dependencies):
        super().__init__(**dependencies)
        self.calls = []

    def execute(self, invocation, arguments, *, result_ref):
        self.calls.append((invocation, arguments, result_ref))
        return super().execute(invocation, arguments, result_ref=result_ref)


def real_facade():
    repository = JsonSeedCompetitionRepository(ROOT / "data/seed")
    return RecordingFacade(
        read_tools={
            CapabilityId.LIST_COMPETITIONS: ListCompetitionsTool(repository),
            CapabilityId.GET_COMPETITION: GetCompetitionTool(repository),
            CapabilityId.LIST_EDITIONS: ListCompetitionEditionsTool(repository),
            CapabilityId.GET_EDITION: GetCompetitionEditionTool(repository),
            CapabilityId.LIST_TRACKS: ListEditionTracksTool(repository),
            CapabilityId.GET_TRACK: GetCompetitionTrackTool(repository),
        },
        eligibility=CompetitionEligibilityEvaluator(
            repository, JsonEligibilityPolicyProvider(ROOT / "data/eligibility")),
        snapshot_builder=CompetitionSnapshotBuilder(repository),
    )


def arguments(payload=None):
    return {
        "invocation_id": "mcp-invocation", "source_request_id": "mcp-request",
        "arguments_ref": {"kind": "CAPABILITY_ARGUMENTS", "ref_id": "mcp-arguments"},
        "result_ref": {"kind": "TOOL_RESULT", "ref_id": "mcp-result"},
        "payload": {} if payload is None else payload,
    }


def eligibility_payload(education="graduate"):
    return {"student": {"id": "mcp-student", "education_level": education},
            "competition_id": COMPETITION, "edition_id": EDITION}
