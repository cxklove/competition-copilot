"""P9.2 mapping tests with TEST-ONLY synthetic Repository entities."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.application.competition_snapshots import (
    CompetitionSnapshotBuilder,
    SnapshotProvenanceError,
    SnapshotTargetMismatchError,
    SnapshotTargetUnsupportedError,
)
from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.digital_twin import CompetitionTarget, ObservationState
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.temporal import TimeWindow
from competition_copilot.repositories.competition import RepositoryEntityNotFoundError

SOURCE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)
CAPTURE_TIME = datetime(2026, 1, 2, tzinfo=timezone.utc)
WINDOW_START = datetime(2026, 3, 1, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 4, 1, tzinfo=timezone.utc)
TARGET = CompetitionTarget(competition_id="competition-a", edition_id="edition-a")


def source(url="https://example.org/test-only-source", status="verified"):
    return SourceMetadata(
        source_url=url,
        source_type="official",
        observed_at=SOURCE_TIME,
        verification_status=status,
    )


class FakeRepository:
    """Only the three CompetitionRepository reads used by this builder."""

    def __init__(
        self,
        *,
        registration=None,
        competition_window=None,
        tracks=None,
        edition_source=None,
    ):
        self.competition = Competition(id="competition-a", name="Display A")
        self.edition = CompetitionEdition(
            id="edition-a",
            competition_id="competition-a",
            year=2026,
            name="Display Edition",
            registration_window=registration,
            competition_window=competition_window,
            source=source() if edition_source is None else edition_source,
        )
        self.tracks = [] if tracks is None else tracks
        self.calls = []

    def get_competition(self, competition_id):
        self.calls.append(("get_competition", competition_id))
        if competition_id != self.competition.id:
            raise RepositoryEntityNotFoundError("competition", competition_id)
        return self.competition

    def get_edition(self, edition_id):
        self.calls.append(("get_edition", edition_id))
        if edition_id != self.edition.id:
            raise RepositoryEntityNotFoundError("edition", edition_id)
        return self.edition

    def list_tracks(self, edition_id):
        self.calls.append(("list_tracks", edition_id))
        if edition_id != self.edition.id:
            raise RepositoryEntityNotFoundError("edition", edition_id)
        return self.tracks


def track(track_id, *, track_source=None):
    return CompetitionTrack(
        id=track_id,
        edition_id="edition-a",
        name=f"Display {track_id}",
        source=source(f"https://example.org/{track_id}")
        if track_source is None
        else track_source,
    )


def test_none_windows_are_unknown_and_empty_tracks_are_known():
    repository = FakeRepository()
    snapshot = CompetitionSnapshotBuilder(repository).build(TARGET, CAPTURE_TIME)
    assert snapshot.target == TARGET
    assert snapshot.observed_at == CAPTURE_TIME
    assert snapshot.dynamic_state.registration_window.state == ObservationState.UNKNOWN
    assert snapshot.dynamic_state.competition_window.state == ObservationState.UNKNOWN
    assert snapshot.dynamic_state.registration_window.value is None
    assert snapshot.dynamic_state.registration_window.sources == ()
    membership = snapshot.dynamic_state.track_membership
    assert membership.state == ObservationState.KNOWN_VALUE
    assert membership.value == ()
    assert membership.sources == (source(),)
    assert repository.calls == [
        ("get_competition", "competition-a"),
        ("get_edition", "edition-a"),
        ("list_tracks", "edition-a"),
    ]
    assert "known_absent" not in snapshot.model_dump_json()


def test_full_and_partial_windows_keep_source_and_capture_time_distinct():
    full = TimeWindow(start_at=WINDOW_START, end_at=WINDOW_END)
    partial = TimeWindow(end_at=WINDOW_END)
    repository = FakeRepository(registration=full, competition_window=partial)
    snapshot = CompetitionSnapshotBuilder(repository).build(TARGET, CAPTURE_TIME)
    registration = snapshot.dynamic_state.registration_window
    competition_window = snapshot.dynamic_state.competition_window
    assert (
        registration.state == competition_window.state == ObservationState.KNOWN_VALUE
    )
    assert registration.value == full
    assert competition_window.value == partial
    assert competition_window.value.start_at is None
    assert registration.sources == competition_window.sources == (source(),)
    assert registration.sources[0].observed_at == SOURCE_TIME
    assert snapshot.observed_at == CAPTURE_TIME != SOURCE_TIME
    assert (
        snapshot.model_dump(mode="json")["dynamic_state"]["competition_window"][
            "value"
        ]["start_at"]
        is None
    )


def test_known_tracks_use_sorted_ids_and_real_entity_sources():
    repository = FakeRepository(tracks=[track("track-b"), track("track-a")])
    snapshot = CompetitionSnapshotBuilder(repository).build(TARGET, CAPTURE_TIME)
    membership = snapshot.dynamic_state.track_membership
    assert membership.value == ("track-a", "track-b")
    assert membership.state == ObservationState.KNOWN_VALUE
    assert {str(item.source_url) for item in membership.sources} == {
        "https://example.org/test-only-source",
        "https://example.org/track-a",
        "https://example.org/track-b",
    }
    assert len(membership.sources) == 3
    assert "Display track-a" not in snapshot.model_dump_json()


def test_same_input_idempotent_and_state_or_time_change_changes_id():
    repository = FakeRepository(
        registration=TimeWindow(end_at=WINDOW_END),
        tracks=[track("track-b"), track("track-a")],
    )
    builder = CompetitionSnapshotBuilder(repository)
    first = builder.build(TARGET, CAPTURE_TIME)
    second = builder.build(TARGET, CAPTURE_TIME)
    assert first == second
    assert first.snapshot_id == second.snapshot_id
    assert first.model_dump_json() == second.model_dump_json()
    later = builder.build(TARGET, CAPTURE_TIME + timedelta(days=1))
    assert later.dynamic_state == first.dynamic_state
    assert later.snapshot_id != first.snapshot_id
    repository.edition.registration_window = TimeWindow(
        end_at=WINDOW_END + timedelta(days=1)
    )
    changed = builder.build(TARGET, CAPTURE_TIME)
    assert changed.snapshot_id != first.snapshot_id
    assert first.dynamic_state.registration_window.value.end_at == WINDOW_END


def test_display_text_and_repository_track_order_do_not_change_identity():
    repository = FakeRepository(tracks=[track("track-b"), track("track-a")])
    builder = CompetitionSnapshotBuilder(repository)
    first = builder.build(TARGET, CAPTURE_TIME)
    repository.competition.name = "New display text"
    repository.edition.name = "New edition display text"
    repository.tracks[0].name = "New track display text"
    repository.tracks.reverse()
    second = builder.build(TARGET, CAPTURE_TIME)
    assert first.snapshot_id == second.snapshot_id
    assert first.model_dump_json() == second.model_dump_json()


def test_builder_does_not_mutate_repository_entities_or_sources():
    repository = FakeRepository(
        registration=TimeWindow(end_at=WINDOW_END), tracks=[track("track-a")]
    )
    before = tuple(
        item.model_dump_json()
        for item in (repository.competition, repository.edition, *repository.tracks)
    )
    snapshot = CompetitionSnapshotBuilder(repository).build(TARGET, CAPTURE_TIME)
    after = tuple(
        item.model_dump_json()
        for item in (repository.competition, repository.edition, *repository.tracks)
    )
    assert before == after
    assert snapshot.dynamic_state.track_membership.sources[0].observed_at == SOURCE_TIME
    with pytest.raises(ValidationError):
        snapshot.dynamic_state.track_membership.value = ("other",)
    with pytest.raises(ValidationError):
        snapshot.observed_at = SOURCE_TIME
    assert (
        snapshot.model_dump_json()
        == CompetitionSnapshotBuilder(repository)
        .build(TARGET, CAPTURE_TIME)
        .model_dump_json()
    )


@pytest.mark.parametrize(
    "bad_target,entity_type",
    [
        (
            CompetitionTarget(competition_id="missing", edition_id="edition-a"),
            "competition",
        ),
        (
            CompetitionTarget(competition_id="competition-a", edition_id="missing"),
            "edition",
        ),
    ],
)
def test_missing_target_raises_repository_not_found(bad_target, entity_type):
    with pytest.raises(RepositoryEntityNotFoundError) as raised:
        CompetitionSnapshotBuilder(FakeRepository()).build(bad_target, CAPTURE_TIME)
    assert raised.value.entity_type == entity_type


def test_mismatched_edition_and_track_fail_fast():
    repository = FakeRepository()
    repository.edition.competition_id = "competition-b"
    with pytest.raises(SnapshotTargetMismatchError):
        CompetitionSnapshotBuilder(repository).build(TARGET, CAPTURE_TIME)
    repository.edition.competition_id = "competition-a"
    repository.tracks = [track("track-a")]
    repository.tracks[0].edition_id = "other-edition"
    with pytest.raises(SnapshotTargetMismatchError):
        CompetitionSnapshotBuilder(repository).build(TARGET, CAPTURE_TIME)


def test_track_target_is_explicitly_deferred_without_fake_dynamic_facts():
    repository = FakeRepository()
    with pytest.raises(SnapshotTargetUnsupportedError):
        CompetitionSnapshotBuilder(repository).build(
            CompetitionTarget(
                competition_id="competition-a",
                edition_id="edition-a",
                track_id="track-a",
            ),
            CAPTURE_TIME,
        )
    assert repository.calls == []


def test_naive_observation_time_rejected():
    repository = FakeRepository()
    with pytest.raises(ValidationError):
        CompetitionSnapshotBuilder(repository).build(
            TARGET, CAPTURE_TIME.replace(tzinfo=None)
        )
    assert repository.calls == []


@pytest.mark.parametrize(
    "source_problem",
    ["missing_edition", "pending_edition", "missing_track", "pending_track"],
)
def test_known_fact_without_verified_source_fails_instead_of_fabricating(
    source_problem,
):
    repository = FakeRepository(
        registration=TimeWindow(end_at=WINDOW_END),
        competition_window=TimeWindow(end_at=WINDOW_END),
        tracks=[track("track-a")],
    )
    if source_problem == "missing_edition":
        repository.edition.source = None
    elif source_problem == "pending_edition":
        repository.edition.source = source(status="pending")
    elif source_problem == "missing_track":
        repository.tracks[0].source = None
    else:
        repository.tracks[0].source = source(status="pending")
    with pytest.raises(SnapshotProvenanceError):
        CompetitionSnapshotBuilder(repository).build(TARGET, CAPTURE_TIME)


def test_duplicate_track_ids_fail_contract_validation():
    repository = FakeRepository(tracks=[track("track-a"), track("track-a")])
    with pytest.raises(ValidationError):
        CompetitionSnapshotBuilder(repository).build(TARGET, CAPTURE_TIME)


def test_source_time_after_capture_rejected_by_snapshot_contract():
    repository = FakeRepository()
    with pytest.raises(ValidationError):
        CompetitionSnapshotBuilder(repository).build(
            TARGET, SOURCE_TIME - timedelta(days=1)
        )
