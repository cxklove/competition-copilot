"""Read-only, deterministic audit of raw fixtures and existing verified seeds."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import ValidationError

from competition_copilot.domain.competition import Competition
from competition_copilot.domain.source_metadata import VerificationStatus
from competition_copilot.domain.temporal import TimeWindow
from competition_copilot.ingestion.candidate import (
    CandidateStatus,
    CompetitionCandidate,
    IssueSeverity,
    ValidationIssue,
)
from competition_copilot.ingestion.models import RawCompetitionData
from competition_copilot.ingestion.normalizer import (
    CompetitionNormalizer,
    NormalizationError,
)
from competition_copilot.ingestion.seed import (
    CompetitionSeedEnvelope,
    deserialize_seed,
    serialize_seed,
)
from competition_copilot.ingestion.validator import CompetitionCandidateValidator

AuditStatus = Literal["passed", "failed", "not_run"]
SeedStatus = Literal["passed", "failed", "missing"]
WindowState = Literal["exact", "partial", "none"]


@dataclass(frozen=True)
class AuditFinding:
    code: str
    message: str
    path: str


@dataclass
class BatchFixtureAuditResult:
    fixture_path: str
    competition_id: str | None = None
    edition_id: str | None = None
    raw_load_status: AuditStatus = "not_run"
    normalization_status: AuditStatus = "not_run"
    validation_error_count: int = 0
    validation_warning_count: int = 0
    validation_issues: list[ValidationIssue] = field(default_factory=list)
    track_count: int | None = None
    registration_window_state: WindowState | None = None
    competition_window_state: WindowState | None = None
    source_type: str | None = None
    source_url: str | None = None
    observed_at: datetime | None = None
    candidate_status: CandidateStatus | None = None
    matching_seed_path: str | None = None
    seed_status: SeedStatus = "missing"
    findings: list[AuditFinding] = field(default_factory=list)


@dataclass
class SeedAuditResult:
    seed_path: str
    raw_fixture_path: str | None = None
    status: AuditStatus = "not_run"
    round_trip_status: AuditStatus = "not_run"
    candidate_id: str | None = None
    findings: list[AuditFinding] = field(default_factory=list)


@dataclass(frozen=True)
class IdCollision:
    code: str
    identifier: str
    fixture_paths: tuple[str, ...]


@dataclass(frozen=True)
class BatchAuditSummary:
    total_raw_fixtures: int
    raw_load_passed: int
    raw_load_failed: int
    normalization_passed: int
    normalization_failed: int
    validation_errors: int
    validation_warnings: int
    existing_seeds: int
    seed_passed: int
    seed_failed: int
    id_collisions: int


@dataclass
class BatchAuditReport:
    fixtures: list[BatchFixtureAuditResult]
    seeds: list[SeedAuditResult]
    id_collisions: list[IdCollision]
    findings: list[AuditFinding] = field(default_factory=list)

    @property
    def summary(self) -> BatchAuditSummary:
        return BatchAuditSummary(
            total_raw_fixtures=len(self.fixtures),
            raw_load_passed=sum(item.raw_load_status == "passed" for item in self.fixtures),
            raw_load_failed=sum(item.raw_load_status == "failed" for item in self.fixtures),
            normalization_passed=sum(
                item.normalization_status == "passed" for item in self.fixtures
            ),
            normalization_failed=sum(
                item.normalization_status == "failed" for item in self.fixtures
            ),
            validation_errors=sum(item.validation_error_count for item in self.fixtures),
            validation_warnings=sum(
                item.validation_warning_count for item in self.fixtures
            ),
            existing_seeds=len(self.seeds),
            seed_passed=sum(item.status == "passed" for item in self.seeds),
            seed_failed=sum(item.status == "failed" for item in self.seeds),
            id_collisions=len(self.id_collisions),
        )

    @property
    def passed(self) -> bool:
        summary = self.summary
        return not (
            self.findings
            or any(item.findings for item in self.fixtures)
            or summary.raw_load_failed
            or summary.normalization_failed
            or summary.validation_errors
            or summary.seed_failed
            or summary.id_collisions
        )


def _window_state(window: TimeWindow | None) -> WindowState:
    if window is None or (window.start_at is None and window.end_at is None):
        return "none"
    if window.start_at is not None and window.end_at is not None:
        return "exact"
    return "partial"


def _display(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _audit_raw(
    path: Path, root: Path
) -> tuple[BatchFixtureAuditResult, CompetitionCandidate | None]:
    result = BatchFixtureAuditResult(fixture_path=_display(path, root))
    try:
        raw = RawCompetitionData.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        result.raw_load_status = "failed"
        result.findings.append(
            AuditFinding("RAW_LOAD_FAILED", str(exc), result.fixture_path)
        )
        return result, None

    result.raw_load_status = "passed"
    result.competition_id = raw.competition_id
    result.edition_id = raw.edition_id
    result.source_type = raw.source_type
    result.source_url = raw.source_url
    result.observed_at = raw.observed_at
    try:
        competition, edition, tracks = CompetitionNormalizer().normalize(raw)
    except (NormalizationError, ValidationError) as exc:
        result.normalization_status = "failed"
        code = exc.code if isinstance(exc, NormalizationError) else "NORMALIZATION_FAILED"
        result.findings.append(AuditFinding(code, str(exc), result.fixture_path))
        return result, None

    candidate = CompetitionCandidate(
        id=f"{edition.id}-candidate",
        raw_data=raw,
        competition=competition,
        edition=edition,
        tracks=tracks,
        created_at=raw.observed_at,
    )
    issues = CompetitionCandidateValidator().validate(candidate)
    result.normalization_status = "passed"
    result.competition_id = competition.id
    result.edition_id = edition.id
    result.track_count = len(tracks)
    result.registration_window_state = _window_state(edition.registration_window)
    result.competition_window_state = _window_state(edition.competition_window)
    result.candidate_status = candidate.status
    result.validation_issues = issues
    result.validation_error_count = sum(
        issue.severity is IssueSeverity.ERROR for issue in issues
    )
    result.validation_warning_count = sum(
        issue.severity is IssueSeverity.WARNING for issue in issues
    )
    if candidate.status is not CandidateStatus.PENDING:
        result.findings.append(
            AuditFinding(
                "CANDIDATE_STATUS_CHANGED",
                "Raw audit candidate must remain pending",
                result.fixture_path,
            )
        )
    return result, candidate


def _check_seed_contract(seed: CompetitionSeedEnvelope, result: SeedAuditResult) -> None:
    sources = [seed.competition_source, seed.edition.source]
    sources.extend(track.source for track in seed.tracks)
    if (
        seed.schema_version not in ("1.0", "1.1")
        or seed.artifact_type != "verified_competition_seed"
        or seed.approval.status is not CandidateStatus.APPROVED
        or seed.verification.previous_status is not VerificationStatus.PENDING
        or seed.verification.new_status is not VerificationStatus.VERIFIED
        or any(
            source is None
            or source.verification_status is not VerificationStatus.VERIFIED
            for source in sources
        )
        or any(
            issue.severity is IssueSeverity.ERROR for issue in seed.validation_issues
        )
        or seed.approval.candidate_id != seed.verification.candidate_id
    ):
        result.findings.append(
            AuditFinding(
                "SEED_CONTRACT_MISMATCH",
                "Seed approval, verification, version, or source state is inconsistent",
                result.seed_path,
            )
        )


def _audit_seed(path: Path, root: Path) -> tuple[SeedAuditResult, CompetitionSeedEnvelope | None]:
    result = SeedAuditResult(seed_path=_display(path, root))
    try:
        payload = path.read_bytes()
    except OSError as exc:
        result.status = "failed"
        result.findings.append(
            AuditFinding("SEED_READ_FAILED", str(exc), result.seed_path)
        )
        return result, None

    if b'"raw_payload"' in payload:
        result.findings.append(
            AuditFinding(
                "FORBIDDEN_RAW_PAYLOAD", "Seed contains a raw_payload key", result.seed_path
            )
        )
    try:
        seed = CompetitionSeedEnvelope.model_validate_json(payload)
    except ValidationError as exc:
        result.status = "failed"
        result.findings.append(
            AuditFinding("SEED_SCHEMA_FAILED", str(exc), result.seed_path)
        )
        return result, None

    result.raw_fixture_path = seed.raw_fixture_path
    result.candidate_id = seed.approval.candidate_id
    _check_seed_contract(seed, result)
    try:
        restored = deserialize_seed(serialize_seed(seed))
    except ValidationError as exc:
        result.round_trip_status = "failed"
        result.findings.append(
            AuditFinding("SEED_ROUND_TRIP_FAILED", str(exc), result.seed_path)
        )
    else:
        result.round_trip_status = "passed" if restored == seed else "failed"
        if restored != seed:
            result.findings.append(
                AuditFinding(
                    "SEED_ROUND_TRIP_FAILED",
                    "Re-serialized seed changed its modeled values",
                    result.seed_path,
                )
            )
    return result, seed


def _matching_raw_path(reference: str, raw_dir: Path) -> Path | None:
    logical_path = PurePosixPath(reference)
    if (
        len(logical_path.parts) != 3
        or logical_path.parts[:2] != ("data", "raw")
        or logical_path.suffix != ".json"
    ):
        return None
    return raw_dir / logical_path.name


def _compare_raw_seed(
    candidate: CompetitionCandidate, seed: CompetitionSeedEnvelope, result: SeedAuditResult
) -> None:
    competition = candidate.competition
    edition = candidate.edition
    assert competition is not None and edition is not None
    if competition != seed.competition:
        result.findings.append(
            AuditFinding(
                "COMPETITION_MISMATCH", "Seed competition differs from Raw", result.seed_path
            )
        )
    if edition.model_dump(exclude={"source"}) != seed.edition.model_dump(
        exclude={"source"}
    ):
        result.findings.append(
            AuditFinding("EDITION_MISMATCH", "Seed edition differs from Raw", result.seed_path)
        )
    if [track.model_dump(exclude={"source"}) for track in candidate.tracks] != [
        track.model_dump(exclude={"source"}) for track in seed.tracks
    ]:
        result.findings.append(
            AuditFinding("TRACK_MISMATCH", "Seed tracks differ from Raw", result.seed_path)
        )
    source = edition.source
    verified_source = seed.competition_source
    if (
        source is None
        or source.source_url != verified_source.source_url
        or source.source_type != verified_source.source_type
        or source.observed_at != verified_source.observed_at
    ):
        result.findings.append(
            AuditFinding(
                "PROVENANCE_MISMATCH", "Seed provenance differs from Raw", result.seed_path
            )
        )
    issues = CompetitionCandidateValidator().validate(candidate)
    if issues != seed.validation_issues:
        result.findings.append(
            AuditFinding(
                "VALIDATION_ISSUES_MISMATCH",
                "Seed validation issues differ from current Raw validation",
                result.seed_path,
            )
        )
    expected_temporal_provenance = [
        item.for_seed() for item in candidate.raw_data.temporal_provenance
    ]
    if seed.temporal_provenance != expected_temporal_provenance:
        result.findings.append(
            AuditFinding(
                "TEMPORAL_PROVENANCE_MISMATCH",
                "Seed temporal provenance differs from Raw",
                result.seed_path,
            )
        )


def _id_collisions(candidates: dict[Path, CompetitionCandidate], root: Path) -> list[IdCollision]:
    competitions: dict[str, tuple[Competition, str]] = {}
    ids: dict[tuple[str, str], list[str]] = defaultdict(list)
    collisions: list[IdCollision] = []
    for path, candidate in sorted(candidates.items()):
        assert candidate.competition is not None and candidate.edition is not None
        fixture = _display(path, root)
        competition = candidate.competition
        previous = competitions.get(competition.id)
        if previous is None:
            competitions[competition.id] = (competition, fixture)
        elif previous[0] != competition:
            collisions.append(
                IdCollision(
                    "COMPETITION_ID_CONFLICT",
                    competition.id,
                    (previous[1], fixture),
                )
            )
        ids["edition", candidate.edition.id].append(fixture)
        ids["candidate", candidate.id].append(fixture)
        for track in candidate.tracks:
            ids["track", track.id].append(fixture)
    for (kind, identifier), paths in sorted(ids.items()):
        if len(paths) > 1:
            collisions.append(
                IdCollision(f"{kind.upper()}_ID_COLLISION", identifier, tuple(paths))
            )
    return collisions


def audit_fixtures(raw_dir: Path, seed_dir: Path) -> BatchAuditReport:
    """Audit discovered files without editing them or changing review state."""

    raw_dir = Path(raw_dir).resolve()
    seed_dir = Path(seed_dir).resolve()
    root = raw_dir.parent.parent
    report = BatchAuditReport(fixtures=[], seeds=[], id_collisions=[])
    for directory in (raw_dir, seed_dir):
        if not directory.is_dir():
            report.findings.append(
                AuditFinding("DIRECTORY_MISSING", "Audit directory does not exist", directory.as_posix())
            )

    raw_results: dict[Path, BatchFixtureAuditResult] = {}
    candidates: dict[Path, CompetitionCandidate] = {}
    for path in sorted(raw_dir.glob("*.json")):
        result, candidate = _audit_raw(path, root)
        report.fixtures.append(result)
        raw_results[path] = result
        if candidate is not None:
            candidates[path] = candidate

    matched_seeds: dict[Path, list[SeedAuditResult]] = defaultdict(list)
    seed_candidates: dict[Path, list[str]] = defaultdict(list)
    for path in sorted(seed_dir.glob("*.json")):
        result, seed = _audit_seed(path, root)
        report.seeds.append(result)
        if seed is None:
            continue
        raw_path = _matching_raw_path(seed.raw_fixture_path, raw_dir)
        if raw_path is None:
            result.findings.append(
                AuditFinding(
                    "RAW_REFERENCE_INVALID",
                    "Seed raw_fixture_path is outside discovered data/raw/*.json",
                    result.seed_path,
                )
            )
            continue
        if raw_path not in raw_results:
            result.findings.append(
                AuditFinding(
                    "RAW_REFERENCE_MISSING", "Seed Raw fixture does not exist", result.seed_path
                )
            )
            continue
        matched_seeds[raw_path].append(result)
        seed_candidates[raw_path].append(seed.approval.candidate_id)
        candidate = candidates.get(raw_path)
        if candidate is None:
            result.findings.append(
                AuditFinding(
                    "RAW_NOT_NORMALIZED",
                    "Matching Raw fixture did not normalize",
                    result.seed_path,
                )
            )
            continue
        _compare_raw_seed(candidate, seed, result)

    for raw_path, seeds in matched_seeds.items():
        if len(seeds) > 1:
            for seed in seeds:
                seed.findings.append(
                    AuditFinding(
                        "DUPLICATE_SEED_FOR_RAW",
                        "Multiple seeds reference one Raw fixture",
                        seed.seed_path,
                    )
                )
        raw_result = raw_results[raw_path]
        raw_result.matching_seed_path = seeds[0].seed_path

    for seed in report.seeds:
        seed.status = "failed" if seed.findings else "passed"
    for raw_path, seeds in matched_seeds.items():
        raw_results[raw_path].seed_status = (
            "passed" if len(seeds) == 1 and seeds[0].status == "passed" else "failed"
        )

    report.id_collisions = _id_collisions(candidates, root)
    explicit_candidate_ids: dict[str, set[str]] = defaultdict(set)
    for raw_path, candidate_ids in seed_candidates.items():
        for candidate_id in candidate_ids:
            explicit_candidate_ids[candidate_id].add(_display(raw_path, root))
    for candidate_id, paths in sorted(explicit_candidate_ids.items()):
        if len(paths) > 1 and not any(
            collision.code == "CANDIDATE_ID_COLLISION"
            and collision.identifier == candidate_id
            for collision in report.id_collisions
        ):
            report.id_collisions.append(
                IdCollision("CANDIDATE_ID_COLLISION", candidate_id, tuple(sorted(paths)))
            )
    return report
