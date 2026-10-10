"""Read-only P3 Repository consumption of the real verified Seed corpus."""

from pathlib import Path

from competition_copilot.infrastructure.repositories import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.repositories import CompetitionRepository

SEED_DIR = Path(__file__).resolve().parents[3] / "data/seed"


def test_real_verified_seeds_satisfy_repository_queries() -> None:
    repository: CompetitionRepository = JsonSeedCompetitionRepository(SEED_DIR)
    competitions = repository.list_competitions()
    editions = repository.list_editions()

    assert competitions
    assert editions
    for competition in competitions:
        assert repository.get_competition(competition.id) == competition

    for edition in editions:
        assert repository.get_edition(edition.id) == edition
        assert edition in repository.list_editions_by_competition(edition.competition_id)
        tracks = repository.list_tracks(edition.id)
        assert tracks == repository.list_tracks(edition.id)
        for track in tracks:
            assert track.edition_id == edition.id
            assert repository.get_track(track.id) == track
