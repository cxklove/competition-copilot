"""Read-only batch audit checks using real and synthetic fixtures."""

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from competition_copilot.ingestion import approval, batch_audit, verification
from competition_copilot.ingestion.batch_audit import audit_fixtures
from competition_copilot.ingestion.candidate import (
    CandidateStatus,
    CompetitionCandidate,
    IssueSeverity,
    ValidationIssue,
)
from competition_copilot.ingestion.validator import CompetitionCandidateValidator

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data/raw"
SEED_DIR = ROOT / "data/seed"
SCRIPT = ROOT / "backend/scripts/audit_fixtures.py"
NAMES = (
    "huawei-ict-2026",
    "c4-big-data-challenge-2026",
    "nuedc-analog-system-2026",
)


def sample_dirs(tmp_path: Path) -> tuple[Path, Path]:
    raw_dir = tmp_path / "data/raw"
    seed_dir = tmp_path / "data/seed"
    raw_dir.mkdir(parents=True)
    seed_dir.mkdir(parents=True)
    for name in NAMES:
        shutil.copyfile(RAW_DIR / f"{name}.json", raw_dir / f"{name}.json")
        shutil.copyfile(SEED_DIR / f"{name}.json", seed_dir / f"{name}.json")
    return raw_dir, seed_dir


def empty_dirs(tmp_path: Path) -> tuple[Path, Path]:
    raw_dir = tmp_path / "data/raw"
    seed_dir = tmp_path / "data/seed"
    raw_dir.mkdir(parents=True)
    seed_dir.mkdir(parents=True)
    return raw_dir, seed_dir


def write_raw(
    raw_dir: Path,
    filename: str,
    *,
    competition_id: str = "example",
    edition_id: str = "example-2026",
    name: str = "Example Competition",
    track_id: str | None = None,
    **overrides: object,
) -> Path:
    data: dict[str, object] = {
        "competition_id": competition_id,
        "name": name,
        "edition_id": edition_id,
        "edition_name": "Example Edition",
        "edition_year": 2026,
        "source_url": "https://example.org/notice",
        "source_type": "official",
        "observed_at": datetime(2026, 10, 8, tzinfo=timezone.utc).isoformat(),
        "tracks": ["Track"] if track_id else [],
        "track_ids": [track_id] if track_id else [],
    }
    data.update(overrides)
    path = raw_dir / filename
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_current_three_samples_pass_complete_batch_audit(tmp_path: Path) -> None:
    raw_dir, seed_dir = sample_dirs(tmp_path)
    report = audit_fixtures(raw_dir, seed_dir)
    by_name = {Path(item.fixture_path).stem: item for item in report.fixtures}
    summary = report.summary

    assert [Path(item.fixture_path).stem for item in report.fixtures] == sorted(NAMES)
    assert summary.total_raw_fixtures == 3
    assert summary.raw_load_passed == 3 and summary.raw_load_failed == 0
    assert summary.normalization_passed == 3 and summary.normalization_failed == 0
    assert summary.validation_errors == 0 and summary.validation_warnings == 0
    assert summary.existing_seeds == 3
    assert summary.seed_passed == 3 and summary.seed_failed == 0
    assert summary.id_collisions == 0
    assert report.passed
    assert by_name["huawei-ict-2026"].track_count == 7
    assert by_name["c4-big-data-challenge-2026"].track_count == 0
    assert by_name["nuedc-analog-system-2026"].track_count == 0
    assert by_name["huawei-ict-2026"].registration_window_state == "none"
    assert by_name["c4-big-data-challenge-2026"].registration_window_state == "exact"
    assert by_name["nuedc-analog-system-2026"].registration_window_state == "none"
    assert all(item.candidate_status is CandidateStatus.PENDING for item in report.fixtures)
    assert all(item.seed_status == "passed" for item in report.fixtures)
    assert all(item.matching_seed_path is not None for item in report.fixtures)
    assert all(seed.round_trip_status == "passed" for seed in report.seeds)
    assert all(seed.raw_fixture_path is not None for seed in report.seeds)
    assert audit_fixtures(raw_dir, seed_dir) == report


