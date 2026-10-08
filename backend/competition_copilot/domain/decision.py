from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from competition_copilot.domain.source_metadata import SourceMetadata


class DecisionStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class Evidence(BaseModel):
    """A structured piece of evidence cited by a business conclusion."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    source: SourceMetadata | None = None
    field: str | None = None
    value: str | int | float | bool | None = None

    @field_validator("code", "message", "field")
    @classmethod
    def strip_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("value", mode="before")
    @classmethod
    def require_simple_scalar(cls, value: object) -> object:
        if value is not None and type(value) not in (str, int, float, bool):
            raise ValueError("value must be a simple scalar or None")
        return value


class DecisionResult(BaseModel):
    """A status with reason codes and evidence from a deterministic decision."""

    model_config = ConfigDict(extra="forbid")

    status: DecisionStatus
    reason_codes: list[str]
    evidence: list[Evidence] = Field(default_factory=list)

    @field_validator("reason_codes")
    @classmethod
    def normalize_reason_codes(cls, reason_codes: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for reason_code in reason_codes:
            stripped = reason_code.strip()
            if not stripped:
                raise ValueError("reason_codes must not contain blank values")
            if stripped not in seen:
                seen.add(stripped)
                normalized.append(stripped)
        return normalized
