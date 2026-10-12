"""Real Repository baselines plus TEST-ONLY CONTROLLED observations.

Controlled fixtures are not official historical updates, live source refreshes,
or Monitor output. Manual fixture provenance verifies test inputs only.
"""

import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from competition_copilot.application.competition_snapshots import (
    CompetitionSnapshotBuilder,
)
from competition_copilot.domain.digital_twin import (
    CompetitionDynamicState,
    CompetitionSnapshot,
    CompetitionTarget,
    FactChangeKind,
    ObservationState,
    ObservedTimeWindow,
    ObservedTrackMembership,
)
from competition_copilot.domain.snapshot_diff_engine import SnapshotDiffEngine
from competition_copilot.domain.source_metadata import SourceMetadata, SourceType
from competition_copilot.domain.temporal import TimeWindow
from competition_copilot.infrastructure.repositories import (
    JsonSeedCompetitionRepository,
)

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
SEED_DIR = DATA_DIR / "seed"
T1 = datetime(2030, 1, 1, tzinfo=timezone.utc)
T2 = datetime(2030, 1, 2, tzinfo=timezone.utc)
COMAP = CompetitionTarget(competition_id="comap-mcm", edition_id="comap-mcm-2027")
HUAWEI = CompetitionTarget(competition_id="huawei-ict", edition_id="huawei-ict-2026")


@pytest.fixture(autouse=True)
def offline_read_only_seed_boundary(monkeypatch):
    reads = []
    original_open = Path.open

    def guarded_open(path, mode="r", *args, **kwargs):
        resolved = path.resolve()
        if resolved.is_relative_to(DATA_DIR):
            assert resolved.is_relative_to(SEED_DIR), (
                "P9 runtime may only read Seed data"
            )
            assert not any(flag in mode for flag in "wax+"), "Real data is read-only"
            reads.append(resolved)
        return original_open(path, mode, *args, **kwargs)

    def forbidden_network(*args, **kwargs):
        pytest.fail("P9.4 integration must remain offline")

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(socket.socket, "connect", forbidden_network)
    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    return reads


@pytest.fixture
def repository():
    return JsonSeedCompetitionRepository(SEED_DIR)


def fixture_source():
    """TEST-ONLY verification of a controlled fixture, never official provenance."""
    return SourceMetadata(
        source_url="https://example.invalid/p9.4/test-only-controlled-observation",
        source_type=SourceType.MANUAL,
        observed_at=T2,
        verification_status="verified",
    )


def controlled(baseline, case, **facts):
    """Public validated constructor; stable test-case ID, not a second production ID algorithm."""
    state = CompetitionDynamicState(
        registration_window=facts.get(
            "registration_window", baseline.dynamic_state.registration_window
        ),
        competition_window=facts.get(
            "competition_window", baseline.dynamic_state.competition_window
        ),
        track_membership=facts.get(
            "track_membership", baseline.dynamic_state.track_membership
        ),
    )
    return CompetitionSnapshot(
        snapshot_id=f"test-only-controlled:{case}:{baseline.snapshot_id}",
        target=baseline.target,
        observed_at=T2,
        dynamic_state=state,
    )


def assert_serializable(model):
    assert type(model).model_validate_json(model.model_dump_json()) == model
    assert type(model).model_validate(model.model_dump(mode="json")) == model


def repository_state(repository, target):
    return tuple(
        item.model_dump_json()
        for item in (
            repository.get_competition(target.competition_id),
            repository.get_edition(target.edition_id),
            *repository.list_tracks(target.edition_id),
        )
    )