def test_audit_is_read_only_and_never_calls_review_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_dir, seed_dir = sample_dirs(tmp_path)
    files = sorted((*raw_dir.glob("*.json"), *seed_dir.glob("*.json")))
    before = {path: path.read_bytes() for path in files}

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Batch audit called a review action")

    monkeypatch.setattr(approval, "approve_candidate", forbidden)
    monkeypatch.setattr(verification, "verify_approved_bundle", forbidden)
    report = audit_fixtures(raw_dir, seed_dir)

    assert report.passed
    assert all(item.candidate_status is CandidateStatus.PENDING for item in report.fixtures)
    assert {path: path.read_bytes() for path in files} == before
    source = Path(batch_audit.__file__).read_text(encoding="utf-8").lower()
    assert all(name not in source for name in ("huawei", "c4", "nuedc"))
    assert "approve_candidate" not in source
    assert "verify_approved_bundle" not in source
    assert "build_seed_envelope" not in source


def test_discovery_is_sorted_and_nonrecursive(tmp_path: Path) -> None:
    raw_dir, seed_dir = empty_dirs(tmp_path)
    write_raw(raw_dir, "z.json", competition_id="z", edition_id="z-2026")
    write_raw(raw_dir, "a.json", competition_id="a", edition_id="a-2026")
    nested = raw_dir / "temporary"
    nested.mkdir()
    (nested / "bad.json").write_text("not JSON", encoding="utf-8")

    report = audit_fixtures(raw_dir, seed_dir)

    assert [Path(item.fixture_path).name for item in report.fixtures] == [
        "a.json",
        "z.json",
    ]
    assert report.passed
    assert all(item.seed_status == "missing" for item in report.fixtures)


def test_bad_raw_does_not_stop_other_fixtures(tmp_path: Path) -> None:
    raw_dir, seed_dir = empty_dirs(tmp_path)
    (raw_dir / "a-bad.json").write_text("{bad", encoding="utf-8")
    write_raw(raw_dir, "b-good.json")

    report = audit_fixtures(raw_dir, seed_dir)

    assert report.summary.raw_load_failed == 1
    assert report.summary.raw_load_passed == 1
    assert report.summary.normalization_passed == 1
    assert report.fixtures[0].findings[0].code == "RAW_LOAD_FAILED"
    assert report.fixtures[1].candidate_status is CandidateStatus.PENDING
    assert not report.passed


def test_normalization_failure_does_not_stop_other_fixtures(tmp_path: Path) -> None:
    raw_dir, seed_dir = empty_dirs(tmp_path)
    write_raw(raw_dir, "a-bad.json", name="")
    write_raw(raw_dir, "b-good.json", competition_id="good", edition_id="good-2026")

    report = audit_fixtures(raw_dir, seed_dir)

    assert report.summary.raw_load_passed == 2
    assert report.summary.normalization_failed == 1
    assert report.summary.normalization_passed == 1
    assert report.fixtures[0].findings[0].code == "MISSING_FIELD"
    assert not report.passed


@pytest.mark.parametrize(
    ("severity", "expected_pass"),
    [(IssueSeverity.ERROR, False), (IssueSeverity.WARNING, True)],
)
def test_validator_issue_severity_controls_batch_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    severity: IssueSeverity,
    expected_pass: bool,
) -> None:
    raw_dir, seed_dir = empty_dirs(tmp_path)
    write_raw(raw_dir, "one.json")
    original_validate = CompetitionCandidateValidator.validate

    def validate(
        self: CompetitionCandidateValidator, candidate: CompetitionCandidate, **kwargs: object
    ) -> list[ValidationIssue]:
        assert candidate.status is CandidateStatus.PENDING
        return original_validate(self, candidate, **kwargs) + [
            ValidationIssue(code="REVIEW_SIGNAL", message="Check source", severity=severity)
        ]

    monkeypatch.setattr(CompetitionCandidateValidator, "validate", validate)
    report = audit_fixtures(raw_dir, seed_dir)

    assert report.passed is expected_pass
    assert report.summary.validation_errors == int(severity is IssueSeverity.ERROR)
    assert report.summary.validation_warnings == int(severity is IssueSeverity.WARNING)
    assert report.fixtures[0].validation_issues[0].code == "REVIEW_SIGNAL"
    assert report.fixtures[0].candidate_status is CandidateStatus.PENDING


