"""P7.3 data smoke tests only; no StudentProfile or SkillGapEngine execution."""

from pathlib import Path

import pytest

from competition_copilot.domain.skill_gap import (
    SkillFactRole,
    skill_fact_field,
    skill_fact_value,
)
from competition_copilot.infrastructure.repositories.json_seed import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.infrastructure.skill_requirement_json import (
    JsonSkillRequirementProvider,
)

ROOT = Path(__file__).resolve().parents[3]
REQUIREMENT_DIR = ROOT / "data" / "skill_requirements"
SEED_DIR = ROOT / "data" / "seed"


def test_reviewed_data_provider_load_is_read_only_and_deterministic():
    paths = tuple(sorted(REQUIREMENT_DIR.glob("*.json")))
    before = {p: p.read_bytes() for p in paths}
    first = JsonSkillRequirementProvider(REQUIREMENT_DIR)
    second = JsonSkillRequirementProvider(REQUIREMENT_DIR)
    assert len(first.list_artifacts()) == len(paths)
    assert tuple(a.model_dump_json() for a in first.list_artifacts()) == tuple(
        a.model_dump_json() for a in second.list_artifacts()
    )
    assert {p: p.read_bytes() for p in paths} == before


def test_real_artifact_target_identity_provenance_and_coverage():
    provider = JsonSkillRequirementProvider(REQUIREMENT_DIR)
    artifacts = provider.list_artifacts()
    if not artifacts:
        pytest.skip("P7.3 SOURCE GAP: no reviewed real skill/proficiency artifacts yet")
    repository = JsonSeedCompetitionRepository(SEED_DIR)
    for artifact in artifacts:
        requirement_set = artifact.requirement_set
        target = requirement_set.target
        assert repository.get_competition(target.competition_id).id == target.competition_id
        edition = repository.get_edition(target.edition_id)
        assert edition.competition_id == target.competition_id
        if target.track_id is not None:
            assert repository.get_track(target.track_id).edition_id == edition.id
        assert requirement_set.coverage_note
        assert artifact.review_note and artifact.requirement_version
        skills = {s.id for s in artifact.skills}
        for requirement in requirement_set.requirements:
            assert requirement.skill_id in skills
            for evidence in requirement.evidence:
                assert evidence.field == skill_fact_field(SkillFactRole.REQUIREMENT, requirement.skill_id)
                assert evidence.value == skill_fact_value(requirement.required_level)
                assert evidence.source.source_type.value == "official"
                assert evidence.source.verification_status.value == "verified"


def test_real_repository_targets_without_exact_artifact_return_missing_data():
    repository = JsonSeedCompetitionRepository(SEED_DIR)
    provider = JsonSkillRequirementProvider(REQUIREMENT_DIR)
    targets = []
    for edition in repository.list_editions():
        targets.append((edition.competition_id, edition.id, None))
        targets.extend(
            (edition.competition_id, edition.id, track.id)
            for track in repository.list_tracks(edition.id)
        )
    missing = [t for t in targets if provider.get_requirements(*t) is None]
    if not missing:
        pytest.skip("Current repository snapshot has no target without an exact artifact")
    competition_id, edition_id, track_id = missing[0]
    assert repository.get_edition(edition_id).competition_id == competition_id
    if track_id is not None:
        assert repository.get_track(track_id).edition_id == edition_id
    assert provider.get_requirements(competition_id, edition_id, track_id) is None
