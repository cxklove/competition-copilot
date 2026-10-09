"""Read-only integration checks for the complete P2 ingestion artifact chain."""

import json
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from competition_copilot.domain.source_metadata import VerificationStatus
from competition_copilot.ingestion.batch_audit import audit_fixtures
from competition_copilot.ingestion.candidate import (
    CandidateStatus,
    CompetitionCandidate,
    IssueSeverity,
    ValidationIssue,
)
from competition_copilot.ingestion.models import RawCompetitionData
from competition_copilot.ingestion.normalizer import CompetitionNormalizer
from competition_copilot.ingestion.review_manifest import (
    ApprovalDecision,
    HumanReviewManifest,
    SourceVerificationDecision,
    deserialize_review_manifest,
    serialize_review_manifest,
    validate_raw_binding,
)
from competition_copilot.ingestion.seed import (
    CompetitionSeedEnvelope,
    deserialize_seed,
    serialize_seed,
)
from competition_copilot.ingestion.temporal_provenance import (
    TemporalField,
    TemporalPrecision,
    TimezoneBasis,
    validate_timezone_offset,
)
from competition_copilot.ingestion.validator import CompetitionCandidateValidator

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data/raw"
SEED_DIR = ROOT / "data/seed"
REVIEW_DIR = ROOT / "data/review"
LEGACY_PRE_MANIFEST_EDITIONS = frozenset(
    {
        "huawei-ict-2026",
        "c4-big-data-challenge-2026",
        "nuedc-analog-system-2026",
    }
)
TIME_FIELD_ENDPOINT = {
    TemporalField.REGISTRATION_START: ("registration_window", "start_at"),
    TemporalField.REGISTRATION_END: ("registration_window", "end_at"),
    TemporalField.COMPETITION_START: ("competition_window", "start_at"),
    TemporalField.COMPETITION_END: ("competition_window", "end_at"),
}


@dataclass(frozen=True)
class RawCase:
    candidate: CompetitionCandidate
    issues: list[ValidationIssue]


@dataclass(frozen=True)
class SeedCase:
    path: Path
    seed: CompetitionSeedEnvelope


@dataclass(frozen=True)
class ManifestCase:
    path: Path
    manifest: HumanReviewManifest


@dataclass(frozen=True)
class Corpus:
    raws: dict[str, RawCase]
    seeds: tuple[SeedCase, ...]
    manifests: tuple[ManifestCase, ...]


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    """Discover and load real artifacts without changing review or seed state."""

    raw_paths = sorted(RAW_DIR.glob("*.json"))
    seed_paths = sorted(SEED_DIR.glob("*.json"))
    assert raw_paths, "P2 integration requires Raw fixtures"
    assert seed_paths, "P2 integration requires verified Seeds"

    raws = {}
    for path in raw_paths:
        raw = RawCompetitionData.model_validate_json(path.read_bytes())
        competition, edition, tracks = CompetitionNormalizer().normalize(raw)
        candidate = CompetitionCandidate(
            id=f"{edition.id}-candidate",
            raw_data=raw,
            competition=competition,
            edition=edition,
            tracks=tracks,
            created_at=raw.observed_at,
        )
        relative_path = path.relative_to(ROOT).as_posix()
        raws[relative_path] = RawCase(
            candidate=candidate,
            issues=CompetitionCandidateValidator().validate(candidate),
        )

    seeds = tuple(
        SeedCase(path, CompetitionSeedEnvelope.model_validate_json(path.read_bytes()))
        for path in seed_paths
    )
    manifests = tuple(
        ManifestCase(path, HumanReviewManifest.model_validate_json(path.read_bytes()))
        for path in sorted(REVIEW_DIR.glob("*.json"))
    )
    return Corpus(raws=raws, seeds=seeds, manifests=manifests)


def _assert_no_raw_payload(value: object) -> None:
    if isinstance(value, dict):
        assert "raw_payload" not in value
        for nested in value.values():
            _assert_no_raw_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_raw_payload(nested)


def test_raw_pipeline_and_domain_relationships(corpus: Corpus) -> None:
    competition_ids = []
    edition_ids = []
    candidate_ids = []
    track_ids = []

    for path, case in corpus.raws.items():
        candidate = case.candidate
        competition = candidate.competition
        edition = candidate.edition
        assert competition is not None, path
        assert edition is not None, path
        assert candidate.status is CandidateStatus.PENDING, path
        assert not [issue for issue in case.issues if issue.severity is IssueSeverity.ERROR], path
        assert not [issue for issue in case.issues if issue.severity is IssueSeverity.WARNING], path
        assert edition.competition_id == competition.id, path
        assert edition.source is not None, path
        assert edition.source.verification_status is VerificationStatus.PENDING, path
        competition_ids.append(competition.id)
        edition_ids.append(edition.id)
        candidate_ids.append(candidate.id)
        for track in candidate.tracks:
            assert track.edition_id == edition.id, path
            track_ids.append(track.id)

    for identifiers in (competition_ids, edition_ids, candidate_ids, track_ids):
        assert len(identifiers) == len(set(identifiers))


