"""Ephemeral local hosting: public handles, never browser GraphInput or authority."""

import asyncio
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable

from pydantic import ValidationError

from competition_copilot.agents.contracts import AgentRequest
from competition_copilot.agents.graph import GraphInput
from competition_copilot.application.plans import PlanRegistry
from competition_copilot.integrations.agentarts.contracts import (
    AgentArtsInvocationEnvelope,
    AgentArtsInvocationResult,
)
from competition_copilot.integrations.agentarts.runtime import AgentArtsRuntimeAdapter


@dataclass
class LocalSession:
    adapter: AgentArtsRuntimeAdapter
    retain: Callable[[str, GraphInput], None]
    presentation: Callable[[dict], dict]


class ReplanningInputUnavailable(ValueError):
    """A resolved plan has no supported target-consistent executable proposal."""


def failure(code, message=None):
    return {"runtime": {"error": {"code": code, "message": message or code}}, "presentation": None}


class LocalInvocationHost:
    """One explicitly authorized local operator; not production authentication.

    Handles are random, bounded, expiring, single-use lookup references. They never
    replace P12 identity/Plan checks. No cookies or platform metadata enter core.
    A host lock serializes resolution/validation/execution for stale-Plan safety.
    No durable storage or restart/reload resume guarantee.
    """

    def __init__(self, factory: Callable[[AgentRequest], LocalSession], *, capacity=128, ttl=600,
                 plan_registry: PlanRegistry | None = None):
        self.factory, self.capacity, self.ttl = factory, capacity, ttl
        self.plan_registry = plan_registry
        self._pending = {}
        self._lock = threading.Lock()
        self.handler_invocations = 0

    async def invoke(self, payload):
        try:
            envelope = AgentArtsInvocationEnvelope.model_validate(payload)
        except ValidationError as exc:
            # Preserve safe field diagnostics without leaking Pydantic input or traceback.
            fields = {str(part) for error in exc.errors() for part in error["loc"]}
            message = None
            if "skill_command" in fields:
                message = "INVALID_SKILL_LEVEL" if "level" in fields else "INVALID_PROFILE_FIELD"
            if "my_competition_command" in fields and "edition_id" in fields:
                message = "TARGET_INCOMPLETE: EDITION_REQUIRED"
            if "profile_update" in fields:
                message = ("INVALID_WEEKLY_HOURS" if "weekly_available_hours" in fields else
                           "INVALID_EDUCATION_LEVEL" if "education_level" in fields else
                           "INVALID_PROFILE_FIELD")
            return failure("INVALID_RUNTIME_PAYLOAD", message)
        except Exception:
            return failure("INVALID_RUNTIME_PAYLOAD")
        await asyncio.to_thread(self._lock.acquire)
        try:
            now = time.monotonic()
            self._pending = {key: item for key, item in self._pending.items() if item[0] > now}
            if envelope.request is not None:
                session = self.factory(envelope.request)
            else:
                entry = self._pending.pop(envelope.continuation_ref, None)
                if entry is None:
                    return failure("CORE_VALIDATION_ERROR")
                session = entry[1]
            self.handler_invocations += 1
            raw = await session.adapter.invoke(envelope.model_dump(mode="json", exclude_none=True))
            result = AgentArtsInvocationResult.model_validate(raw)
            public = {"response": raw["response"], "error": raw["error"]}
            if result.continuation is not None:
                if len(self._pending) >= self.capacity:
                    return failure("RUNTIME_DEPENDENCY_ERROR")
                handle = secrets.token_urlsafe(32)
                session.retain(handle, result.continuation)
                self._pending[handle] = (time.monotonic() + self.ttl, session)
                public["continuation_ref"] = handle
            # Explicit transport delivery, not a new AgentResponse. No internal
            # continuation, receipt authority, actor or execution context escapes.
            return {"runtime": public,
                    "presentation": session.presentation(raw["response"]) if result.response else None}
        except ReplanningInputUnavailable:
            return failure("CORE_VALIDATION_ERROR", "NO_TARGET_CONSISTENT_REPLANNING_INPUT")
        except ValueError:
            return failure("CORE_VALIDATION_ERROR")
        except Exception:
            return failure("RUNTIME_DEPENDENCY_ERROR")
        finally:
            self._lock.release()
