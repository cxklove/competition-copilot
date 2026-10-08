from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.source_metadata import VerificationStatus
from competition_copilot.ingestion.approval import (
    ApprovedCompetitionBundle,
    approve_candidate,
    approved_bundle,
    mark_duplicate,
    reject_candidate,
)
from competition_copilot.ingestion.candidate import (
    CandidateStatus,
    CompetitionCandidate,
)
from competition_copilot.ingestion.models import RawCompetitionData
from competition_copilot.ingestion.normalizer import CompetitionNormalizer
from competition_copilot.ingestion.verification import (
    SourceVerificationError,
    SourceVerificationRecord,
    VerifiedCompetitionBundle,
    verify_approved_bundle,
)

OBSERVED_AT = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
APPROVED_AT = datetime(2026, 10, 8, 13, 0, tzinfo=timezone.utc)
VERIFIED_AT = datetime(2026, 10, 8, 21, 0, tzinfo=timezone(timedelta(hours=8)))


def pending_candidate() -> CompetitionCandidate:
    raw = RawCompetitionData(
        competition_id="example",
        name="Example Competition",
        edition_id="example-2026",
        edition_name="2026 Edition",
        edition_year=2026,
        tracks=["Innovation", "Practice"],
        track_ids=["innovation", "practice"],
        source_url="https://example.org/notice",
        source_type="official",
        observed_at=OBSERVED_AT,
    )
    competition, edition, tracks = CompetitionNormalizer().normalize(raw)
    return CompetitionCandidate(
        id="candidate-1",
        raw_data=raw,
        competition=competition,
        edition=edition,
        tracks=tracks,
        created_at=OBSERVED_AT,
    )


def approved_inputs() -> tuple[CompetitionCandidate, ApprovedCompetitionBundle]:
    candidate = pending_candidate()
    approve_candidate(candidate, reviewed_at=APPROVED_AT, review_note="Reviewed")
    return candidate, approved_bundle(candidate)


def test_pending_candidate_cannot_be_source_verified() -> None:
    candidate, bundle = approved_inputs()
    candidate.status = CandidateStatus.PENDING

    with pytest.raises(SourceVerificationError) as error:
        verify_approved_bundle(
            candidate, bundle, verified_at=VERIFIED_AT, verification_note="Checked"
        )

    assert error.value.code == "CANDIDATE_NOT_APPROVED"


@pytest.mark.parametrize("action", [reject_candidate, mark_duplicate])
def test_rejected_or_duplicate_candidate_cannot_be_source_verified(
    action: object,
) -> None:
    candidate, bundle = approved_inputs()
    candidate.status = CandidateStatus.PENDING
    action(candidate, reviewed_at=APPROVED_AT)

    with pytest.raises(SourceVerificationError) as error:
        verify_approved_bundle(
            candidate, bundle, verified_at=VERIFIED_AT, verification_note="Checked"
        )

    assert error.value.code == "CANDIDATE_NOT_APPROVED"


def test_explicit_verification_preserves_facts_and_original_objects() -> None:
    candidate, bundle = approved_inputs()
    assert bundle.edition.source is not None
    before_source = bundle.edition.source.model_dump(mode="json")
    before_observed_at = bundle.edition.source.observed_at
    before_candidate = candidate.model_dump(mode="json")
    before_bundle = bundle.model_dump(mode="json")

    verified = verify_approved_bundle(
        candidate,
        bundle,
        verified_at=VERIFIED_AT,
        verification_note="Source checked against its notice",
    )

    assert isinstance(verified, VerifiedCompetitionBundle)
    assert candidate.status is CandidateStatus.APPROVED
    assert verified.competition == bundle.competition
    assert verified.competition is not bundle.competition
    assert verified.competition_source.verification_status is VerificationStatus.VERIFIED
    assert verified.edition.source is not None
    assert verified.edition.source.verification_status is VerificationStatus.VERIFIED
    assert len(verified.tracks) == 2
    assert all(
        track.source is not None
        and track.source.verification_status is VerificationStatus.VERIFIED
        for track in verified.tracks
    )
    assert verified.edition.source == verified.competition_source
    assert all(track.source == verified.competition_source for track in verified.tracks)
    assert str(verified.competition_source.source_url) == before_source["source_url"]
    assert verified.competition_source.source_type.value == before_source["source_type"]
    assert verified.competition_source.observed_at == before_observed_at
    assert candidate.model_dump(mode="json") == before_candidate
    assert bundle.model_dump(mode="json") == before_bundle
    assert bundle.edition.source.verification_status is VerificationStatus.PENDING
    assert all(
        track.source is not None
        and track.source.verification_status is VerificationStatus.PENDING
        for track in bundle.tracks
    )