def test_seeds_are_verified_round_tripping_and_raw_free(corpus: Corpus) -> None:
    for case in corpus.seeds:
        seed = case.seed
        serialized = serialize_seed(seed)
        assert deserialize_seed(serialized) == seed, case.path
        assert seed.schema_version in {"1.0", "1.1"}, case.path
        assert seed.approval.status is CandidateStatus.APPROVED, case.path
        assert seed.verification.previous_status is VerificationStatus.PENDING, case.path
        assert seed.verification.new_status is VerificationStatus.VERIFIED, case.path
        assert seed.approval.candidate_id == seed.verification.candidate_id, case.path
        assert seed.edition.competition_id == seed.competition.id, case.path
        assert all(track.edition_id == seed.edition.id for track in seed.tracks), case.path
        assert not any(
            issue.severity is IssueSeverity.ERROR for issue in seed.validation_issues
        ), case.path
        _assert_no_raw_payload(json.loads(serialized))


def test_raw_to_seed_structured_facts_and_source_identity(corpus: Corpus) -> None:
    seed_by_raw = {case.seed.raw_fixture_path: case.seed for case in corpus.seeds}
    assert len(seed_by_raw) == len(corpus.seeds), "Two Seeds reference one Raw fixture"
    assert set(seed_by_raw) == set(corpus.raws), "Every Raw must have one matching Seed"

    for path, raw_case in corpus.raws.items():
        candidate = raw_case.candidate
        seed = seed_by_raw[path]
        assert seed.approval.candidate_id == candidate.id, path
        assert seed.competition == candidate.competition, path
        assert candidate.edition is not None
        assert seed.edition.model_dump(exclude={"source"}) == candidate.edition.model_dump(
            exclude={"source"}
        ), path
        assert [track.model_dump(exclude={"source"}) for track in seed.tracks] == [
            track.model_dump(exclude={"source"}) for track in candidate.tracks
        ], path
        assert candidate.edition.source is not None
        pending_source = seed.competition_source.model_copy(
            update={"verification_status": VerificationStatus.PENDING}
        )
        assert pending_source == candidate.edition.source, path
        assert seed.validation_issues == raw_case.issues, path


def test_manifests_bind_raw_and_match_human_decision_chain(corpus: Corpus) -> None:
    managed_raw_paths = []
    managed_candidate_ids = []
    seeds_by_candidate = {case.seed.approval.candidate_id: case.seed for case in corpus.seeds}
    assert len(seeds_by_candidate) == len(corpus.seeds)

    for case in corpus.manifests:
        manifest = case.manifest
        assert deserialize_review_manifest(serialize_review_manifest(manifest)) == manifest
        for entry in manifest.entries:
            assert entry.raw_fixture_path in corpus.raws, case.path
            validate_raw_binding(entry, ROOT)
            candidate = corpus.raws[entry.raw_fixture_path].candidate
            assert candidate.competition is not None
            assert candidate.edition is not None
            assert entry.competition_id == candidate.competition.id
            assert entry.edition_id == candidate.edition.id
            assert entry.candidate_id == candidate.id
            managed_raw_paths.append(entry.raw_fixture_path)
            managed_candidate_ids.append(entry.candidate_id)

            if (
                entry.approval_decision is ApprovalDecision.APPROVE
                and entry.source_verification_decision is SourceVerificationDecision.VERIFY
            ):
                assert entry.candidate_id in seeds_by_candidate, entry.raw_fixture_path
                seed = seeds_by_candidate[entry.candidate_id]
                assert seed.raw_fixture_path == entry.raw_fixture_path
                assert seed.competition.id == entry.competition_id
                assert seed.edition.id == entry.edition_id
                assert seed.verification.candidate_id == entry.candidate_id
                assert seed.approval.review_note == entry.review_note
                assert seed.verification.verification_note == entry.verification_note
            else:
                assert entry.candidate_id not in seeds_by_candidate, entry.raw_fixture_path

    assert len(managed_raw_paths) == len(set(managed_raw_paths))
    assert len(managed_candidate_ids) == len(set(managed_candidate_ids))


