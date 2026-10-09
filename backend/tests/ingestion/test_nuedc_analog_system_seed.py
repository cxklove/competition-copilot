"""Regression checks for the reviewed 2026 NUEDC analog system seed."""

import json
from datetime import timezone
from pathlib import Path

from competition_copilot.domain.source_metadata import VerificationStatus
from competition_copilot.ingestion.candidate import CandidateStatus
from competition_copilot.ingestion.models import RawCompetitionData
from competition_copilot.ingestion.normalizer import CompetitionNormalizer
from competition_copilot.ingestion.seed import CompetitionSeedEnvelope

ROOT = Path(__file__).resolve().parents[3]
RAW_PATH = ROOT / "data/raw/nuedc-analog-system-2026.json"
SEED_PATH = ROOT / "data/seed/nuedc-analog-system-2026.json"


def test_raw_review_preserves_stage_rules_without_inferred_structure() -> None:
    raw = RawCompetitionData.model_validate_json(RAW_PATH.read_bytes())

    assert raw.competition_id == "nuedc-analog-system"
    assert raw.edition_id == "nuedc-analog-system-2026"
    assert raw.edition_year == 2026
    assert raw.source_url == "https://www.nuedc-training.com.cn/index/news/details/new_id/353"
    assert raw.source_type == "official"
    assert raw.observed_at.utcoffset() is not None
    assert raw.registration_start is None and raw.registration_end is None
    assert raw.competition_start is None and raw.competition_end is None
    assert raw.tracks == [] and raw.track_ids == []
    assert raw.raw_payload is not None
    assert raw.raw_payload["eligibility_text"]
    assert raw.raw_payload["team_text"]

    competition, edition, tracks = CompetitionNormalizer().normalize(raw)

    assert competition.id == raw.competition_id
    assert edition.id == raw.edition_id and edition.year == 2026
    assert edition.registration_window is None
    assert edition.competition_window is None
    assert tracks == []
    assert edition.source is not None
    assert edition.source.verification_status is VerificationStatus.PENDING


def test_verified_seed_round_trip_keeps_audit_and_raw_boundary() -> None:
    payload = SEED_PATH.read_bytes()
    seed = CompetitionSeedEnvelope.model_validate_json(payload)
    raw = RawCompetitionData.model_validate_json(RAW_PATH.read_bytes())
    document = json.loads(payload)

    assert seed.schema_version == "1.0"
    assert seed.artifact_type == "verified_competition_seed"
    assert seed.raw_fixture_path == "data/raw/nuedc-analog-system-2026.json"
    assert seed.validation_issues == []
    assert seed.competition.id == "nuedc-analog-system"
    assert seed.edition.id == "nuedc-analog-system-2026"
    assert seed.edition.year == 2026
    assert seed.edition.registration_window is None
    assert seed.edition.competition_window is None
    assert seed.tracks == []
    assert seed.approval.status is CandidateStatus.APPROVED
    assert seed.verification.previous_status is VerificationStatus.PENDING
    assert seed.verification.new_status is VerificationStatus.VERIFIED
    assert seed.competition_source.verification_status is VerificationStatus.VERIFIED
    assert seed.edition.source == seed.competition_source
    assert seed.approval.candidate_id == seed.verification.candidate_id
    assert seed.approval.candidate_id == "nuedc-analog-system-2026-candidate"
    assert (
        raw.observed_at.astimezone(timezone.utc)
        <= seed.approval.reviewed_at.astimezone(timezone.utc)
        <= seed.verification.verified_at.astimezone(timezone.utc)
    )
    assert not {
        "raw_payload",
        "eligibility_text",
        "team_text",
        "registration_text",
        "competition_text",
        "notes",
    }.intersection(document)
    assert CompetitionSeedEnvelope.model_validate_json(payload) == seed
