"""Read-only P7 data abstraction; no gap computation or target discovery."""

from typing import Protocol

from competition_copilot.domain.skill_gap import SkillRequirementSet
from competition_copilot.domain.skill_requirement_artifact import (
    SkillRequirementSetEnvelope,
)


class SkillRequirementProvider(Protocol):
    """Exact target data access. None means no artifact, never empty COMPLETE.

    Caller validates target existence/relationships via CompetitionRepository.
    P7.4 may map absence to an explicit MISSING SkillRequirementSet.
    """

    def get_requirements(
        self, competition_id: str, edition_id: str, track_id: str | None = None
    ) -> SkillRequirementSet | None: ...

    def list_artifacts(self) -> tuple[SkillRequirementSetEnvelope, ...]:
        """Validated reviewed snapshots in deterministic discovery order."""
        ...
