"""Read-only, eagerly loaded P5 eligibility policy JSON adapter."""

from pathlib import Path
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from competition_copilot.application.eligibility import EligibilityPolicyProvider
from competition_copilot.domain.eligibility_policy import EligibilityPolicy


class EligibilityPolicyLoadError(ValueError):
    def __init__(self, reason: str, artifact_path: Path) -> None:
        self.reason = reason
        self.artifact_path = artifact_path
        super().__init__(f"{reason}: {artifact_path}")


class _PolicyArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    artifact_type: Literal["eligibility_policy"]
    policy: EligibilityPolicy


class JsonEligibilityPolicyProvider(EligibilityPolicyProvider):
    """Snapshot of validated P5 policy files; unrelated to P2 Seed artifacts."""

    def __init__(self, policy_dir: Path) -> None:
        if not policy_dir.is_dir():
            raise EligibilityPolicyLoadError("POLICY_DIRECTORY_INVALID", policy_dir)
        policies: dict[tuple[str, str, str | None], EligibilityPolicy] = {}
        for path in sorted(policy_dir.glob("*.json"), key=lambda item: item.name):
            try:
                artifact = _PolicyArtifact.model_validate_json(path.read_bytes())
            except (OSError, ValidationError) as exc:
                raise EligibilityPolicyLoadError("POLICY_ARTIFACT_INVALID", path) from exc
            policy = artifact.policy
            key = (policy.competition_id, policy.edition_id, policy.track_id)
            if key in policies:
                raise EligibilityPolicyLoadError("DUPLICATE_POLICY_TARGET", path)
            policies[key] = policy
        self._policies = MappingProxyType(policies)

    def get_policy(
        self, competition_id: str, edition_id: str, track_id: str | None = None
    ) -> EligibilityPolicy | None:
        policy = self._policies.get((competition_id, edition_id, track_id))
        return policy.model_copy(deep=True) if policy is not None else None
