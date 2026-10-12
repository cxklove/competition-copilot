"""Read-only eager loader for reviewed P7 requirement JSON, independent of P2."""

from pathlib import Path
from types import MappingProxyType

from pydantic import ValidationError

from competition_copilot.application.skill_requirements import SkillRequirementProvider
from competition_copilot.domain.skill_gap import SkillRequirementSet
from competition_copilot.domain.skill_requirement_artifact import (
    SkillRequirementSetEnvelope,
)


class SkillRequirementLoadError(ValueError):
    def __init__(self, reason: str, artifact_path: Path) -> None:
        self.reason = reason
        self.artifact_path = artifact_path
        super().__init__(f"{reason}: {artifact_path}")


class JsonSkillRequirementProvider(SkillRequirementProvider):
    """Atomic artifact snapshot; no Repository, student data, inference or writes."""

    def __init__(self, requirement_dir: Path) -> None:
        if not requirement_dir.is_dir():
            raise SkillRequirementLoadError("REQUIREMENT_DIRECTORY_INVALID", requirement_dir)
        artifacts = {}
        catalog = {}
        for path in sorted(requirement_dir.glob("*.json"), key=lambda item: item.name):
            try:
                artifact = SkillRequirementSetEnvelope.model_validate_json(path.read_bytes())
            except (OSError, ValidationError) as exc:
                raise SkillRequirementLoadError("REQUIREMENT_ARTIFACT_INVALID", path) from exc
            target = artifact.requirement_set.target
            key = (target.competition_id, target.edition_id, target.track_id)
            if key in artifacts:
                raise SkillRequirementLoadError("DUPLICATE_REQUIREMENT_TARGET", path)
            for skill in artifact.skills:
                if skill.id in catalog and catalog[skill.id] != skill:
                    raise SkillRequirementLoadError("CONFLICTING_SKILL_IDENTITY", path)
                catalog[skill.id] = skill
            artifacts[key] = artifact
        self._artifacts = MappingProxyType(artifacts)

    def get_requirements(
        self, competition_id: str, edition_id: str, track_id: str | None = None
    ) -> SkillRequirementSet | None:
        artifact = self._artifacts.get((competition_id, edition_id, track_id))
        return artifact.requirement_set if artifact is not None else None

    def list_artifacts(self) -> tuple[SkillRequirementSetEnvelope, ...]:
        return tuple(self._artifacts.values())
