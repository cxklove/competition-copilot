"""Pure transport adapter; no SDK, provider, persistence or business composition."""

import asyncio
import json
from typing import Protocol

from pydantic import ValidationError

from competition_copilot.agents.contracts import AgentRequest
from competition_copilot.agents.graph import GraphInput, GraphTurn
from competition_copilot.agents.human_contracts import HumanResume
from competition_copilot.integrations.agentarts.contracts import (
    AgentArtsInvocationEnvelope,
    AgentArtsInvocationResult,
    HumanReply,
    RuntimeError,
    RuntimeErrorCode,
)


class CoreAgent(Protocol):
    """Implemented by the existing CompetitionCopilotGraph; no new workflow."""
    def run_turn(self, value: GraphInput) -> GraphTurn:
        ...

    def resume(self, prior: GraphInput, response: HumanResume) -> GraphTurn:
        ...


class RuntimeBindings(Protocol):
    """Explicit trusted application boundary, never populated from SDK context.

    prepare_request resolves caller-owned arguments and correlation IDs. Resolver
    authorization, actor/current Plan/time and continuation storage are application
    responsibilities. This adapter ships no session store or implicit bindings.
    Implementations may reconstruct values from trusted JSON across processes.
    """
    def prepare_request(self, request: AgentRequest) -> GraphInput:
        ...

    def resolve_continuation(self, reference: str) -> GraphInput:
        ...

    def prepare_resume(self, prior: GraphInput, reply: HumanReply) -> HumanResume:
        ...


def _error(code: RuntimeErrorCode) -> dict:
    # No exception prose, paths, payload echoes, credentials or provider reprs.
    return AgentArtsInvocationResult(error=RuntimeError(code=code, message=code.value)).model_dump(mode="json")


class AgentArtsRuntimeAdapter:
    def __init__(self, core: CoreAgent, bindings: RuntimeBindings):
        self._core, self._bindings = core, bindings

    async def invoke(self, payload: object) -> dict:
        try:
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            # Reject live Python handles/callables and non-finite numbers before
            # typed validation; this is a JSON transport, not a service locator.
            raw = json.loads(json.dumps(payload, allow_nan=False))
            envelope = AgentArtsInvocationEnvelope.model_validate(raw)
        except (ValueError, TypeError, ValidationError, RecursionError):
            return _error(RuntimeErrorCode.INVALID_RUNTIME_PAYLOAD)
        try:
            if envelope.request is not None:
                frame = GraphInput.model_validate(await asyncio.to_thread(
                    self._bindings.prepare_request, envelope.request))
                if frame.state.request != envelope.request or frame.resume is not None:
                    raise ValueError("Application binding cannot overwrite the request")
                command = None
            else:
                frame = GraphInput.model_validate(await asyncio.to_thread(
                    self._bindings.resolve_continuation, envelope.continuation_ref))
                command = HumanResume.model_validate(await asyncio.to_thread(
                    self._bindings.prepare_resume, frame, envelope.human_reply))
                if (command.clarification or command.approval or command.message) != envelope.human_reply:
                    raise ValueError("Application binding cannot overwrite the human reply")
            frame = GraphInput.model_validate_json(frame.model_dump_json())
        except (ValueError, TypeError, ValidationError):
            return _error(RuntimeErrorCode.CORE_VALIDATION_ERROR)
        except Exception:
            return _error(RuntimeErrorCode.RUNTIME_DEPENDENCY_ERROR)
        try:
            # One synchronous core invocation in a worker, never asyncio.run in
            # an SDK event loop. All core routing/approval/explanation is reused.
            if command is None:
                turn = await asyncio.to_thread(self._core.run_turn, frame)
            else:
                turn = await asyncio.to_thread(self._core.resume, frame, command)
            turn = GraphTurn.model_validate(turn)
            if turn.response.request_id != frame.state.request.request_id:
                raise ValueError("Core result request mismatch")
            pending = turn.response.outcome in ("NEEDS_CLARIFICATION", "WAITING_FOR_APPROVAL")
            result = AgentArtsInvocationResult(response=turn.response,
                continuation=turn.continuation if pending else None)
            # Dump every Enum/URL/datetime through existing typed JSON serializers.
            return json.loads(json.dumps(result.model_dump(mode="json"), allow_nan=False))
        except (ValueError, TypeError, ValidationError):
            return _error(RuntimeErrorCode.CORE_VALIDATION_ERROR)
        except Exception:
            return _error(RuntimeErrorCode.CORE_EXECUTION_ERROR)
