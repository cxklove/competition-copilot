"""Human decision records are explicit, versioned, and bound to Raw bytes."""

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from competition_copilot.ingestion import approval, verification
from competition_copilot.ingestion.review_manifest import (
    ApprovalDecision,
    HumanReviewEntry,
    HumanReviewManifest,
    RawBindingError,
    SourceVerificationDecision,
    compute_file_sha256,
    deserialize_review_manifest,
    serialize_review_manifest,
    validate_raw_binding,
)

APPROVAL_TIME = datetime(2026, 10, 9, 10, 0, tzinfo=timezone(timedelta(hours=8)))
VERIFICATION_TIME = datetime(2026, 10, 9, 3, 0, tzinfo=timezone.utc)


def raw_file(tmp_path: Path, filename: str = "sample.json") -> Path:
    path = tmp_path / "data/raw" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'{"source":"example"}\n')
    return path


def entry_data(tmp_path: Path, **overrides: object) -> dict[str, object]:
    path = raw_file(tmp_path)
    data: dict[str, object] = {
        "raw_fixture_path": "data/raw/sample.json",
        "raw_sha256": compute_file_sha256(path),
        "competition_id": "example",
        "edition_id": "example-2026",
        "candidate_id": "example-2026-candidate",
        "approval_decision": "approve",
        "approval_decided_at": APPROVAL_TIME,
        "review_note": "Human checked the original notice",
        "source_verification_decision": "hold",
        "source_verification_decided_at": None,
        "verification_note": None,
    }
    data.update(overrides)
    return data


def manifest_with(entry: HumanReviewEntry) -> HumanReviewManifest:
    return HumanReviewManifest(
        schema_version="1.0",
        artifact_type="human_review_manifest",
        entries=[entry],
    )


def test_empty_manifest_is_valid_and_round_trips() -> None:
    manifest = HumanReviewManifest(
        schema_version="1.0", artifact_type="human_review_manifest", entries=[]
    )

    assert deserialize_review_manifest(serialize_review_manifest(manifest)) == manifest


@pytest.mark.parametrize(
    ("decision", "decided_at"),
    [
        (ApprovalDecision.APPROVE, APPROVAL_TIME),
        (ApprovalDecision.REJECT, APPROVAL_TIME),
        (ApprovalDecision.HOLD, None),
    ],
)
def test_approval_decisions_round_trip(
    tmp_path: Path, decision: ApprovalDecision, decided_at: datetime | None
) -> None:
    entry = HumanReviewEntry.model_validate(
        entry_data(
            tmp_path,
            approval_decision=decision,
            approval_decided_at=decided_at,
        )
    )
    manifest = manifest_with(entry)

    restored = deserialize_review_manifest(serialize_review_manifest(manifest))

    assert restored == manifest
    assert restored.entries[0].approval_decision is decision
    assert restored.entries[0].approval_decided_at == decided_at
    assert restored.entries[0].source_verification_decision is SourceVerificationDecision.HOLD


def test_verify_decision_requires_approved_entry_and_round_trips(tmp_path: Path) -> None:
    entry = HumanReviewEntry.model_validate(
        entry_data(
            tmp_path,
            source_verification_decision="verify",
            source_verification_decided_at=VERIFICATION_TIME,
            verification_note="Human checked official source",
        )
    )

    restored = deserialize_review_manifest(serialize_review_manifest(manifest_with(entry)))

    assert restored.entries[0].approval_decision is ApprovalDecision.APPROVE
    assert (
        restored.entries[0].source_verification_decision
        is SourceVerificationDecision.VERIFY
    )
    assert restored.entries[0].source_verification_decided_at == VERIFICATION_TIME


@pytest.mark.parametrize("decision", ["reject", "hold"])
def test_reject_or_hold_cannot_pair_with_verify(tmp_path: Path, decision: str) -> None:
    data = entry_data(
        tmp_path,
        approval_decision=decision,
        approval_decided_at=APPROVAL_TIME if decision == "reject" else None,
        source_verification_decision="verify",
        source_verification_decided_at=VERIFICATION_TIME,
        verification_note="Human checked source",
    )

    with pytest.raises(ValidationError, match="verify requires an approve decision"):
        HumanReviewEntry.model_validate(data)


@pytest.mark.parametrize("decision", ["approve", "reject", "hold"])
def test_every_approval_decision_requires_review_note(
    tmp_path: Path, decision: str
) -> None:
    data = entry_data(
        tmp_path,
        approval_decision=decision,
        approval_decided_at=APPROVAL_TIME if decision != "hold" else None,
        review_note="  ",
    )

    with pytest.raises(ValidationError, match="review_note"):
        HumanReviewEntry.model_validate(data)


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_approve_and_reject_require_decision_time(tmp_path: Path, decision: str) -> None:
    with pytest.raises(ValidationError, match="approval_decided_at"):
        HumanReviewEntry.model_validate(
            entry_data(tmp_path, approval_decision=decision, approval_decided_at=None)
        )


def test_verify_requires_decision_time_and_note(tmp_path: Path) -> None:
    data = entry_data(
        tmp_path,
        source_verification_decision="verify",
        verification_note="Human checked source",
    )
    with pytest.raises(ValidationError, match="source_verification_decided_at"):
        HumanReviewEntry.model_validate(data)

    data["source_verification_decided_at"] = VERIFICATION_TIME
    data["verification_note"] = "  "
    with pytest.raises(ValidationError, match="verification_note"):
        HumanReviewEntry.model_validate(data)


