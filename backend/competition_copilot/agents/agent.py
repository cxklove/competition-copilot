"""Public request entry over the existing graph and caller-owned preparation."""

from typing import Protocol

from competition_copilot.agents.contracts import AgentRequest, AgentResponse
from competition_copilot.agents.graph import (
    CompetitionCopilotGraph,
    GraphInput,
    GraphTurn,
)
from competition_copilot.agents.human_contracts import HumanResume


class AgentInputPreparer(Protocol):
    def prepare_request(self, request: AgentRequest) -> GraphInput:
        """Prepare explicit arguments/refs; never infer business facts or consent."""
        ...


class CompetitionCopilotAgent:
    """No session storage or second routing policy; Runtime uses this same core."""

    def __init__(self, graph: CompetitionCopilotGraph, inputs: AgentInputPreparer):
        self.graph, self._inputs = graph, inputs

    def start(self, request: AgentRequest) -> GraphTurn:
        request = AgentRequest.model_validate(request)
        frame = GraphInput.model_validate(self._inputs.prepare_request(request))
        if frame.state.request != request or frame.resume is not None:
            raise ValueError("Prepared input must preserve the supplied request")
        return self.run_turn(frame)

    def invoke(self, request: AgentRequest) -> AgentResponse:
        return self.start(request).response

    def run_turn(self, frame: GraphInput) -> GraphTurn:
        return self.graph.run_turn(frame)

    def resume(self, prior: GraphInput, response: HumanResume) -> GraphTurn:
        return self.graph.resume(prior, response)
