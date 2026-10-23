"""Explicit outer composition root; construction only, no decision execution.

Concrete data adapters belong here, outside Agent/Tool/Domain dependencies.
There are no default paths, clocks, profiles, scoring policies or model providers.
"""

from dataclasses import dataclass
from pathlib import Path

from competition_copilot.agents.agent import AgentInputPreparer, CompetitionCopilotAgent
from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.agents.contracts import CapabilityId
from competition_copilot.agents.explanation import ExplanationModel
from competition_copilot.agents.graph import build_competition_copilot_graph
from competition_copilot.agents.human_contracts import HumanResponseInterpreter
from competition_copilot.agents.routing import IntentModel
from competition_copilot.application.competition_detail import CompetitionDetailReader
from competition_copilot.application.competition_snapshots import (
    CompetitionSnapshotBuilder,
)
from competition_copilot.application.eligibility import CompetitionEligibilityEvaluator
from competition_copilot.application.skill_requirements import SkillRequirementProvider
from competition_copilot.application.temporal_evidence import TemporalEvidenceProvider
from competition_copilot.domain.baseline_plan_builder import (
    BaselineCompetitionPlanBuilder,
)
from competition_copilot.domain.event_aggregation import CompetitionEventAggregator
from competition_copilot.domain.event_engine import CompetitionEventEngine
from competition_copilot.domain.event_impact_analyzer import (
    CompetitionEventImpactAnalyzer,
)
from competition_copilot.domain.plan_revision_service import PlanRevisionService
from competition_copilot.domain.planning_inputs import PlanningInputDeriver
from competition_copilot.domain.recommendation_ranking import (
    RecommendationRankingEngine,
)
from competition_copilot.domain.recommendation_scoring import (
    RecommendationScoringEngine,
)
from competition_copilot.domain.replanning_decision_service import (
    ReplanningDecisionService,
)
from competition_copilot.domain.skill_gap_engine import SkillGapEngine
from competition_copilot.domain.snapshot_diff_engine import SnapshotDiffEngine
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
from competition_copilot.tools.competition_detail import GetCompetitionDetailsTool


@dataclass(frozen=True)
class AgentComposition:
    agent: CompetitionCopilotAgent
    facade: AgentCapabilityFacade


def build_seed_agent(
    *, seed_directory: Path, policy_directory: Path,
    inputs: AgentInputPreparer, scoring: RecommendationScoringEngine,
    intent_model: IntentModel | None = None,
    explanation_model: ExplanationModel | None = None,
    human_interpreter: HumanResponseInterpreter | None = None,
    requirement_provider: SkillRequirementProvider | None = None,
    temporal_evidence: TemporalEvidenceProvider | None = None,
) -> AgentComposition:
    """Assemble the frozen authorities; caller supplies every workflow argument.

    P6's soft scorers remain explicitly injected. None are invented by this root.
    The optional Agent stack is loaded only when this module is explicitly used.
    """
    repository = JsonSeedCompetitionRepository(seed_directory)
    policies = JsonEligibilityPolicyProvider(policy_directory)
    facade = AgentCapabilityFacade(
        read_tools={
            **({CapabilityId.GET_COMPETITION_DETAILS: GetCompetitionDetailsTool(
                CompetitionDetailReader(repository, policies, requirement_provider, repository,
                                        temporal_evidence))}
               if requirement_provider is not None else {}),
            CapabilityId.LIST_COMPETITIONS: ListCompetitionsTool(repository),
            CapabilityId.GET_COMPETITION: GetCompetitionTool(repository),
            CapabilityId.LIST_EDITIONS: ListCompetitionEditionsTool(repository),
            CapabilityId.GET_EDITION: GetCompetitionEditionTool(repository),
            CapabilityId.LIST_TRACKS: ListEditionTracksTool(repository),
            CapabilityId.GET_TRACK: GetCompetitionTrackTool(repository),
        },
        eligibility=CompetitionEligibilityEvaluator(repository, policies),
        scoring=scoring, ranking=RecommendationRankingEngine(),
        skill_gap=SkillGapEngine(), planning_inputs=PlanningInputDeriver(),
        planner=BaselineCompetitionPlanBuilder(),
        snapshot_builder=CompetitionSnapshotBuilder(repository), snapshot_diff=SnapshotDiffEngine(),
        event_engine=CompetitionEventEngine(), event_aggregator=CompetitionEventAggregator(),
        impact=CompetitionEventImpactAnalyzer(), replanning=ReplanningDecisionService(),
        revision=PlanRevisionService(),
    )
    graph = build_competition_copilot_graph(facade, intent_model=intent_model,
        explanation_model=explanation_model, human_interpreter=human_interpreter)
    return AgentComposition(CompetitionCopilotAgent(graph, inputs), facade)