def test_case_a_real_same_state_observations(
    repository, offline_read_only_seed_boundary
):
    original = repository_state(repository, COMAP)
    builder = CompetitionSnapshotBuilder(repository)
    first, second = builder.build(COMAP, T1), builder.build(COMAP, T2)
    edition = repository.get_edition(COMAP.edition_id)
    assert first.target == second.target == COMAP
    assert first.observed_at == T1 < second.observed_at == T2
    assert first.snapshot_id != second.snapshot_id
    assert first.dynamic_state == second.dynamic_state
    assert first.dynamic_state.registration_window.value == edition.registration_window
    assert first.dynamic_state.competition_window.value == edition.competition_window
    for fact in (
        first.dynamic_state.registration_window,
        first.dynamic_state.competition_window,
    ):
        assert fact.state == ObservationState.KNOWN_VALUE
        assert fact.sources == (edition.source,)
        assert fact.sources[0].observed_at == edition.source.observed_at != T1
        assert fact.sources[0].source_type == SourceType.OFFICIAL
    assert repository.list_tracks(COMAP.edition_id) == []
    assert first.dynamic_state.track_membership.state == ObservationState.KNOWN_VALUE
    assert first.dynamic_state.track_membership.value == ()
    assert first.dynamic_state.track_membership.sources == (edition.source,)

    engine = SnapshotDiffEngine()
    before_json, after_json = first.model_dump_json(), second.model_dump_json()
    result = engine.compare(first, second)
    assert result.changes == ()
    assert result.before.target == result.after.target == COMAP
    assert result.before.snapshot_id == first.snapshot_id
    assert result.after.snapshot_id == second.snapshot_id
    assert result.before.observed_at == T1 and result.after.observed_at == T2
    again_a, again_b = builder.build(COMAP, T1), builder.build(COMAP, T2)
    assert again_a.model_dump_json() == before_json
    assert again_b.model_dump_json() == after_json
    assert (
        engine.compare(again_a, again_b).model_dump_json() == result.model_dump_json()
    )
    assert (
        first.model_dump_json() == before_json
        and second.model_dump_json() == after_json
    )
    assert repository_state(repository, COMAP) == original
    for model in (first, second, result):
        assert_serializable(model)
    assert offline_read_only_seed_boundary
    assert all(
        path.is_relative_to(SEED_DIR) for path in offline_read_only_seed_boundary
    )


def test_case_b_same_exact_real_snapshot(repository):
    baseline = CompetitionSnapshotBuilder(repository).build(COMAP, T1)
    result = SnapshotDiffEngine().compare(baseline, baseline)
    assert result.before == result.after
    assert result.changes == ()
    assert_serializable(result)
    with pytest.raises(ValidationError):
        baseline.dynamic_state.track_membership.value = ("other",)
    with pytest.raises(ValidationError):
        result.before.snapshot_id = "other"
    with pytest.raises(AttributeError):
        result.changes.append(None)


def test_case_c_test_only_window_observation_lost(repository):
    baseline = CompetitionSnapshotBuilder(repository).build(COMAP, T1)
    assert (
        baseline.dynamic_state.registration_window.state == ObservationState.KNOWN_VALUE
    )
    later = controlled(
        baseline,
        "window-observation-lost",
        registration_window=ObservedTimeWindow(state="unknown"),
    )
    before_json, after_json = baseline.model_dump_json(), later.model_dump_json()
    result = SnapshotDiffEngine().compare(baseline, later)
    assert later.target == baseline.target and later.observed_at > baseline.observed_at
    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.field == "registration_window"
    assert change.kind == FactChangeKind.OBSERVATION_STATE_CHANGED
    assert change.kind != FactChangeKind.PRESENCE_CHANGED
    assert change.before.sources == baseline.dynamic_state.registration_window.sources
    assert change.after.state == ObservationState.UNKNOWN and change.after.sources == ()
    repeated = controlled(
        baseline,
        "window-observation-lost",
        registration_window=ObservedTimeWindow(state="unknown"),
    )
    assert repeated.model_dump_json() == after_json
    assert (
        SnapshotDiffEngine().compare(baseline, repeated).model_dump_json()
        == result.model_dump_json()
    )
    assert (
        baseline.model_dump_json() == before_json
        and later.model_dump_json() == after_json
    )
    with pytest.raises(ValidationError):
        change.kind = FactChangeKind.VALUE_CHANGED
    assert_serializable(later)
    assert_serializable(result)