def test_verification_record_is_immutable_and_round_trips() -> None:
    candidate, bundle = approved_inputs()
    verified = verify_approved_bundle(
        candidate, bundle, verified_at=VERIFIED_AT, verification_note="Checked source"
    )
    record = verified.verification

    assert record.candidate_id == candidate.id
    assert record.verified_at == VERIFIED_AT
    assert record.verification_note == "Checked source"
    assert record.previous_status is VerificationStatus.PENDING
    assert record.new_status is VerificationStatus.VERIFIED
    assert record.source_url == verified.competition_source.source_url
    assert SourceVerificationRecord.model_validate_json(record.model_dump_json()) == record
    assert (
        VerifiedCompetitionBundle.model_validate_json(verified.model_dump_json())
        == verified
    )
    with pytest.raises(ValidationError):
        record.verification_note = "Overwritten"


def test_naive_verified_at_is_rejected_without_mutation() -> None:
    candidate, bundle = approved_inputs()
    before = bundle.model_dump(mode="json")

    with pytest.raises(SourceVerificationError) as error:
        verify_approved_bundle(
            candidate,
            bundle,
            verified_at=datetime(2026, 10, 8, 21, 0),
            verification_note="Checked",
        )

    assert error.value.code == "INVALID_VERIFIED_AT"
    assert bundle.model_dump(mode="json") == before


@pytest.mark.parametrize("note", ["", " \t "])
def test_blank_verification_note_is_rejected(note: str) -> None:
    candidate, bundle = approved_inputs()

    with pytest.raises(SourceVerificationError) as error:
        verify_approved_bundle(
            candidate, bundle, verified_at=VERIFIED_AT, verification_note=note
        )

    assert error.value.code == "INVALID_VERIFICATION_NOTE"


def test_repeated_verification_of_verified_input_is_rejected() -> None:
    candidate, bundle = approved_inputs()
    verified = verify_approved_bundle(
        candidate, bundle, verified_at=VERIFIED_AT, verification_note="First check"
    )
    original_record = verified.verification.model_dump(mode="json")

    with pytest.raises(SourceVerificationError) as error:
        verify_approved_bundle(
            candidate,
            verified,
            verified_at=VERIFIED_AT + timedelta(hours=1),
            verification_note="Second check",
        )

    assert error.value.code == "ALREADY_VERIFIED"
    assert verified.verification.model_dump(mode="json") == original_record


def test_existing_verified_source_is_rejected() -> None:
    candidate, bundle = approved_inputs()
    assert candidate.edition is not None
    assert bundle.edition.source is not None
    verified_source = bundle.edition.source.model_copy(
        update={"verification_status": VerificationStatus.VERIFIED}
    )
    candidate.edition.source = verified_source
    bundle.edition.source = verified_source

    with pytest.raises(SourceVerificationError) as error:
        verify_approved_bundle(
            candidate, bundle, verified_at=VERIFIED_AT, verification_note="Checked"
        )

    assert error.value.code == "ALREADY_VERIFIED"


def test_raw_provenance_mismatch_is_rejected() -> None:
    candidate, bundle = approved_inputs()
    candidate.raw_data.source_url = "https://example.org/other-notice"

    with pytest.raises(SourceVerificationError) as error:
        verify_approved_bundle(
            candidate, bundle, verified_at=VERIFIED_AT, verification_note="Checked"
        )

    assert error.value.code == "PROVENANCE_MISMATCH"