def test_bad_seed_is_reported_without_stopping_other_seeds(tmp_path: Path) -> None:
    raw_dir, seed_dir = sample_dirs(tmp_path)
    (seed_dir / "c4-big-data-challenge-2026.json").write_text("{bad", encoding="utf-8")

    report = audit_fixtures(raw_dir, seed_dir)

    assert report.summary.seed_failed == 1
    assert report.summary.seed_passed == 2
    assert any(
        finding.code == "SEED_SCHEMA_FAILED"
        for seed in report.seeds
        for finding in seed.findings
    )
    assert not report.passed


def test_seed_matching_uses_explicit_raw_fixture_path(tmp_path: Path) -> None:
    raw_dir, seed_dir = sample_dirs(tmp_path)
    original = seed_dir / "c4-big-data-challenge-2026.json"
    renamed = seed_dir / "unrelated-seed-name.json"
    original.rename(renamed)

    report = audit_fixtures(raw_dir, seed_dir)
    c4 = next(
        item for item in report.fixtures if item.edition_id == "c4-big-data-challenge-2026"
    )

    assert report.passed
    assert c4.matching_seed_path == "data/seed/unrelated-seed-name.json"


def test_duplicate_seeds_for_one_raw_are_reported(tmp_path: Path) -> None:
    raw_dir, seed_dir = sample_dirs(tmp_path)
    original = seed_dir / "c4-big-data-challenge-2026.json"
    shutil.copyfile(original, seed_dir / "duplicate.json")

    report = audit_fixtures(raw_dir, seed_dir)

    assert report.summary.seed_failed == 2
    assert any(
        finding.code == "DUPLICATE_SEED_FOR_RAW"
        for seed in report.seeds
        for finding in seed.findings
    )
    assert not report.passed


def test_raw_seed_structural_mismatch_is_reported(tmp_path: Path) -> None:
    raw_dir, seed_dir = sample_dirs(tmp_path)
    path = seed_dir / "c4-big-data-challenge-2026.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["edition"]["year"] = 2025
    path.write_text(json.dumps(document), encoding="utf-8")

    report = audit_fixtures(raw_dir, seed_dir)

    assert report.summary.seed_failed == 1
    assert any(
        finding.code == "EDITION_MISMATCH"
        for seed in report.seeds
        for finding in seed.findings
    )


def test_seed_raw_reference_must_identify_discovered_raw(tmp_path: Path) -> None:
    raw_dir, seed_dir = sample_dirs(tmp_path)
    path = seed_dir / "c4-big-data-challenge-2026.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["raw_fixture_path"] = "data/raw/absent.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    report = audit_fixtures(raw_dir, seed_dir)

    assert report.summary.seed_failed == 1
    assert any(
        finding.code == "RAW_REFERENCE_MISSING"
        for seed in report.seeds
        for finding in seed.findings
    )


def test_seed_rejects_forbidden_raw_payload(tmp_path: Path) -> None:
    raw_dir, seed_dir = sample_dirs(tmp_path)
    path = seed_dir / "c4-big-data-challenge-2026.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["raw_payload"] = {"raw": "evidence"}
    path.write_text(json.dumps(document), encoding="utf-8")

    report = audit_fixtures(raw_dir, seed_dir)

    assert report.summary.seed_failed == 1
    assert {
        finding.code for seed in report.seeds for finding in seed.findings
    } >= {"FORBIDDEN_RAW_PAYLOAD", "SEED_SCHEMA_FAILED"}


