"""Plan storage contract; references select state, never grant approval."""

from typing import Protocol

from competition_copilot.domain.plan import CompetitionPlan
from competition_copilot.domain.replanning import PlanDiff, PlanReference


class PlanRegistry(Protocol):
    """One current head per lineage; exact historical snapshots remain available."""

    def register(self, plan: CompetitionPlan) -> PlanReference: ...

    def resolve(self, reference: PlanReference) -> CompetitionPlan: ...

    def get_current(self, plan_id: str) -> CompetitionPlan: ...

    def replace_current(
        self, expected_before: PlanReference, after: CompetitionPlan, *, plan_diff: PlanDiff,
    ) -> PlanReference: ...

    def history(self, plan_id: str) -> tuple[CompetitionPlan, ...]: ...

    def revisions(self, plan_id: str) -> tuple[PlanDiff, ...]: ...
