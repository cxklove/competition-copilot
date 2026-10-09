"""Manifest-driven execution uses synthetic Raw facts and explicit decisions."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from competition_copilot.domain.source_metadata import VerificationStatus
from competition_copilot.ingestion import review_executor
from competition_copilot.ingestion.candidate import IssueSeverity, ValidationIssue
from competition_copilot.ingestion.models import RawCompetitionData
from competition_copilot.ingestion.review_executor import (
    ReviewExecutionError,
    execute_review_file,
    execute_review_manifest,
)
from competition_copilot.ingestion.review_manifest import (
    HumanReviewEntry,
    HumanReviewManifest,
    compute_file_sha256,
    serialize_review_manifest,
)
from competition_copilot.ingestion.seed import deserialize_seed, serialize_seed
from scripts import execute_reviews

DECIDED_AT = datetime(2026, 10, 9, 10, tzinfo=timezone(timedelta(hours=8)))
EXECUTED_AT = datetime(2026, 10, 10, 10, tzinfo=timezone.utc)


def make_entry(
    root: Path,
    name: str = "sample-2026",
    *,
    approval: str = "approve",
    verification: str = "verify",
) -> HumanReviewEntry:
    raw_path = root / "data/raw" / f"{name}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw = RawCompetitionData(
        competition_id=name.removesuffix("-2026"),
        name="Synthetic Competition",
        edition_id=name,
        edition_name="Synthetic 2026 Edition",
        edition_year=2026,
        tracks=["Practice", "Innovation"],
        track_ids=[f"{name}-practice", f"{name}-innovation"],
        source_url="https://example.org/notice",
        source_type="official",
        observed_at=DECIDED_AT,
        raw_payload={"source_text": "Synthetic evidence only"},
    )
    raw_path.write_text(raw.model_dump_json(), encoding="utf-8")
    return HumanReviewEntry(
        raw_fixture_path=f"data/raw/{name}.json",
        raw_sha256=compute_file_sha256(raw_path),
        competition_id=raw.competition_id,
        edition_id=raw.edition_id,
        candidate_id=f"{raw.edition_id}-candidate",
        approval_decision=approval,
        approval_decided_at=DECIDED_AT if approval != "hold" else None,
        review_note="Human explicitly reviewed synthetic facts",
        source_verification_decision=verification,
        source_verification_decided_at=DECIDED_AT if verification == "verify" else None,
        verification_note="Human explicitly verified source" if verification == "verify" else None,
    )


def manifest(*entries: HumanReviewEntry) -> HumanReviewManifest:
    return HumanReviewManifest(
        schema_version="1.0", artifact_type="human_review_manifest", entries=list(entries)
    )


def seed_path(root: Path, entry: HumanReviewEntry) -> Path:
    return root / "data/seed" / Path(entry.raw_fixture_path).name


def run(
    root: Path, entry: HumanReviewEntry, *, execute: bool = False
) -> review_executor.ReviewEntryResult:
    return execute_review_manifest(
        manifest(entry), root, execute=execute, clock=lambda: EXECUTED_AT
    ).entries[0]


def test_cli_defaults_to_dry_run_and_only_execute_writes_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entry = make_entry(tmp_path)
    path = tmp_path / "data/review/manifest.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(serialize_review_manifest(manifest(entry)))
    monkeypatch.setattr(execute_reviews, "PROJECT_ROOT", tmp_path)

    assert execute_reviews.main([str(path)]) == 0
    assert "Mode: dry-run" in capsys.readouterr().out
    assert not seed_path(tmp_path, entry).exists()

    assert execute_reviews.main([str(path), "--execute"]) == 0
    assert "Mode: execute" in capsys.readouterr().out
    assert seed_path(tmp_path, entry).exists()


def test_correct_raw_binding_plans_explicit_decision(tmp_path: Path) -> None:
    entry = make_entry(tmp_path)
    result = run(tmp_path, entry)
    assert result.status == "planned"
    assert result.code is None
    assert not seed_path(tmp_path, entry).exists()


def test_changed_raw_hash_blocks_execution(tmp_path: Path) -> None:
    entry = make_entry(tmp_path)
    (tmp_path / entry.raw_fixture_path).write_bytes(b"changed")

    result = run(tmp_path, entry, execute=True)

    assert result.status == "failed"
    assert result.code == "RAW_FIXTURE_CHANGED_AFTER_REVIEW"
    assert not seed_path(tmp_path, entry).exists()


def test_missing_raw_fixture_fails_binding(tmp_path: Path) -> None:
    entry = make_entry(tmp_path)
    (tmp_path / entry.raw_fixture_path).unlink()

    result = run(tmp_path, entry, execute=True)

    assert result.status == "failed"
    assert result.code == "RAW_FIXTURE_UNAVAILABLE"


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("candidate_id", "CANDIDATE_ID_MISMATCH"),
        ("competition_id", "COMPETITION_ID_MISMATCH"),
        ("edition_id", "EDITION_ID_MISMATCH"),
    ],
)
def test_manifest_identity_mismatch_blocks_execution(
    tmp_path: Path, field: str, code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = make_entry(tmp_path).model_copy(update={field: "different"})

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("approval must not run after identity mismatch")

    monkeypatch.setattr(review_executor, "approve_candidate", forbidden)
    result = run(tmp_path, entry, execute=True)

    assert result.status == "failed"
    assert result.code == code
    assert not seed_path(tmp_path, entry).exists()


def test_validator_error_blocks_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = make_entry(tmp_path)

    def invalid(*args: object, **kwargs: object) -> list[ValidationIssue]:
        return [
            ValidationIssue(
                code="SYNTHETIC_ERROR", message="Invalid", severity=IssueSeverity.ERROR
            )
        ]

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("approval must not run after validator error")

    monkeypatch.setattr(review_executor.CompetitionCandidateValidator, "validate", invalid)
    monkeypatch.setattr(review_executor, "approve_candidate", forbidden)
    result = run(tmp_path, entry, execute=True)

    assert result.status == "failed"
    assert result.code == "VALIDATION_ERRORS"


def test_hold_never_approves_verifies_or_creates_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = make_entry(tmp_path, approval="hold", verification="hold")

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("hold must not run workflow actions")

    monkeypatch.setattr(review_executor, "approve_candidate", forbidden)
    monkeypatch.setattr(review_executor, "verify_approved_bundle", forbidden)
    result = run(tmp_path, entry, execute=True)

    assert result.status == "held"
    assert not seed_path(tmp_path, entry).exists()


def test_dry_run_never_calls_approval_or_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = make_entry(tmp_path)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("dry-run must not run workflow actions")

    monkeypatch.setattr(review_executor, "approve_candidate", forbidden)
    monkeypatch.setattr(review_executor, "verify_approved_bundle", forbidden)
    assert run(tmp_path, entry).status == "planned"


def test_approve_verify_reuses_actions_and_builds_round_tripping_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = make_entry(tmp_path)
    calls: list[tuple[str, datetime]] = []
    approve = review_executor.approve_candidate
    verify = review_executor.verify_approved_bundle

    def traced_approve(*args: object, **kwargs: object) -> object:
        calls.append(("approve", kwargs["reviewed_at"]))
        return approve(*args, **kwargs)

    def traced_verify(*args: object, **kwargs: object) -> object:
        calls.append(("verify", kwargs["verified_at"]))
        return verify(*args, **kwargs)

    monkeypatch.setattr(review_executor, "approve_candidate", traced_approve)
    monkeypatch.setattr(review_executor, "verify_approved_bundle", traced_verify)
    result = run(tmp_path, entry, execute=True)

    assert result.status == "executed"
    assert calls == [("approve", EXECUTED_AT), ("verify", EXECUTED_AT)]
    seed = deserialize_seed(seed_path(tmp_path, entry).read_bytes())
    assert deserialize_seed(serialize_seed(seed)) == seed
    assert seed.approval.candidate_id == seed.verification.candidate_id == entry.candidate_id
    assert seed.approval.reviewed_at == EXECUTED_AT != entry.approval_decided_at
    assert seed.verification.verified_at == EXECUTED_AT != entry.source_verification_decided_at
    assert seed.competition_source.verification_status is VerificationStatus.VERIFIED
    assert seed.edition.source == seed.competition_source
    assert all(track.source == seed.competition_source for track in seed.tracks)
    assert not any(issue.severity is IssueSeverity.ERROR for issue in seed.validation_issues)
    assert "raw_payload" not in seed.model_dump_json()


def test_approve_with_verification_hold_never_verifies_or_writes_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = make_entry(tmp_path, verification="hold")
    calls = []
    approve = review_executor.approve_candidate

    def traced_approve(*args: object, **kwargs: object) -> object:
        calls.append("approve")
        return approve(*args, **kwargs)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("verification hold must not verify")

    monkeypatch.setattr(review_executor, "approve_candidate", traced_approve)
    monkeypatch.setattr(review_executor, "verify_approved_bundle", forbidden)
    assert run(tmp_path, entry, execute=True).status == "executed"
    assert calls == ["approve"]
    assert not seed_path(tmp_path, entry).exists()


def test_reject_uses_formal_action_and_never_creates_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = make_entry(tmp_path, approval="reject", verification="hold")
    calls = []
    reject = review_executor.reject_candidate

    def traced_reject(*args: object, **kwargs: object) -> object:
        calls.append(kwargs["reviewed_at"])
        return reject(*args, **kwargs)

    monkeypatch.setattr(review_executor, "reject_candidate", traced_reject)
    assert run(tmp_path, entry).status == "planned"
    assert run(tmp_path, entry, execute=True).status == "rejected"
    assert calls == [EXECUTED_AT]
    assert not seed_path(tmp_path, entry).exists()


def test_identical_existing_seed_is_not_rewritten_or_reexecuted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = make_entry(tmp_path)
    assert run(tmp_path, entry, execute=True).status == "executed"
    path = seed_path(tmp_path, entry)
    before = path.read_bytes()
    before_mtime = path.stat().st_mtime_ns

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("existing Seed must not repeat workflow actions")

    monkeypatch.setattr(review_executor, "approve_candidate", forbidden)
    monkeypatch.setattr(review_executor, "verify_approved_bundle", forbidden)
    assert run(tmp_path, entry).status == "already_materialized"
    later = execute_review_manifest(
        manifest(entry),
        tmp_path,
        execute=True,
        clock=lambda: EXECUTED_AT + timedelta(days=1),
    )
    assert later.entries[0].status == "already_materialized"
    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == before_mtime


def test_conflicting_existing_seed_fails_without_overwrite(tmp_path: Path) -> None:
    entry = make_entry(tmp_path)
    assert run(tmp_path, entry, execute=True).status == "executed"
    path = seed_path(tmp_path, entry)
    document = json.loads(path.read_bytes())
    document["approval"]["review_note"] = "Different human review"
    before = json.dumps(document).encode("utf-8")
    path.write_bytes(before)

    result = run(tmp_path, entry, execute=True)

    assert result.status == "failed"
    assert result.code == "EXISTING_SEED_CONFLICT"
    assert path.read_bytes() == before


def test_one_entry_failure_does_not_stop_other_dry_run_checks(tmp_path: Path) -> None:
    changed = make_entry(tmp_path, "first-2026")
    valid = make_entry(tmp_path, "second-2026")
    (tmp_path / changed.raw_fixture_path).write_bytes(b"changed")

    report = execute_review_manifest(manifest(changed, valid), tmp_path)

    assert [result.status for result in report.entries] == ["failed", "planned"]
    assert report.entries[0].code == "RAW_FIXTURE_CHANGED_AFTER_REVIEW"
    assert report.summary == {
        "planned": 1,
        "executed": 0,
        "held": 0,
        "rejected": 0,
        "failed": 1,
        "already_materialized": 0,
    }
    assert not report.passed


def test_manifest_file_is_loaded_through_schema(tmp_path: Path) -> None:
    entry = make_entry(tmp_path)
    path = tmp_path / "manifest.json"
    path.write_bytes(serialize_review_manifest(manifest(entry)))

    assert execute_review_file(path, tmp_path).entries[0].status == "planned"


def test_invalid_manifest_schema_stops_before_entries(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text('{"schema_version":"2.0","entries":[]}', encoding="utf-8")

    with pytest.raises(ReviewExecutionError) as error:
        execute_review_file(path, tmp_path, execute=True)

    assert error.value.code == "MANIFEST_SCHEMA_INVALID"
