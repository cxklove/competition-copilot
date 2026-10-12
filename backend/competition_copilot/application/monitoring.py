"""Source observation capability; concrete source adapters belong to Infrastructure."""

from typing import Protocol

from competition_copilot.domain.monitoring import (
    MonitorCheckRequest,
    SourceObservationResult,
)


class CompetitionObservationSource(Protocol):
    """Observe a stable target once using explicit time/source context.

    Expected external failures return typed CHECK_FAILED, never invented UNKNOWN
    facts. Contract/programmer errors may raise. No Repository writes, HTTP API,
    retry/schedule policy or execution-model requirement is exposed here.
    """

    def observe(self, request: MonitorCheckRequest) -> SourceObservationResult: ...
