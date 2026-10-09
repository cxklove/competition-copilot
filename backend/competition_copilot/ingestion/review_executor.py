"""Execute only explicit, Raw-bound human review decisions."""

import hashlib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from competition_copilot.domain.source_metadata import VerificationStatus
from competition_copilot.ingestion.approval import (
    CandidateReviewError,
    approve_candidate,
    approved_bundle,
    reject_candidate,
)
from competition_copilot.ingestion.candidate import (
    CompetitionCandidate,
    IssueSeverity,
    ValidationIssue,
)
from competition_copilot.ingestion.models import RawCompetitionData
from competition_copilot.ingestion.normalizer import (
    CompetitionNormalizer,
    NormalizationError,
)
from competition_copilot.ingestion.review_manifest import (
    ApprovalDecision,
    HumanReviewEntry,
    HumanReviewManifest,
    RawBindingError,
    SourceVerificationDecision,
    deserialize_review_manifest,
    validate_raw_binding,
)
from competition_copilot.ingestion.seed import (
    CompetitionSeedEnvelope,
    build_seed_envelope,
    deserialize_seed,
    serialize_seed,
)
from competition_copilot.ingestion.validator import CompetitionCandidateValidator
from competition_copilot.ingestion.verification import (
    SourceVerificationError,
    verify_approved_bundle,
)

ReviewStatus = Literal[
    "planned", "executed", "held", "rejected", "failed", "already_materialized"
]
STATUSES: tuple[ReviewStatus, ...] = (
    "planned",
    "executed",
    "held",
    "rejected",
    "failed",
    "already_materialized",
)


