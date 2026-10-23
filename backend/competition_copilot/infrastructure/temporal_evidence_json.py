"""Load explicitly admitted quotes once. No extraction on detail requests."""

import json
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from competition_copilot.application.temporal_evidence import TemporalCandidateSnapshot
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    SourceType,
    VerificationStatus,
)
from competition_copilot.repositories.provenance import CompetitionProvenanceReader


class TemporalAdmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    review_reference: str
    candidate_id: str
    decision: Literal["admit", "reject"]


class TemporalEvidenceArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"]
    artifact_type: Literal["reviewed_temporal_evidence"]
    candidates: tuple[TemporalCandidateSnapshot, ...]
    admissions: tuple[TemporalAdmission, ...]


class JsonTemporalEvidenceProvider:
    def __init__(self, artifact_path: Path, project_root: Path,
                 provenance: CompetitionProvenanceReader):
        root = project_root.resolve()
        artifact = TemporalEvidenceArtifact.model_validate_json(artifact_path.read_bytes())
        admissions = {a.review_reference: a for a in artifact.admissions}
        if len(admissions) != len(artifact.admissions):
            raise ValueError("Duplicate temporal admission")
        ids = set()
        for candidate in artifact.candidates:
            if candidate.candidate_id in ids:
                raise ValueError("Duplicate temporal candidate")
            ids.add(candidate.candidate_id)
            admission = admissions.get(candidate.review_reference)
            if admission is None or admission.candidate_id != candidate.candidate_id:
                raise ValueError("Temporal admission content binding mismatch")
            if (admission.decision == "reject") != (
                candidate.verification_status is VerificationStatus.REJECTED
            ):
                raise ValueError("Temporal admission status mismatch")
            raw_path = (root / candidate.raw_reference).resolve()
            if not raw_path.is_relative_to(root) or not raw_path.is_relative_to((root / "data/raw").resolve()):
                raise ValueError("Temporal raw path outside fixture directory")
            raw_bytes = raw_path.read_bytes()
            if sha256(raw_bytes).hexdigest() != candidate.raw_digest:
                raise ValueError("Temporal raw digest mismatch")
            raw = json.loads(raw_bytes)
            if (raw.get("competition_id"), raw.get("edition_id")) != (
                candidate.competition_id, candidate.edition_id
            ):
                raise ValueError("Temporal raw target mismatch")
            # Initial artifacts only admit edition evidence. Track presence in a
            # page inventory is not proof that a quoted date applies to that track.
            if candidate.track_id is not None:
                raise ValueError("Track temporal admission requires independent scope evidence")
            field_name = candidate.text_locator.removeprefix("/raw_payload/")
            allowed = ("registration_text",) if candidate.field.startswith("registration") else (
                "competition_text", "schedule_text")
            text = raw.get("raw_payload", {}).get(field_name)
            if field_name not in allowed or not isinstance(text, str) or candidate.raw_text not in text:
                raise ValueError("Temporal field / quote locator mismatch")
            source = SourceMetadata(source_url=raw["source_url"], source_type=raw["source_type"],
                observed_at=raw["observed_at"], verification_status=candidate.source.verification_status)
            if source != candidate.source:
                raise ValueError("Temporal raw source mismatch")
            if not any(p.section == "edition" and p.source == candidate.source
                       for p in provenance.read_provenance(candidate.competition_id,
                                                           candidate.edition_id)):
                raise ValueError("Temporal source not bound to reviewed edition provenance")
        if set(admissions) != {c.review_reference for c in artifact.candidates}:
            raise ValueError("Unused temporal admission")
        self._candidates = artifact.candidates

    def read_candidates(self, competition_id: str, edition_id: str,
                        track_id: str | None = None) -> tuple[TemporalCandidateSnapshot, ...]:
        return tuple(c for c in self._candidates if (
            c.competition_id == competition_id and c.edition_id == edition_id
            and c.track_id in (None, track_id)
            and c.verification_status is VerificationStatus.PENDING
            and c.source.source_type is SourceType.OFFICIAL
            and c.source.verification_status is VerificationStatus.VERIFIED))