def test_only_named_pre_manifest_seeds_lack_review_entries(corpus: Corpus) -> None:
    managed_ids = {
        entry.candidate_id
        for case in corpus.manifests
        for entry in case.manifest.entries
    }
    unmanaged_editions = {
        case.seed.edition.id
        for case in corpus.seeds
        if case.seed.approval.candidate_id not in managed_ids
    }
    assert unmanaged_editions == LEGACY_PRE_MANIFEST_EDITIONS


def test_both_seed_versions_load_without_migration(corpus: Corpus) -> None:
    versions = Counter(case.seed.schema_version for case in corpus.seeds)
    assert {"1.0", "1.1"} <= set(versions)
    for case in corpus.seeds:
        serialized = json.loads(serialize_seed(case.seed))
        assert serialized["schema_version"] == case.seed.schema_version
        if case.seed.schema_version == "1.0":
            assert "temporal_provenance" not in serialized
            assert case.seed.temporal_provenance == []
        else:
            assert "temporal_provenance" in serialized


def test_temporal_provenance_matches_raw_and_local_offsets(corpus: Corpus) -> None:
    for case in corpus.seeds:
        seed = case.seed
        raw = corpus.raws[seed.raw_fixture_path].candidate.raw_data
        assert seed.temporal_provenance == [
            provenance.for_seed() for provenance in raw.temporal_provenance
        ], case.path
        for provenance in seed.temporal_provenance:
            assert isinstance(provenance.field, TemporalField)
            assert isinstance(provenance.timezone_basis, TimezoneBasis)
            assert isinstance(provenance.precision, TemporalPrecision)
            window_name, endpoint_name = TIME_FIELD_ENDPOINT[provenance.field]
            window = getattr(seed.edition, window_name)
            assert window is not None, case.path
            value = getattr(window, endpoint_name)
            assert value is not None, case.path
            zone = ZoneInfo(provenance.timezone_name)
            local = value.astimezone(zone)
            assert local.utcoffset() == value.utcoffset(), case.path
            assert local.replace(tzinfo=None) == value.replace(tzinfo=None), case.path
            validate_timezone_offset(value, provenance)


def test_reviewed_real_timezone_examples(corpus: Corpus) -> None:
    by_edition = {case.seed.edition.id: case.seed for case in corpus.seeds}
    fwwb = by_edition["fwwb-2026"]
    graduate = by_edition["china-graduate-math-modeling-2026"]
    comap = by_edition["comap-mcm-2027"]

    assert [item.timezone_basis for item in fwwb.temporal_provenance] == [
        TimezoneBasis.JURISDICTION_DEFAULT
    ]
    assert {item.field for item in graduate.temporal_provenance} == set(TemporalField)
    assert all(
        item.timezone_name == "Asia/Shanghai"
        and item.timezone_basis is TimezoneBasis.JURISDICTION_DEFAULT
        for item in graduate.temporal_provenance
    )
    assert {item.field for item in comap.temporal_provenance} == {
        TemporalField.REGISTRATION_END,
        TemporalField.COMPETITION_START,
        TemporalField.COMPETITION_END,
    }
    assert all(
        item.timezone_name == "Etc/GMT+5"
        and item.timezone_basis is TimezoneBasis.SOURCE_EXPLICIT
        for item in comap.temporal_provenance
    )
    assert ZoneInfo("Etc/GMT+5").utcoffset(None) == -timedelta(hours=5)


def test_all_seed_sources_are_verified(corpus: Corpus) -> None:
    for case in corpus.seeds:
        seed = case.seed
        assert seed.competition_source.verification_status is VerificationStatus.VERIFIED
        assert seed.edition.source == seed.competition_source
        assert all(track.source == seed.competition_source for track in seed.tracks)
        assert seed.verification.source_url == seed.competition_source.source_url
        assert seed.verification.new_status is VerificationStatus.VERIFIED


def test_batch_audit_agrees_with_artifact_invariants(corpus: Corpus) -> None:
    report = audit_fixtures(RAW_DIR, SEED_DIR)
    summary = report.summary
    assert summary.total_raw_fixtures == len(corpus.raws)
    assert summary.existing_seeds == len(corpus.seeds)
    assert summary.raw_load_failed == 0
    assert summary.normalization_failed == 0
    assert summary.validation_errors == 0
    assert summary.validation_warnings == 0
    assert summary.seed_failed == 0
    assert summary.id_collisions == 0
    assert summary.raw_load_passed == len(corpus.raws)
    assert summary.normalization_passed == len(corpus.raws)
    assert summary.seed_passed == len(corpus.seeds)
    assert report.passed