@pytest.mark.parametrize("field", ["approval_decided_at", "source_verification_decided_at"])
def test_naive_decision_time_is_rejected(tmp_path: Path, field: str) -> None:
    data = entry_data(
        tmp_path,
        source_verification_decision="verify",
        source_verification_decided_at=VERIFICATION_TIME,
        verification_note="Human checked source",
    )
    data[field] = datetime(2026, 10, 9, 10, 0)

    with pytest.raises(ValidationError, match=field):
        HumanReviewEntry.model_validate(data)


@pytest.mark.parametrize("bad_sha", ["", "a" * 63, "A" * 64, "g" * 64])
def test_raw_sha256_requires_exact_lowercase_hex(
    tmp_path: Path, bad_sha: str
) -> None:
    with pytest.raises(ValidationError, match="raw_sha256"):
        HumanReviewEntry.model_validate(entry_data(tmp_path, raw_sha256=bad_sha))


@pytest.mark.parametrize(
    "field", ["raw_fixture_path", "competition_id", "edition_id", "candidate_id"]
)
def test_identifiers_must_not_be_blank(tmp_path: Path, field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        HumanReviewEntry.model_validate(entry_data(tmp_path, **{field: " \t "}))


def test_duplicate_raw_fixture_path_is_rejected(tmp_path: Path) -> None:
    first = HumanReviewEntry.model_validate(entry_data(tmp_path))
    second = first.model_copy(update={"candidate_id": "other-candidate"})

    with pytest.raises(ValidationError, match="raw_fixture_path must be unique"):
        HumanReviewManifest(
            schema_version="1.0",
            artifact_type="human_review_manifest",
            entries=[first, second],
        )


def test_duplicate_candidate_id_is_rejected(tmp_path: Path) -> None:
    first = HumanReviewEntry.model_validate(entry_data(tmp_path))
    second = first.model_copy(update={"raw_fixture_path": "data/raw/other.json"})

    with pytest.raises(ValidationError, match="candidate_id must be unique"):
        HumanReviewManifest(
            schema_version="1.0",
            artifact_type="human_review_manifest",
            entries=[first, second],
        )


def test_file_sha256_is_deterministic_and_tracks_exact_bytes(tmp_path: Path) -> None:
    path = raw_file(tmp_path)
    before_bytes = path.read_bytes()
    expected = hashlib.sha256(before_bytes).hexdigest()

    assert compute_file_sha256(path) == expected
    assert compute_file_sha256(path) == expected
    assert path.read_bytes() == before_bytes

    path.write_bytes(before_bytes + b" ")
    assert compute_file_sha256(path) != expected


def test_raw_binding_passes_unchanged_and_fails_after_change(tmp_path: Path) -> None:
    entry = HumanReviewEntry.model_validate(entry_data(tmp_path))
    path = tmp_path / entry.raw_fixture_path

    assert validate_raw_binding(entry, tmp_path) is None
    path.write_bytes(path.read_bytes() + b"\n")

    with pytest.raises(RawBindingError) as error:
        validate_raw_binding(entry, tmp_path)
    assert error.value.code == "RAW_FIXTURE_CHANGED_AFTER_REVIEW"
    assert entry.raw_sha256 != compute_file_sha256(path)


def test_raw_binding_rejects_missing_or_outside_project(tmp_path: Path) -> None:
    entry = HumanReviewEntry.model_validate(entry_data(tmp_path))
    (tmp_path / entry.raw_fixture_path).unlink()

    with pytest.raises(RawBindingError) as missing:
        validate_raw_binding(entry, tmp_path)
    assert missing.value.code == "RAW_FIXTURE_UNAVAILABLE"

    outside = entry.model_copy(update={"raw_fixture_path": "../outside.json"})
    with pytest.raises(RawBindingError) as escaped:
        validate_raw_binding(outside, tmp_path)
    assert escaped.value.code == "RAW_FIXTURE_PATH_OUTSIDE_PROJECT"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2.0"),
        ("artifact_type", "verified_competition_seed"),
    ],
)
def test_manifest_version_and_type_are_fixed(field: str, value: str) -> None:
    data = {
        "schema_version": "1.0",
        "artifact_type": "human_review_manifest",
        "entries": [],
    }
    data[field] = value

    with pytest.raises(ValidationError, match=field):
        HumanReviewManifest.model_validate(data)


def test_manifest_requires_explicit_version_type_and_entries() -> None:
    with pytest.raises(ValidationError):
        HumanReviewManifest.model_validate({})


@pytest.mark.parametrize(
    ("field", "value"),
    [("approval_decision", "auto"), ("source_verification_decision", "pass")],
)
def test_automatic_decision_values_are_not_supported(
    tmp_path: Path, field: str, value: str
) -> None:
    with pytest.raises(ValidationError, match=field):
        HumanReviewEntry.model_validate(entry_data(tmp_path, **{field: value}))


def test_manifest_validation_never_calls_approval_or_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Manifest validation executed a workflow action")

    monkeypatch.setattr(approval, "approve_candidate", forbidden)
    monkeypatch.setattr(verification, "verify_approved_bundle", forbidden)
    entry = HumanReviewEntry.model_validate(
        entry_data(
            tmp_path,
            source_verification_decision="verify",
            source_verification_decided_at=VERIFICATION_TIME,
            verification_note="Human checked source",
        )
    )

    manifest = manifest_with(entry)
    assert deserialize_review_manifest(serialize_review_manifest(manifest)) == manifest
    assert validate_raw_binding(entry, tmp_path) is None
