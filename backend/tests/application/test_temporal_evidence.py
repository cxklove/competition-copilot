"""Presentation candidates never enter deterministic planning or observation truth."""

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from competition_copilot.application.competition_detail import (
    CompetitionDetailQuery,
    CompetitionDetailReader,
)
from competition_copilot.application.competition_snapshots import (
    CompetitionSnapshotBuilder,
)
from competition_copilot.application.temporal_evidence import TemporalCandidateSnapshot
from competition_copilot.domain.digital_twin import CompetitionTarget
from competition_copilot.domain.event_engine import CompetitionEventEngine
from competition_copilot.domain.snapshot_diff_engine import SnapshotDiffEngine
from competition_copilot.infrastructure.eligibility_policy_json import (
    JsonEligibilityPolicyProvider,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.infrastructure.skill_requirement_json import (
    JsonSkillRequirementProvider,
)
from competition_copilot.infrastructure.temporal_evidence_json import (
    JsonTemporalEvidenceProvider,
)

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT = ROOT / "data/temporal_evidence/candidates.json"


def provider(path=ARTIFACT, root=ROOT):
    return JsonTemporalEvidenceProvider(path, root, JsonSeedCompetitionRepository(ROOT / "data/seed"))


def reader(temporal=None):
    repo = JsonSeedCompetitionRepository(ROOT / "data/seed")
    return CompetitionDetailReader(repo, JsonEligibilityPolicyProvider(ROOT / "data/eligibility"),
        JsonSkillRequirementProvider(ROOT / "data/skill_requirements"), repo, temporal)


def query(**updates):
    return CompetitionDetailQuery(**{"competition_id": "huawei-ict",
        "edition_id": "huawei-ict-2026", **updates})


def test_load_stable_identity_frozen_json_and_no_request_filesystem(monkeypatch):
    p = provider()
    first = p.read_candidates("huawei-ict", "huawei-ict-2026")[0]
    assert first.verification_status == "pending"
    assert first.source.verification_status == "verified"
    assert first == TemporalCandidateSnapshot.model_validate_json(first.model_dump_json())
    assert first.candidate_id == provider().read_candidates("huawei-ict", "huawei-ict-2026")[0].candidate_id
    with pytest.raises(ValidationError):
        first.raw_text = "changed"
    with pytest.raises(ValidationError):
        first.source.source_type = "manual"
    with pytest.raises(TypeError):
        first.model_copy(update={"raw_text": "changed"})
    monkeypatch.setattr(Path, "read_bytes", Mock(side_effect=AssertionError("runtime IO")))
    assert p.read_candidates("huawei-ict", "huawei-ict-2026") == (first,)


def test_artifact_raw_digests_match_fixture_bytes():
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    for candidate in artifact["candidates"]:
        raw_path = ROOT / candidate["raw_reference"]
        assert sha256(raw_path.read_bytes()).hexdigest() == candidate["raw_digest"]


@pytest.mark.parametrize("field,value", [
    ("raw_digest", "0" * 64), ("competition_id", "wrong"),
    ("field", "competition_end"), ("text_locator", "/raw_payload/notes"),
    ("raw_text", "not present in source"), ("track_id", "huawei-ict-2026-innovation"),
    ("raw_reference", "data/raw/../../secret.json"),
])
def test_binding_mismatch_fails_closed(tmp_path, field, value):
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    c = artifact["candidates"][0]
    c[field] = value
    c["candidate_id"] = ""
    # Even a recomputed content ID cannot replace Raw identity/quote checks.
    try:
        c = TemporalCandidateSnapshot.model_validate(c).model_dump(mode="json")
    except ValidationError:
        return
    artifact["candidates"][0] = c
    artifact["admissions"][0]["candidate_id"] = c["candidate_id"]
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(ValueError):
        provider(path)


def test_source_and_admission_mismatch(tmp_path):
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    for key in ("source", "admission"):
        changed = json.loads(json.dumps(artifact))
        if key == "source":
            c = changed["candidates"][0]
            c["source"]["observed_at"] = "2030-01-01T00:00:00Z"
            c["candidate_id"] = ""
            changed["candidates"][0] = TemporalCandidateSnapshot(**c).model_dump(mode="json")
            changed["admissions"][0]["candidate_id"] = changed["candidates"][0]["candidate_id"]
        else:
            changed["admissions"][0]["candidate_id"] = "wrong"
        path = tmp_path / "artifact.json"
        path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(ValueError):
            provider(path)


@pytest.mark.parametrize("status", ["rejected", "verified"])
def test_non_pending_not_published_or_promoted(tmp_path, status):
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    c = artifact["candidates"][0]
    c.update(candidate_id="", verification_status=status)
    artifact["candidates"][0] = TemporalCandidateSnapshot(**c).model_dump(mode="json")
    artifact["admissions"][0].update(candidate_id=artifact["candidates"][0]["candidate_id"],
        decision="reject" if status == "rejected" else "admit")
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    assert provider(path).read_candidates("huawei-ict", "huawei-ict-2026") == ()
    assert reader(provider(path)).read(query()).selected_edition.registration_window is None


def test_partial_availability_and_scope():
    r = reader(provider())
    unrequested = r.read(CompetitionDetailQuery(competition_id="huawei-ict"))
    assert not unrequested.temporal_candidates_availability.requested
    assert unrequested.temporal_candidates == ()
    for q in (query(), query(track_id="huawei-ict-2026-innovation")):
        value = r.read(q)
        assert value.temporal_candidates_availability.state == "known_value"
        assert value.temporal_candidates[0].track_id is None
        assert value.selected_edition.registration_window is None
    empty = r.read(CompetitionDetailQuery(competition_id="comap-mcm", edition_id="comap-mcm-2027"))
    assert empty.temporal_candidates == ()
    assert empty.temporal_candidates_availability.requested
    assert empty.temporal_candidates_availability.reason == "NO_ADMITTED_CANDIDATE"
    r.temporal_evidence = Mock()
    r.temporal_evidence.read_candidates.side_effect = RuntimeError("provider failed")
    with pytest.raises(RuntimeError):
        r.read(query())


@pytest.mark.parametrize("window", [
    {"start_at": "2030-01-01T00:00:00Z", "end_at": "2030-01-02T00:00:00Z"},
    {"start_at": "2030-01-01T00:00:00Z", "end_at": None},
])
def test_projection_preserves_verified_with_pending_candidate(window, monkeypatch):
    from competition_copilot.domain.temporal import TimeWindow

    r = reader(provider())
    edition = r.repository.get_edition("huawei-ict-2026")
    edition.registration_window = TimeWindow(**window)
    monkeypatch.setattr(r.repository, "get_edition", lambda _: edition)
    monkeypatch.setattr(r.repository, "list_editions_by_competition", lambda _: [edition])
    value = r.read(query())
    assert value.selected_edition.registration_window == edition.registration_window
    assert value.temporal_candidates


def test_candidates_do_not_feed_real_planner_snapshot_or_events():
    from tests.domain.test_baseline_plan_builder import build, need
    from tests.domain.test_baseline_plan_builder import target as plan_target

    r = reader(provider())
    target = CompetitionTarget(competition_id="huawei-ict", edition_id="huawei-ict-2026")
    clock = datetime(2030, 1, 1, tzinfo=timezone.utc)
    builder = CompetitionSnapshotBuilder(r.repository)
    before = builder.build(target, clock)
    planning_target = plan_target(competition_id="huawei-ict", edition_id="huawei-ict-2026")
    plan_before = build((need("uncertainty_resolution", skill_id=None),), planning_target=planning_target)
    value = r.read(query())  # Real Application read, with admitted evidence present.
    assert value.temporal_candidates
    c = value.temporal_candidates[0]
    changed = TemporalCandidateSnapshot(**{**c.model_dump(), "candidate_id": "", "raw_text": "Synthetic changed evidence"})
    r.temporal_evidence = Mock()
    r.temporal_evidence.read_candidates.return_value = (changed,)
    assert r.read(query()).temporal_candidates[0] != c
    after = builder.build(target, clock)
    assert before == after
    diff = SnapshotDiffEngine().compare(before, after)
    assert diff.changes == ()
    assert CompetitionEventEngine().interpret(diff, detected_at=clock) == ()
    plan_after = build((need("uncertainty_resolution", skill_id=None),), planning_target=planning_target)
    assert plan_before == plan_after
    assert all(m.due_at is None for m in plan_after.milestones)
    with pytest.raises((ValidationError, TypeError)):
        build(horizon=c)
    # Downstream authorities have no dependency on the presentation contract.
    for filename in ("baseline_plan_builder.py", "digital_twin.py", "event_engine.py",
                     "event_impact_analyzer.py", "replanning_decision_service.py",
                     "plan_revision_service.py"):
        source = (ROOT / "backend/competition_copilot/domain" / filename).read_text()
        assert "temporal_evidence" not in source and "TemporalCandidate" not in source
