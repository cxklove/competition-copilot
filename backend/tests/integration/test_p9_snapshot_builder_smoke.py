"""Read-only P9.2 smoke tests using the real verified Seed Repository."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from competition_copilot.application.competition_snapshots import (
    CompetitionSnapshotBuilder,
)
from competition_copilot.domain.digital_twin import CompetitionTarget, ObservationState
from competition_copilot.infrastructure.repositories import (
    JsonSeedCompetitionRepository,
)
from competition_copilot.repositories import RepositoryEntityNotFoundError

SEED_DIR = Path(__file__).resolve().parents[3] / "data" / "seed"
OBSERVED_AT = datetime(2030, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def repository():
    return JsonSeedCompetitionRepository(SEED_DIR)


def test_real_comap_edition_builds_repository_backed_snapshot(repository):
    target = CompetitionTarget(competition_id="comap-mcm", edition_id="comap-mcm-2027")
    competition = repository.get_competition(target.competition_id)
    edition = repository.get_edition(target.edition_id)
    assert competition.id == edition.competition_id == target.competition_id
    assert edition.source is not None

    builder = CompetitionSnapshotBuilder(repository)
    first = builder.build(target, OBSERVED_AT)
    second = builder.build(target, OBSERVED_AT)
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert first.snapshot_id.startswith("competition-snapshot-v1:")
    assert first.target.track_id is None
    assert first.observed_at == OBSERVED_AT
    assert first.dynamic_state.registration_window.state == ObservationState.KNOWN_VALUE
    assert first.dynamic_state.competition_window.state == ObservationState.KNOWN_VALUE
    assert first.dynamic_state.registration_window.value == edition.registration_window
    assert first.dynamic_state.competition_window.value == edition.competition_window
    assert first.dynamic_state.registration_window.sources == (edition.source,)
    assert (
        first.dynamic_state.registration_window.sources[0].observed_at
        == edition.source.observed_at
    )
    assert first.dynamic_state.track_membership.state == ObservationState.KNOWN_VALUE
    assert first.dynamic_state.track_membership.value == ()
    assert first.dynamic_state.track_membership.sources == (edition.source,)
    assert first.model_dump(mode="json")["target"]["track_id"] is None


def test_real_known_zero_track_edition_is_not_unknown(repository):
    target = CompetitionTarget(
        competition_id="c4-big-data-challenge",
        edition_id="c4-big-data-challenge-2026",
    )
    edition = repository.get_edition(target.edition_id)
    assert edition.competition_id == target.competition_id
    assert repository.list_tracks(target.edition_id) == []
    snapshot = CompetitionSnapshotBuilder(repository).build(target, OBSERVED_AT)
    membership = snapshot.dynamic_state.track_membership
    assert membership.state == ObservationState.KNOWN_VALUE
    assert membership.value == ()
    assert membership.sources == (edition.source,)


def test_real_repository_missing_target_raises_instead_of_unknown_snapshot(repository):
    builder = CompetitionSnapshotBuilder(repository)
    with pytest.raises(RepositoryEntityNotFoundError):
        builder.build(
            CompetitionTarget(competition_id="not-real", edition_id="comap-mcm-2027"),
            OBSERVED_AT,
        )