def test_case_d_test_only_controlled_window_value(repository):
    baseline = CompetitionSnapshotBuilder(repository).build(COMAP, T1)
    real_window = baseline.dynamic_state.registration_window.value
    assert real_window is not None and real_window.end_at is not None
    changed_window = ObservedTimeWindow(
        state="known_value",
        value=TimeWindow(
            start_at=real_window.start_at, end_at=real_window.end_at + timedelta(days=1)
        ),
        sources=(fixture_source(),),
    )
    later = controlled(
        baseline, "manual-window-value", registration_window=changed_window
    )
    result = SnapshotDiffEngine().compare(baseline, later)
    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.field == "registration_window.end_at"
    assert change.kind == FactChangeKind.VALUE_CHANGED
    assert change.before.value == real_window.end_at
    assert change.after.value == real_window.end_at + timedelta(days=1)
    assert change.before.sources == baseline.dynamic_state.registration_window.sources
    assert change.after.sources == (fixture_source(),)
    assert change.after.sources[0].source_type == SourceType.MANUAL
    assert change.after.sources != change.before.sources
    assert (
        SnapshotDiffEngine().compare(baseline, later).model_dump_json()
        == result.model_dump_json()
    )
    assert_serializable(later)
    assert_serializable(result)


@pytest.mark.parametrize("mode", ["controlled-member-removal", "observation-lost"])
def test_case_e_test_only_track_observation(repository, mode):
    original = repository_state(repository, HUAWEI)
    baseline = CompetitionSnapshotBuilder(repository).build(HUAWEI, T1)
    membership = baseline.dynamic_state.track_membership
    assert membership.state == ObservationState.KNOWN_VALUE and membership.value
    assert baseline.dynamic_state.registration_window.state == ObservationState.UNKNOWN
    assert baseline.dynamic_state.competition_window.state == ObservationState.UNKNOWN
    if mode == "controlled-member-removal":
        replacement = ObservedTrackMembership(
            state="known_value", value=membership.value[1:], sources=(fixture_source(),)
        )
    else:
        replacement = ObservedTrackMembership(state="unknown")
    later = controlled(baseline, mode, track_membership=replacement)
    result = SnapshotDiffEngine().compare(baseline, later)
    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.field == "track_membership"
    assert change.before == membership
    if mode == "controlled-member-removal":
        assert change.kind == FactChangeKind.VALUE_CHANGED
        assert change.after.value == membership.value[1:]
        assert change.after.sources == (fixture_source(),)
    else:
        assert change.kind == FactChangeKind.OBSERVATION_STATE_CHANGED
        assert (
            change.after.state == ObservationState.UNKNOWN
            and change.after.value is None
        )
        assert change.kind != FactChangeKind.VALUE_CHANGED
    assert repository_state(repository, HUAWEI) == original
    assert (
        SnapshotDiffEngine().compare(baseline, later).model_dump_json()
        == result.model_dump_json()
    )
    assert_serializable(result)


def test_unknown_membership_is_not_real_known_empty(repository):
    baseline = CompetitionSnapshotBuilder(repository).build(COMAP, T1)
    known_empty = baseline.dynamic_state.track_membership
    unknown = ObservedTrackMembership(state="unknown")
    assert known_empty.value == () and unknown.value is None
    assert known_empty.model_dump_json() != unknown.model_dump_json()
    later = controlled(
        baseline, "known-empty-observation-lost", track_membership=unknown
    )
    result = SnapshotDiffEngine().compare(baseline, later)
    assert len(result.changes) == 1
    assert result.changes[0].kind == FactChangeKind.OBSERVATION_STATE_CHANGED


def test_cases_f_g_real_reverse_time_and_target_mismatch_rejected(repository):
    builder = CompetitionSnapshotBuilder(repository)
    first, later = builder.build(COMAP, T1), builder.build(COMAP, T2)
    other_target = builder.build(HUAWEI, T2)
    engine = SnapshotDiffEngine()
    with pytest.raises(ValidationError):
        engine.compare(later, first)
    with pytest.raises(ValidationError):
        engine.compare(first, other_target)
