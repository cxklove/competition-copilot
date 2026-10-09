"""Explicit human review decisions bound to exact Raw fixture bytes."""

import hashlib
import re
from enum import Enum
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    field_validator,
    model_validator,
)

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    HOLD = "hold"


class SourceVerificationDecision(str, Enum):
    VERIFY = "verify"
    HOLD = "hold"


class HumanReviewEntry(BaseModel):
    """Record human decision times, never later workflow execution times."""

    model_config = ConfigDict(extra="forbid")

    raw_fixture_path: str
    raw_sha256: str
    competition_id: str
    edition_id: str
    candidate_id: str
    approval_decision: ApprovalDecision
    approval_decided_at: AwareDatetime | None = None
    review_note: str | None = None
    source_verification_decision: SourceVerificationDecision
    source_verification_decided_at: AwareDatetime | None = None
    verification_note: str | None = None

    @field_validator("raw_fixture_path", "competition_id", "edition_id", "candidate_id")
    @classmethod
    def require_nonblank_identifier(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("raw_sha256")
    @classmethod
    def require_sha256(cls, value: str) -> str:
        if _SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("raw_sha256 must be 64 lowercase hexadecimal characters")
        return value

    @model_validator(mode="after")
    def require_explicit_decisions(self) -> Self:
        if self.approval_decision in (ApprovalDecision.APPROVE, ApprovalDecision.REJECT):
            if self.approval_decided_at is None:
                raise ValueError("approval_decided_at is required for approve or reject")
        if self.review_note is None or not self.review_note.strip():
            raise ValueError("review_note is required for every approval decision")
        if self.source_verification_decision is SourceVerificationDecision.VERIFY:
            if self.approval_decision is not ApprovalDecision.APPROVE:
                raise ValueError("verify requires an approve decision")
            if self.source_verification_decided_at is None:
                raise ValueError("source_verification_decided_at is required for verify")
            if self.verification_note is None or not self.verification_note.strip():
                raise ValueError("verification_note is required for verify")
        return self


class HumanReviewManifest(BaseModel):
    """Versioned collection of explicit human decisions; empty is valid."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    artifact_type: Literal["human_review_manifest"]
    entries: list[HumanReviewEntry]

    @model_validator(mode="after")
    def require_unique_entries(self) -> Self:
        raw_paths = [entry.raw_fixture_path for entry in self.entries]
        candidate_ids = [entry.candidate_id for entry in self.entries]
        if len(raw_paths) != len(set(raw_paths)):
            raise ValueError("raw_fixture_path must be unique within a manifest")
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate_id must be unique within a manifest")
        return self


class RawBindingError(ValueError):
    """The current Raw fixture cannot be used with a recorded human decision."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def compute_file_sha256(path: str | Path) -> str:
    """Hash the exact file bytes without parsing or changing the file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_raw_binding(entry: HumanReviewEntry, project_root: str | Path) -> None:
    """Reject a decision when its Raw file is missing or has changed."""

    root = Path(project_root).resolve()
    path = (root / entry.raw_fixture_path).resolve()
    if not path.is_relative_to(root):
        raise RawBindingError(
            "RAW_FIXTURE_PATH_OUTSIDE_PROJECT",
            "raw_fixture_path must resolve within project_root",
        )
    try:
        current_sha256 = compute_file_sha256(path)
    except OSError as exc:
        raise RawBindingError(
            "RAW_FIXTURE_UNAVAILABLE", f"cannot read Raw fixture: {entry.raw_fixture_path}"
        ) from exc
    if current_sha256 != entry.raw_sha256:
        raise RawBindingError(
            "RAW_FIXTURE_CHANGED_AFTER_REVIEW",
            f"Raw fixture changed after human review: {entry.raw_fixture_path}",
        )


def serialize_review_manifest(manifest: HumanReviewManifest) -> bytes:
    """Serialize the versioned manifest as indented UTF-8 JSON."""

    return manifest.model_dump_json(indent=2).encode("utf-8")


def deserialize_review_manifest(payload: bytes | str) -> HumanReviewManifest:
    """Load a manifest through its formal schema without executing decisions."""

    return HumanReviewManifest.model_validate_json(payload)