def test_same_competition_id_across_editions_is_legal_when_identity_matches(
    tmp_path: Path,
) -> None:
    raw_dir, seed_dir = empty_dirs(tmp_path)
    write_raw(raw_dir, "one.json", competition_id="shared", edition_id="shared-2026")
    write_raw(raw_dir, "two.json", competition_id="shared", edition_id="shared-2027")

    report = audit_fixtures(raw_dir, seed_dir)

    assert report.passed
    assert report.id_collisions == []


def test_conflicting_competition_identity_is_collision(tmp_path: Path) -> None:
    raw_dir, seed_dir = empty_dirs(tmp_path)
    write_raw(raw_dir, "one.json", competition_id="shared", edition_id="shared-2026")
    write_raw(
        raw_dir,
        "two.json",
        competition_id="shared",
        edition_id="shared-2027",
        name="Different Competition",
    )

    report = audit_fixtures(raw_dir, seed_dir)

    assert [collision.code for collision in report.id_collisions] == [
        "COMPETITION_ID_CONFLICT"
    ]
    assert not report.passed


def test_edition_track_and_candidate_ids_must_be_unique(tmp_path: Path) -> None:
    raw_dir, seed_dir = empty_dirs(tmp_path)
    write_raw(raw_dir, "one.json", track_id="shared-track")
    write_raw(raw_dir, "two.json", track_id="shared-track")

    report = audit_fixtures(raw_dir, seed_dir)

    assert {collision.code for collision in report.id_collisions} == {
        "EDITION_ID_COLLISION",
        "TRACK_ID_COLLISION",
        "CANDIDATE_ID_COLLISION",
    }
    assert not report.passed


def test_seed_candidate_id_collision_is_detected_across_raws(tmp_path: Path) -> None:
    raw_dir, seed_dir = sample_dirs(tmp_path)
    path = seed_dir / "c4-big-data-challenge-2026.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["approval"]["candidate_id"] = "huawei-ict-2026-candidate"
    document["verification"]["candidate_id"] = "huawei-ict-2026-candidate"
    path.write_text(json.dumps(document), encoding="utf-8")

    report = audit_fixtures(raw_dir, seed_dir)

    assert any(
        collision.code == "CANDIDATE_ID_COLLISION" for collision in report.id_collisions
    )
    assert not report.passed


def test_time_window_partial_state_uses_real_model_fields(tmp_path: Path) -> None:
    raw_dir, seed_dir = empty_dirs(tmp_path)
    write_raw(raw_dir, "one.json", registration_start="2026-10-01T09:00:00Z")

    report = audit_fixtures(raw_dir, seed_dir)

    assert report.fixtures[0].registration_window_state == "partial"
    assert report.fixtures[0].competition_window_state == "none"
    assert report.passed


def test_candidate_status_change_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_dir, seed_dir = empty_dirs(tmp_path)
    write_raw(raw_dir, "one.json")

    def validate(
        self: CompetitionCandidateValidator, candidate: CompetitionCandidate, **kwargs: object
    ) -> list[ValidationIssue]:
        candidate.status = CandidateStatus.APPROVED
        return []

    monkeypatch.setattr(CompetitionCandidateValidator, "validate", validate)
    report = audit_fixtures(raw_dir, seed_dir)

    assert report.fixtures[0].candidate_status is CandidateStatus.APPROVED
    assert report.fixtures[0].findings[0].code == "CANDIDATE_STATUS_CHANGED"
    assert not report.passed


def test_cli_success_and_failure_exit_codes(tmp_path: Path) -> None:
    raw_dir, seed_dir = sample_dirs(tmp_path)
    command = [
        sys.executable,
        str(SCRIPT),
        "--raw-dir",
        str(raw_dir),
        "--seed-dir",
        str(seed_dir),
    ]

    success = subprocess.run(command, capture_output=True, text=True, check=False)
    assert success.returncode == 0
    assert all(column in success.stdout for column in ("Fixture", "RegWindow", "Seed"))
    assert "seed_passed=3" in success.stdout

    (raw_dir / "broken.json").write_text("{bad", encoding="utf-8")
    failure = subprocess.run(command, capture_output=True, text=True, check=False)
    assert failure.returncode != 0
    assert "RAW_LOAD_FAILED" in failure.stdout