class ReviewExecutionError(ValueError):
    """A manifest entry cannot be executed safely."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ReviewEntryResult:
    raw_fixture_path: str
    status: ReviewStatus
    code: str | None = None
    message: str | None = None
    seed_path: str | None = None


@dataclass(frozen=True)
class ReviewExecutionReport:
    entries: list[ReviewEntryResult]

    @property
    def summary(self) -> dict[str, int]:
        counts = Counter(entry.status for entry in self.entries)
        return {status: counts[status] for status in STATUSES}

    @property
    def passed(self) -> bool:
        return self.summary["failed"] == 0


def _fail(code: str, message: str) -> None:
    raise ReviewExecutionError(code, message)


def _seed_path(entry: HumanReviewEntry, root: Path) -> Path:
    raw_path = (root / entry.raw_fixture_path).resolve()
    if raw_path.parent != (root / "data/raw").resolve() or raw_path.suffix != ".json":
        _fail("INVALID_RAW_FIXTURE_PATH", "Raw fixture must be a data/raw/*.json file")
    return root / "data/seed" / raw_path.name


def _matches_existing_seed(
    seed: CompetitionSeedEnvelope,
    entry: HumanReviewEntry,
    candidate: CompetitionCandidate,
    issues: list[ValidationIssue],
) -> bool:
    edition = candidate.edition
    if edition is None or edition.source is None:
        return False
    pending_source = seed.competition_source.model_copy(
        update={"verification_status": VerificationStatus.PENDING}
    )
    return (
        seed.raw_fixture_path == entry.raw_fixture_path
        and seed.approval.candidate_id == entry.candidate_id == candidate.id
        and seed.verification.candidate_id == candidate.id
        and seed.approval.review_note == entry.review_note
        and seed.verification.verification_note == entry.verification_note
        and seed.competition == candidate.competition
        and seed.edition.model_dump(exclude={"source"})
        == edition.model_dump(exclude={"source"})
        and [track.model_dump(exclude={"source"}) for track in seed.tracks]
        == [track.model_dump(exclude={"source"}) for track in candidate.tracks]
        and pending_source == edition.source
        and seed.validation_issues == issues
    )


def _existing_seed_result(
    path: Path,
    entry: HumanReviewEntry,
    candidate: CompetitionCandidate,
    issues: list[ValidationIssue],
    root: Path,
) -> ReviewEntryResult:
    relative_path = path.relative_to(root).as_posix()
    try:
        existing = deserialize_seed(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise ReviewExecutionError(
            "EXISTING_SEED_CONFLICT", f"cannot validate existing Seed: {exc}"
        ) from exc
    if not _matches_existing_seed(existing, entry, candidate, issues):
        _fail("EXISTING_SEED_CONFLICT", "existing Seed differs from reviewed facts")
    return ReviewEntryResult(
        entry.raw_fixture_path, "already_materialized", seed_path=relative_path
    )


def _prepare_candidate(
    entry: HumanReviewEntry, root: Path
) -> tuple[CompetitionCandidate, list[ValidationIssue]]:
    validate_raw_binding(entry, root)
    try:
        raw_bytes = (root / entry.raw_fixture_path).read_bytes()
    except OSError as exc:
        raise ReviewExecutionError("RAW_LOAD_FAILED", str(exc)) from exc
    if hashlib.sha256(raw_bytes).hexdigest() != entry.raw_sha256:
        _fail(
            "RAW_FIXTURE_CHANGED_AFTER_REVIEW",
            "Raw fixture changed while being loaded",
        )
    try:
        raw = RawCompetitionData.model_validate_json(raw_bytes)
    except ValidationError as exc:
        raise ReviewExecutionError("RAW_LOAD_FAILED", str(exc)) from exc
    competition, edition, tracks = CompetitionNormalizer().normalize(raw)
    candidate = CompetitionCandidate(
        id=f"{edition.id}-candidate",
        raw_data=raw,
        competition=competition,
        edition=edition,
        tracks=tracks,
        created_at=raw.observed_at,
    )
    issues = CompetitionCandidateValidator().validate(candidate)
    if any(issue.severity is IssueSeverity.ERROR for issue in issues):
        _fail("VALIDATION_ERRORS", "candidate has error-level validation issues")
    if competition.id != entry.competition_id:
        _fail("COMPETITION_ID_MISMATCH", "Competition ID differs from manifest")
    if edition.id != entry.edition_id:
        _fail("EDITION_ID_MISMATCH", "Edition ID differs from manifest")
    if candidate.id != entry.candidate_id:
        _fail("CANDIDATE_ID_MISMATCH", "Candidate ID differs from manifest")
    return candidate, issues


def _run_entry(
    entry: HumanReviewEntry,
    root: Path,
    *,
    execute: bool,
    clock: Callable[[], datetime],
) -> ReviewEntryResult:
    candidate, issues = _prepare_candidate(entry, root)
    if entry.approval_decision is ApprovalDecision.HOLD:
        return ReviewEntryResult(entry.raw_fixture_path, "held")
    if entry.approval_decision is ApprovalDecision.REJECT:
        if not execute:
            return ReviewEntryResult(entry.raw_fixture_path, "planned")
        validate_raw_binding(entry, root)
        reject_candidate(candidate, reviewed_at=clock(), review_note=entry.review_note)
        return ReviewEntryResult(entry.raw_fixture_path, "rejected")

    if entry.source_verification_decision is SourceVerificationDecision.VERIFY:
        seed_path = _seed_path(entry, root)
        if seed_path.exists():
            return _existing_seed_result(seed_path, entry, candidate, issues, root)
    if not execute:
        return ReviewEntryResult(entry.raw_fixture_path, "planned")

    validate_raw_binding(entry, root)
    approve_candidate(candidate, reviewed_at=clock(), review_note=entry.review_note)
    if entry.source_verification_decision is SourceVerificationDecision.HOLD:
        return ReviewEntryResult(entry.raw_fixture_path, "executed")

    verified = verify_approved_bundle(
        candidate,
        approved_bundle(candidate),
        verified_at=clock(),
        verification_note=entry.verification_note or "",
    )
    seed = build_seed_envelope(candidate, verified, issues, entry.raw_fixture_path)
    if not _matches_existing_seed(seed, entry, candidate, issues):
        _fail("SEED_CONSISTENCY_FAILED", "generated Seed differs from reviewed facts")
    serialized = serialize_seed(seed)
    if deserialize_seed(serialized) != seed:
        _fail("SEED_ROUND_TRIP_FAILED", "generated Seed did not round-trip")
    validate_raw_binding(entry, root)
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with seed_path.open("xb") as output:
            output.write(serialized)
    except FileExistsError:
        return _existing_seed_result(seed_path, entry, candidate, issues, root)
    return ReviewEntryResult(
        entry.raw_fixture_path,
        "executed",
        seed_path=seed_path.relative_to(root).as_posix(),
    )


def execute_review_manifest(
    manifest: HumanReviewManifest,
    project_root: str | Path,
    *,
    execute: bool = False,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> ReviewExecutionReport:
    """Inspect every entry independently; only explicit execute runs review actions."""
    try:
        manifest = deserialize_review_manifest(manifest.model_dump_json())
    except ValidationError as exc:
        raise ReviewExecutionError("MANIFEST_SCHEMA_INVALID", str(exc)) from exc
    root = Path(project_root).resolve()
    results = []
    for entry in manifest.entries:
        try:
            result = _run_entry(entry, root, execute=execute, clock=clock)
        except (
            ReviewExecutionError,
            RawBindingError,
            NormalizationError,
            CandidateReviewError,
            SourceVerificationError,
        ) as exc:
            result = ReviewEntryResult(
                entry.raw_fixture_path, "failed", exc.code, str(exc)
            )
        except (OSError, ValidationError, ValueError) as exc:
            result = ReviewEntryResult(
                entry.raw_fixture_path, "failed", "REVIEW_EXECUTION_FAILED", str(exc)
            )
        results.append(result)
    return ReviewExecutionReport(results)


def execute_review_file(
    manifest_path: str | Path,
    project_root: str | Path,
    *,
    execute: bool = False,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> ReviewExecutionReport:
    """Load the formal manifest contract before processing any entry."""
    try:
        manifest = deserialize_review_manifest(Path(manifest_path).read_bytes())
    except OSError as exc:
        raise ReviewExecutionError("MANIFEST_UNAVAILABLE", str(exc)) from exc
    except ValidationError as exc:
        raise ReviewExecutionError("MANIFEST_SCHEMA_INVALID", str(exc)) from exc
    return execute_review_manifest(manifest, project_root, execute=execute, clock=clock)
