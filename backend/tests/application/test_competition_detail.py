"""Exact read projections using real repositories/providers; no decision services."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from competition_copilot.application.competition_detail import (
    CompetitionDetailProjection,
    CompetitionDetailQuery,
    CompetitionDetailReader,
)
from competition_copilot.infrastructure.eligibility_policy_json import (
    JsonEligibilityPolicyProvider,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.infrastructure.skill_requirement_json import (
    JsonSkillRequirementProvider,
)
from competition_copilot.repositories.competition import RepositoryEntityNotFoundError

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def reader():
    repository = JsonSeedCompetitionRepository(ROOT / "data/seed")
    return CompetitionDetailReader(repository, JsonEligibilityPolicyProvider(ROOT / "data/eligibility"),
        JsonSkillRequirementProvider(ROOT / "data/skill_requirements"), repository)


def query(**extra):
    return CompetitionDetailQuery(competition_id="comap-mcm", **extra)


def test_competition_only_does_not_select_or_read_target_providers(reader):
    reader.policies = Mock()
    reader.requirements = Mock()
    value = reader.read(query())
    assert value.editions
    assert value.selected_edition is None and value.selected_track is None
    assert value.tracks == ()
    assert not value.availability.tracks.requested
    assert value.availability.tracks.reason == "NOT_REQUESTED"
    reader.policies.get_policy.assert_not_called()
    reader.requirements.list_artifacts.assert_not_called()


def test_edition_exact_artifact_and_null_semantics(reader):
    q = query(edition_id="comap-mcm-2027")
    value = reader.read(q)
    assert value.selected_edition.id == q.edition_id
    assert value.selected_track is None
    artifact = value.skill_requirements
    assert artifact in reader.requirements.list_artifacts()
    assert artifact.requirement_version == "1.0"
    assert artifact.requirement_set.coverage == "partial"
    assert artifact.requirement_set.requirements[0].required_level is None
    assert artifact.skills[0].name
    assert value.provenance
    assert value.availability.event_history.reason == "EVENT_HISTORY_PERSISTENCE_GAP"


def test_track_query_does_not_inherit_edition_artifact(reader):
    q = CompetitionDetailQuery(competition_id="huawei-ict", edition_id="huawei-ict-2026",
        track_id="huawei-ict-2026-innovation")
    value = reader.read(q)
    assert value.selected_track.id == q.track_id
    assert all(t.edition_id == q.edition_id for t in value.tracks)
    assert value.skill_requirements is None


@pytest.mark.parametrize("extra,error", [
    ({"track_id": "track"}, ValidationError),
    ({"edition_id": "missing"}, RepositoryEntityNotFoundError),
    ({"edition_id": "huawei-ict-2026"}, ValueError),
    ({"edition_id": "comap-mcm-2027", "track_id": "huawei-ict-2026-innovation"}, ValueError),
])
def test_bad_target_fails_closed(reader, extra, error):
    with pytest.raises(error):
        reader.read(query(**extra))


def test_none_policy_is_partial_read_but_provider_failure_is_not_unknown(reader):
    reader.policies = Mock()
    reader.policies.get_policy.return_value = None
    value = reader.read(query(edition_id="comap-mcm-2027"))
    assert value.eligibility_policy is None and value.skill_requirements is not None
    assert value.availability.eligibility_policy.reason == "NO_EXACT_POLICY"
    reader.policies.get_policy.side_effect = RuntimeError("unavailable")
    with pytest.raises(RuntimeError):
        reader.read(query(edition_id="comap-mcm-2027"))


def test_corrupt_policy_identity_is_rejected(reader):
    reader.policies = Mock()
    reader.policies.get_policy.return_value = JsonEligibilityPolicyProvider(
        ROOT / "data/eligibility").get_policy("gcxl-engineering-practice-innovation",
        "gcxl-engineering-practice-innovation-2027")
    assert reader.policies.get_policy.return_value is not None
    with pytest.raises(ValidationError, match="Policy target mismatch"):
        reader.read(query(edition_id="comap-mcm-2027"))


def test_deep_immutable_detached_json_stable(reader):
    q = query(edition_id="comap-mcm-2027")
    value = reader.read(q)
    for obj, field, replacement in (
        (value, "tracks", ()), (value.competition, "name", "tampered"),
        (value.selected_edition, "name", "tampered"),
        (value.skill_requirements.skills[0], "name", "tampered"),
        (value.provenance[0].source, "source_type", "manual"),
    ):
        with pytest.raises(ValidationError):
            setattr(obj, field, replacement)
    assert CompetitionDetailProjection.model_validate_json(value.model_dump_json()) == value
    assert reader.read(q).model_dump_json() == value.model_dump_json()
    with pytest.raises(TypeError):
        value.model_copy(update={"selected_edition": None})


def test_all_real_entities_preserve_windows_order_and_reviewed_provenance(reader):
    for edition in reader.repository.list_editions():
        value = reader.read(CompetitionDetailQuery(competition_id=edition.competition_id,
            edition_id=edition.id))
        assert value.selected_edition.registration_window == edition.registration_window
        assert value.selected_edition.competition_window == edition.competition_window
        assert [t.id for t in value.tracks] == [t.id for t in reader.repository.list_tracks(edition.id)]
        assert value.provenance == reader.provenance.read_provenance(edition.competition_id, edition.id)


def test_partial_window_preserved_without_io_or_business_calls(reader, monkeypatch):
    from competition_copilot.domain.temporal import TimeWindow

    edition = reader.repository.get_edition("comap-mcm-2027")
    edition.registration_window = None
    edition.competition_window = TimeWindow(start_at="2027-02-01T00:00:00+08:00", end_at=None)
    monkeypatch.setattr(reader.repository, "get_edition", lambda _: edition)
    monkeypatch.setattr(reader.repository, "list_editions_by_competition", lambda _: [edition])
    monkeypatch.setattr(Path, "read_bytes", Mock(side_effect=AssertionError("no IO")))
    monkeypatch.setattr(Path, "read_text", Mock(side_effect=AssertionError("no IO")))
    value = reader.read(query(edition_id=edition.id))
    assert value.selected_edition.registration_window is None
    assert value.selected_edition.competition_window.end_at is None
    assert value.selected_edition.competition_window.start_at.utcoffset().total_seconds() == 28800


def test_policy_snapshot_keeps_constraints_immutable(reader):
    value = reader.read(CompetitionDetailQuery(competition_id="gcxl-engineering-practice-innovation",
        edition_id="gcxl-engineering-practice-innovation-2027"))
    assert isinstance(value.eligibility_policy.constraints, tuple)
    assert isinstance(value.eligibility_policy.constraints[0].allowed_levels, tuple)
    assert value.eligibility_policy.source.verification_status == "verified"


def test_seed_provenance_is_lossless(reader):
    from competition_copilot.ingestion.seed import deserialize_seed

    for path in sorted((ROOT / "data/seed").glob("*.json")):
        seed = deserialize_seed(path.read_bytes())
        value = reader.read(CompetitionDetailQuery(competition_id=seed.competition.id,
            edition_id=seed.edition.id))
        competition = next(p for p in value.provenance if p.section == "competition")
        temporal = next(p for p in value.provenance if p.section == "time_windows")
        assert competition.source == seed.competition_source
        assert [p.model_dump(mode="json") for p in temporal.temporal] == [
            p.model_dump(mode="json") for p in seed.temporal_provenance]


def test_exact_track_never_inherits_edition_requirement(reader, monkeypatch):
    from competition_copilot.domain.competition import CompetitionTrack

    track = CompetitionTrack(id="test-track", edition_id="comap-mcm-2027", name="Synthetic track")
    monkeypatch.setattr(reader.repository, "get_track", lambda _: track)
    monkeypatch.setattr(reader.repository, "list_tracks", lambda _: [track])
    value = reader.read(query(edition_id=track.edition_id, track_id=track.id))
    assert value.skill_requirements is None
    assert value.availability.skill_requirements.reason == "NO_EXACT_ARTIFACT"


def test_duplicate_artifact_and_wrong_provenance_fail_closed(reader):
    artifact = next(a for a in reader.requirements.list_artifacts()
                    if a.requirement_set.target.competition_id == "comap-mcm")
    reader.requirements = Mock()
    reader.requirements.list_artifacts.return_value = (artifact, artifact)
    with pytest.raises(ValueError, match="Duplicate"):
        reader.read(query(edition_id="comap-mcm-2027"))
    reader.requirements.list_artifacts.return_value = ()
    reader.provenance = Mock()
    reader.provenance.read_provenance.return_value = (
        reader.repository.read_provenance("huawei-ict")[0],)
    with pytest.raises(ValidationError, match="Provenance target mismatch"):
        reader.read(query(edition_id="comap-mcm-2027"))


def test_reader_does_not_execute_business_services(reader, monkeypatch):
    from competition_copilot.application.eligibility import (
        CompetitionEligibilityEvaluator,
    )
    from competition_copilot.domain.skill_gap_engine import SkillGapEngine

    forbidden = Mock(side_effect=AssertionError("read must not execute a decision"))
    monkeypatch.setattr(CompetitionEligibilityEvaluator, "evaluate", forbidden)
    monkeypatch.setattr(SkillGapEngine, "evaluate", forbidden)
    reader.read(query(edition_id="comap-mcm-2027"))
    forbidden.assert_not_called()


@pytest.mark.parametrize("payload,code", [
    ({"competition_id": "comap-mcm", "track_id": "track"}, "INVALID_INPUT"),
    ({"competition_id": "missing"}, "NOT_FOUND"),
    ({"competition_id": "comap-mcm", "edition_id": "huawei-ict-2026"}, "INTERNAL_ERROR"),
])
def test_tool_reuses_existing_errors_without_partial_corrupt_data(reader, payload, code):
    from competition_copilot.tools.competition_detail import GetCompetitionDetailsTool

    output = GetCompetitionDetailsTool(reader).execute(payload)
    assert not output.success and output.data is None
    assert output.error.code == code
