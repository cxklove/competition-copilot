"""Thread-safe ephemeral PlanRegistry adapter. No planning/approval decisions."""

from threading import RLock

from competition_copilot.domain.plan import CompetitionPlan
from competition_copilot.domain.replanning import PlanDiff, PlanReference


class InMemoryPlanRegistry:
    """Detached full snapshots, immutable history and atomic lineage-head CAS.

    P11 can change plan ID on revision. Every retained ID resolves the same
    lineage's current head; exact resolve still returns the requested snapshot.
    Registration cannot bypass replacement by reusing a known historical ID.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._plans: dict[str, CompetitionPlan] = {}
        self._roots: dict[str, str] = {}
        self._heads: dict[str, str] = {}
        self._history: dict[str, tuple[str, ...]] = {}
        self._diffs: dict[str, tuple[PlanDiff, ...]] = {}

    def register(self, plan: CompetitionPlan) -> PlanReference:
        snapshot = CompetitionPlan.model_validate(plan.model_dump())
        reference = PlanReference.from_plan(snapshot)
        with self._lock:
            existing = self._plans.get(snapshot.id)
            if existing is not None:
                if PlanReference.from_plan(existing) != reference:
                    raise ValueError("Plan registration conflict")
                return reference  # Never reset a lineage head to an old version.
            self._plans[snapshot.id] = snapshot
            self._roots[snapshot.id] = snapshot.id
            self._heads[snapshot.id] = snapshot.id
            self._history[snapshot.id] = (snapshot.id,)
            self._diffs[snapshot.id] = ()
        return reference

    def resolve(self, reference: PlanReference) -> CompetitionPlan:
        reference = PlanReference.model_validate(reference)
        with self._lock:
            plan = self._plans.get(reference.plan_id)
            if plan is None or PlanReference.from_plan(plan) != reference:
                raise ValueError("Unknown exact Plan reference")
            return CompetitionPlan.model_validate(plan.model_dump())

    def _root(self, plan_id: str) -> str:
        if plan_id not in self._roots:
            raise ValueError("Unknown Plan lineage")
        return self._roots[plan_id]

    def get_current(self, plan_id: str) -> CompetitionPlan:
        with self._lock:
            plan = self._plans[self._heads[self._root(plan_id)]]
            return CompetitionPlan.model_validate(plan.model_dump())

    def replace_current(
        self, expected_before: PlanReference, after: CompetitionPlan, *, plan_diff: PlanDiff,
    ) -> PlanReference:
        expected_before = PlanReference.model_validate(expected_before)
        snapshot = CompetitionPlan.model_validate(after.model_dump())
        diff = PlanDiff.model_validate(plan_diff.model_dump())
        with self._lock:
            root = self._root(expected_before.plan_id)
            before = self.get_current(expected_before.plan_id)
            if PlanReference.from_plan(before) != expected_before:
                raise ValueError("Stale current Plan")
            if diff.before != before or diff.after != snapshot:
                raise ValueError("Revision lineage must retain exact before/after")
            if snapshot == before:
                return expected_before
            if snapshot.id in self._plans:
                raise ValueError("Revision Plan identity already registered")
            self._plans[snapshot.id] = snapshot
            self._roots[snapshot.id] = root
            self._heads[root] = snapshot.id
            self._history[root] += (snapshot.id,)
            self._diffs[root] += (diff,)
            return PlanReference.from_plan(snapshot)

    def history(self, plan_id: str) -> tuple[CompetitionPlan, ...]:
        with self._lock:
            return tuple(CompetitionPlan.model_validate(self._plans[key].model_dump())
                         for key in self._history[self._root(plan_id)])

    def revisions(self, plan_id: str) -> tuple[PlanDiff, ...]:
        with self._lock:
            return tuple(PlanDiff.model_validate(diff.model_dump())
                         for diff in self._diffs[self._root(plan_id)])
