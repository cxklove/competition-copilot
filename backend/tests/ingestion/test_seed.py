"""Contract tests for verified competition seed JSON, using synthetic facts only."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.source_metadata import VerificationStatus
from competition_copilot.ingestion.approval import approve_candidate, approved_bundle
from competition_copilot.ingestion.candidate import (
    CandidateStatus,
    CompetitionCandidate,
    IssueSeverity,
    ValidationIssue,
)
from competition_copilot.ingestion.models import RawCompetitionData
from competition_copilot.ingestion.normalizer import CompetitionNormalizer
from competition_copilot.ingestion.seed import (
    CompetitionSeedEnvelope,
    build_seed_envelope,
    deserialize_seed,
    serialize_seed,
)
from competition_copilot.ingestion.validator import CompetitionCandidateValidator
from competition_copilot.ingestion.verification import (
    VerifiedCompetitionBundle,
    verify_approved_bundle,
)

LOCAL_TIME = timezone(timedelta(hours=8))
OBSERVED_AT = datetime(2026, 10, 8, 12, 0, tzinfo=LOCAL_TIME)
REVIEWED_AT = datetime(2026, 10, 8, 13, 0, tzinfo=LOCAL_TIME)
VERIFIED_AT = datetime(2026, 10, 8, 14, 0, tzinfo=LOCAL_TIME)
RAW_PATH = "data/raw/example-2026.json"


def verified_inputs(
    warning: ValidationIssue | None = None,
    raw_overrides: dict[str, object] | None = None,
) -> tuple[
    CompetitionCandidate, VerifiedCompetitionBundle, list[ValidationIssue]
]:
    raw = RawCompetitionData(
        competition_id="example",
        name="Example Competition",
        edition_id="example-2026",
        edition_name="Example 2026",
        edition_year=2026,
        tracks=["Innovation", "Practice"],
        track_ids=["innovation", "practice"],
        source_url="https://example.org/notice",
        source_type="official",
        observed_at=OBSERVED_AT,
        raw_payload={"page_text": "Raw-only page text"},
    )
    if raw_overrides is not None:
        raw = RawCompetitionData.model_validate(
            {**raw.model_dump(), **raw_overrides}
        )
    competition, edition, tracks = CompetitionNormalizer().normalize(raw)
    candidate = CompetitionCandidate(
        id="candidate-1",
        raw_data=raw,
        competition=competition,
        edition=edition,
        tracks=tracks,
        created_at=OBSERVED_AT,
    )
    if warning is not None:
        candidate.validation_issues.append(warning)
    issues = CompetitionCandidateValidator().validate(candidate)
    assert issues == ([warning] if warning is not None else [])
    approve_candidate(candidate, reviewed_at=REVIEWED_AT, review_note="Human review")
    verified = verify_approved_bundle(
        candidate,
        approved_bundle(candidate),
        verified_at=VERIFIED_AT,
        verification_note="Source checked",
    )
    return candidate, verified, issues


def build_valid_seed() -> CompetitionSeedEnvelope:
    candidate, verified, issues = verified_inputs()
    return build_seed_envelope(candidate, verified, issues, RAW_PATH)


def test_approved_and_verified_inputs_build_seed() -> None:
    candidate, verified, issues = verified_inputs()
    candidate_before = candidate.model_dump(mode="json")
    verified_before = verified.model_dump(mode="json")

    seed = build_seed_envelope(candidate, verified, issues, RAW_PATH)

    assert seed.schema_version == "1.1"
    assert seed.temporal_provenance == []
    assert seed.artifact_type == "verified_competition_seed"
    assert seed.raw_fixture_path == RAW_PATH
    assert seed.approval.candidate_id == candidate.id
    assert seed.approval.status is CandidateStatus.APPROVED
    assert seed.approval.reviewed_at == REVIEWED_AT
    assert seed.approval.review_note == "Human review"
    assert seed.verification.verified_at == VERIFIED_AT
    assert seed.verification.verification_note == "Source checked"
    assert seed.validation_issues == []
    assert seed.competition.id == "example"
    assert seed.edition.id == "example-2026"
    assert seed.edition.year == 2026
    assert [track.name for track in seed.tracks] == ["Innovation", "Practice"]
    assert candidate.model_dump(mode="json") == candidate_before
    assert verified.model_dump(mode="json") == verified_before
    with pytest.raises(ValidationError):
        seed.schema_version = "2.0"
    with pytest.raises(ValidationError):
        seed.approval.review_note = "Changed"


def test_seed_is_detached_from_workflow_inputs() -> None:
    candidate, verified, issues = verified_inputs()
    seed = build_seed_envelope(candidate, verified, issues, RAW_PATH)

    candidate.review_note = "Later change"
    verified.edition.name = "Later change"
    verified.tracks[0].name = "Later change"
    issues.append(
        ValidationIssue(
            code="LATER", message="Added later", severity=IssueSeverity.WARNING
        )
    )

    assert seed.approval.review_note == "Human review"
    assert seed.edition.name == "Example 2026"
    assert seed.tracks[0].name == "Innovation"
    assert seed.validation_issues == []


def test_pending_candidate_is_rejected() -> None:
    candidate, verified, issues = verified_inputs()
    candidate.status = CandidateStatus.PENDING

    with pytest.raises(ValueError, match="candidate must be approved"):
        build_seed_envelope(candidate, verified, issues, RAW_PATH)


def test_verified_facts_must_match_approved_candidate() -> None:
    candidate, verified, issues = verified_inputs()
    verified.competition.name = "Another Competition"

    with pytest.raises(ValueError, match="do not match the approved candidate"):
        build_seed_envelope(candidate, verified, issues, RAW_PATH)


def test_missing_reviewed_at_is_rejected() -> None:
    candidate, verified, issues = verified_inputs()
    candidate.reviewed_at = None

    with pytest.raises(ValidationError, match="reviewed_at"):
        build_seed_envelope(candidate, verified, issues, RAW_PATH)


@pytest.mark.parametrize("review_note", [None, "", " \t "])
def test_missing_or_blank_review_note_is_rejected(review_note: str | None) -> None:
    candidate, verified, issues = verified_inputs()
    candidate.review_note = review_note

    with pytest.raises(ValidationError, match="review_note"):
        build_seed_envelope(candidate, verified, issues, RAW_PATH)


def test_pending_competition_source_is_rejected() -> None:
    candidate, verified, issues = verified_inputs()
    pending_source = verified.competition_source.model_copy(
        update={"verification_status": VerificationStatus.PENDING}
    )
    verified = verified.model_copy(update={"competition_source": pending_source})

    with pytest.raises(ValidationError, match="competition source must be verified"):
        build_seed_envelope(candidate, verified, issues, RAW_PATH)


def test_pending_edition_source_is_rejected() -> None:
    candidate, verified, issues = verified_inputs()
    pending_source = verified.competition_source.model_copy(
        update={"verification_status": VerificationStatus.PENDING}
    )
    edition = verified.edition.model_copy(update={"source": pending_source})
    verified = verified.model_copy(update={"edition": edition})

    with pytest.raises(ValidationError, match="edition source"):
        build_seed_envelope(candidate, verified, issues, RAW_PATH)


def test_any_pending_track_source_is_rejected() -> None:
    candidate, verified, issues = verified_inputs()
    pending_source = verified.competition_source.model_copy(
        update={"verification_status": VerificationStatus.PENDING}
    )
    tracks = [track.model_copy(deep=True) for track in verified.tracks]
    tracks[1].source = pending_source
    verified = verified.model_copy(update={"tracks": tracks})

    with pytest.raises(ValidationError, match="track source"):
        build_seed_envelope(candidate, verified, issues, RAW_PATH)


def test_verification_candidate_id_mismatch_is_rejected() -> None:
    candidate, verified, issues = verified_inputs()
    record = verified.verification.model_copy(update={"candidate_id": "other"})
    verified = verified.model_copy(update={"verification": record})

    with pytest.raises(ValidationError, match="candidate IDs differ"):
        build_seed_envelope(candidate, verified, issues, RAW_PATH)


def test_wrong_track_edition_id_is_rejected() -> None:
    candidate, verified, issues = verified_inputs()
    tracks = [track.model_copy(deep=True) for track in verified.tracks]
    tracks[1].edition_id = "other-edition"
    verified = verified.model_copy(update={"tracks": tracks})

    with pytest.raises(ValidationError, match="track edition ID"):
        build_seed_envelope(candidate, verified, issues, RAW_PATH)


def test_error_issue_is_rejected() -> None:
    candidate, verified, issues = verified_inputs()
    issues.append(
        ValidationIssue(
            code="INVALID_FACT", message="Fact requires correction", severity=IssueSeverity.ERROR
        )
    )

    with pytest.raises(ValidationError, match="error-level validation issues"):
        build_seed_envelope(candidate, verified, issues, RAW_PATH)


def test_warning_issue_is_preserved() -> None:
    warning = ValidationIssue(
        code="REVIEWED_WARNING",
        message="Nonblocking limitation",
        field="edition",
        severity=IssueSeverity.WARNING,
    )
    candidate, verified, issues = verified_inputs(warning)

    seed = build_seed_envelope(candidate, verified, issues, RAW_PATH)

    assert seed.validation_issues == [warning]
    assert deserialize_seed(serialize_seed(seed)).validation_issues == [warning]


@pytest.mark.parametrize("raw_fixture_path", ["", " \t "])
def test_blank_raw_fixture_path_is_rejected(raw_fixture_path: str) -> None:
    candidate, verified, issues = verified_inputs()

    with pytest.raises(ValidationError, match="raw_fixture_path"):
        build_seed_envelope(candidate, verified, issues, raw_fixture_path)


def test_raw_fixture_reference_stays_in_raw_directory() -> None:
    candidate, verified, issues = verified_inputs()

    with pytest.raises(ValidationError, match="data/raw/"):
        build_seed_envelope(candidate, verified, issues, "data/seed/example.json")


def test_json_round_trip_retains_audits_order_and_all_provenance() -> None:
    seed = build_valid_seed()
    payload = serialize_seed(seed)
    restored = deserialize_seed(payload)

    assert isinstance(payload, bytes)
    assert payload.decode("utf-8").startswith("{\n  ")
    assert restored == seed
    assert restored.approval.candidate_id == "candidate-1"
    assert restored.approval.reviewed_at.isoformat() == REVIEWED_AT.isoformat()
    assert restored.approval.review_note == "Human review"
    assert restored.verification.verified_at.isoformat() == VERIFIED_AT.isoformat()
    assert restored.verification.verification_note == "Source checked"
    assert restored.verification.previous_status is VerificationStatus.PENDING
    assert restored.verification.new_status is VerificationStatus.VERIFIED
    assert restored.competition.id == "example"
    assert restored.edition.id == "example-2026"
    assert restored.edition.year == 2026
    assert [track.id for track in restored.tracks] == ["innovation", "practice"]
    for source in (
        restored.competition_source,
        restored.edition.source,
        *(track.source for track in restored.tracks),
    ):
        assert source is not None
        assert str(source.source_url) == "https://example.org/notice"
        assert source.source_type.value == "official"
        assert source.observed_at.isoformat() == OBSERVED_AT.isoformat()
        assert source.verification_status is VerificationStatus.VERIFIED


def test_seed_schema_excludes_raw_payload_and_rejects_extra_fields() -> None:
    seed = build_valid_seed()
    payload = serialize_seed(seed)

    assert b"raw_payload" not in payload
    assert b"Raw-only page text" not in payload
    with pytest.raises(ValidationError, match="raw_payload"):
        CompetitionSeedEnvelope.model_validate(
            {**seed.model_dump(), "raw_payload": {"page_text": "Raw-only page text"}}
        )


def test_seed_rejects_invalid_version_or_artifact_type_on_load() -> None:
    seed_data = build_valid_seed().model_dump()
    with pytest.raises(ValidationError, match="schema_version"):
        CompetitionSeedEnvelope.model_validate({**seed_data, "schema_version": "2.0"})
    with pytest.raises(ValidationError, match="artifact_type"):
        CompetitionSeedEnvelope.model_validate({**seed_data, "artifact_type": "raw"})


def test_seed_1_1_carries_only_reviewed_raw_temporal_provenance() -> None:
    candidate, verified, issues = verified_inputs(
        raw_overrides={
            "registration_end": "2026-03-31T16:00:00+08:00",
            "temporal_provenance": [
                {
                    "field": "registration_end",
                    "timezone_name": "Asia/Shanghai",
                    "timezone_basis": "jurisdiction_default",
                    "precision": "minute",
                    "source_text": "报名截止：2026年3月31日16:00",
                }
            ],
        }
    )

    seed = build_seed_envelope(candidate, verified, issues, RAW_PATH)
    restored = deserialize_seed(serialize_seed(seed))

    assert restored == seed
    assert seed.schema_version == "1.1"
    assert seed.edition.registration_window.start_at is None
    assert seed.edition.registration_window.end_at.isoformat() == (
        "2026-03-31T16:00:00+08:00"
    )
    assert seed.temporal_provenance[0].field == "registration_end"
    assert seed.temporal_provenance[0].timezone_basis == "jurisdiction_default"
    assert "source_text" not in seed.model_dump_json()


def test_seed_builder_does_not_invent_provenance_from_offset() -> None:
    candidate, verified, issues = verified_inputs(
        raw_overrides={"registration_end": "2026-03-31T16:00:00+08:00"}
    )

    seed = build_seed_envelope(candidate, verified, issues, RAW_PATH)

    assert seed.temporal_provenance == []
    assert deserialize_seed(serialize_seed(seed)) == seed


def test_seed_1_0_loads_and_serializes_without_new_field() -> None:
    data = build_valid_seed().model_dump()
    data["schema_version"] = "1.0"
    data.pop("temporal_provenance")

    old_seed = CompetitionSeedEnvelope.model_validate(data)
    serialized = serialize_seed(old_seed)

    assert old_seed.temporal_provenance == []
    assert b"temporal_provenance" not in serialized
    assert deserialize_seed(serialized) == old_seed


def test_seed_versions_require_their_respective_temporal_field_shape() -> None:
    data = build_valid_seed().model_dump()

    with pytest.raises(ValidationError, match="Seed 1.1 requires"):
        CompetitionSeedEnvelope.model_validate(
            {key: value for key, value in data.items() if key != "temporal_provenance"}
        )
    with pytest.raises(ValidationError, match="Seed 1.0 cannot contain"):
        CompetitionSeedEnvelope.model_validate({**data, "schema_version": "1.0"})


def test_verification_record_must_end_verified() -> None:
    candidate, verified, issues = verified_inputs()
    record = verified.verification.model_copy(
        update={"new_status": VerificationStatus.PENDING}
    )
    verified = verified.model_copy(update={"verification": record})

    with pytest.raises(ValidationError, match="pending to verified"):
        build_seed_envelope(candidate, verified, issues, RAW_PATH)
