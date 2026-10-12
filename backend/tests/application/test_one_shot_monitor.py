"""Deterministic fake source tests; no network, Repository or runtime fake wiring."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

import competition_copilot.application.monitor_checks as monitor_module
from competition_copilot.application.competition_snapshots import _snapshot_id
from competition_copilot.application.monitor_checks import OneShotCompetitionMonitor
from competition_copilot.application.monitoring import CompetitionObservationSource
from competition_copilot.domain.digital_twin import (
    CompetitionDynamicState,
    CompetitionSnapshot,
    CompetitionTarget,
    FactChangeKind,
    ObservedTimeWindow,
    ObservedTrackMembership,
)
from competition_copilot.domain.monitoring import (
    MonitorCheckOutcome,
    MonitorCheckRequest,
    MonitorCheckResult,
    SourceCheckError,
    SourceCheckErrorCode,
    SourceObservationResult,
)
from competition_copilot.domain.snapshot_diff_engine import SnapshotDiffEngine
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.temporal import TimeWindow

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)
BEFORE = NOW - timedelta(days=1)
SOURCE_TIME = BEFORE - timedelta(days=1)
END = datetime(2027, 1, 1, tzinfo=timezone.utc)
TARGET = CompetitionTarget(competition_id="test-competition", edition_id="test-edition")


def source(status="verified", at=SOURCE_TIME):
    return SourceMetadata(
        source_url="https://example.invalid/test-only-one-shot-source",
        source_type="manual",
        observed_at=at,
        verification_status=status,
    )


def state(window="unknown", tracks="unknown", ids=("a", "b"), end=END, metadata=None):
    provenance = metadata or source()
    return CompetitionDynamicState(
        registration_window=ObservedTimeWindow(
            state=window,
            value=TimeWindow(end_at=end) if window == "known_value" else None,
            sources=(provenance,) if window != "unknown" else (),
        ),
        competition_window=ObservedTimeWindow(state="unknown"),
        track_membership=ObservedTrackMembership(
            state=tracks,
            value=ids if tracks == "known_value" else None,
            sources=(provenance,) if tracks != "unknown" else (),
        ),
    )


def previous(facts, at=BEFORE):
    return CompetitionSnapshot(
        snapshot_id=_snapshot_id(TARGET, at, facts),
        target=TARGET,
        observed_at=at,
        dynamic_state=facts,
    )


def success(facts, metadata=None, target=TARGET, at=NOW):
    return SourceObservationResult(
        target=target,
        observed_at=at,
        source=metadata or source(),
        outcome="check_succeeded",
        dynamic_state=facts,
    )


def request(baseline, metadata=None, at=NOW):
    return MonitorCheckRequest(
        target=TARGET,
        previous_snapshot=baseline,
        source=metadata or source(),
        observed_at=at,
    )


class FakeCompetitionObservationSource(CompetitionObservationSource):
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def observe(self, context):
        self.calls += 1
        return self.result


class RecordingDiffEngine(SnapshotDiffEngine):
    def __init__(self):
        self.calls = []

    def compare(self, before, after):
        self.calls.append((before.snapshot_id, after.snapshot_id))
        return super().compare(before, after)


class ForbiddenDiffEngine(SnapshotDiffEngine):
    def compare(self, before, after):
        pytest.fail("Failure/invalid context must not execute Diff")


def run(old_state, current_state, metadata=None):
    baseline = previous(old_state)
    context = request(baseline, metadata)
    observed = success(current_state, metadata)
    fake = FakeCompetitionObservationSource(observed)
    engine = RecordingDiffEngine()
    result = OneShotCompetitionMonitor(fake, engine).check(context)
    assert fake.calls == 1
    assert engine.calls == [(baseline.snapshot_id, result.snapshot.snapshot_id)]
    assert result.outcome == MonitorCheckOutcome.CHECK_SUCCEEDED
    assert result.snapshot.dynamic_state == current_state
    assert result.snapshot.observed_at == observed.observed_at == NOW
    return result


@pytest.mark.parametrize("code", list(SourceCheckErrorCode))
def test_failure_preserves_error_without_snapshot_identity_or_diff(monkeypatch, code):
    baseline = previous(state("known_value", "known_value"))
    context = request(baseline)
    failed = SourceObservationResult(
        target=TARGET,
        observed_at=NOW,
        source=source(),
        outcome="check_failed",
        error=SourceCheckError(code=code, message="TEST-ONLY source failure"),
    )
    before_json = baseline.model_dump_json()

    def forbidden_creation(*args, **kwargs):
        pytest.fail("Source failure must not create a Snapshot or identity")

    monkeypatch.setattr(monitor_module, "CompetitionSnapshot", forbidden_creation)
    monkeypatch.setattr(monitor_module, "_snapshot_id", forbidden_creation)
    fake = FakeCompetitionObservationSource(failed)
    result = OneShotCompetitionMonitor(fake, ForbiddenDiffEngine()).check(context)
    assert fake.calls == 1
    assert result.outcome == MonitorCheckOutcome.CHECK_FAILED
    assert result.observation.error == failed.error
    assert result.observation.dynamic_state is None
    assert result.snapshot is None and result.diff is None
    assert baseline.model_dump_json() == before_json
    assert MonitorCheckResult.model_validate_json(result.model_dump_json()) == result
    assert MonitorCheckResult.model_validate(result.model_dump(mode="json")) == result


def test_same_state_later_observation_is_success_with_zero_diff():
    facts = state("known_value", "known_value")
    result = run(facts, facts)
    assert result.diff.changes == ()
    assert result.snapshot.snapshot_id != result.request.previous_snapshot.snapshot_id
    assert result.observation.error is None
    assert MonitorCheckResult.model_validate_json(result.model_dump_json()) == result
    assert MonitorCheckResult.model_validate(result.model_dump(mode="json")) == result


def test_same_exact_observation_identity_uses_formal_reflexive_diff():
    facts = state("known_value", "known_value")
    baseline = previous(facts, NOW)
    fake = FakeCompetitionObservationSource(success(facts))
    engine = RecordingDiffEngine()
    result = OneShotCompetitionMonitor(fake, engine).check(request(baseline))
    assert result.snapshot == baseline
    assert result.diff.before == result.diff.after
    assert result.diff.changes == ()
    assert engine.calls == [(baseline.snapshot_id, baseline.snapshot_id)]


@pytest.mark.parametrize(
    "old,new,expected",
    [
        ("known_value", "unknown", "observation_state_changed"),
        ("unknown", "known_value", "observation_state_changed"),
        ("known_absent", "known_value", "presence_changed"),
    ],
)
def test_successful_observation_transitions_reuse_p9_semantics(old, new, expected):
    result = run(state(old), state(new))
    assert len(result.diff.changes) == 1
    change = result.diff.changes[0]
    assert change.field == "registration_window"
    assert change.kind.value == expected
    if "unknown" in (old, new):
        assert change.kind != FactChangeKind.PRESENCE_CHANGED
        assert change.kind != FactChangeKind.VALUE_CHANGED


def test_successful_full_unknown_is_not_fetch_failure_and_preserves_pending_policy():
    pending = source("pending")
    result = run(state(), state(), pending)
    assert result.outcome == MonitorCheckOutcome.CHECK_SUCCEEDED
    assert result.snapshot is not None and result.diff.changes == ()
    assert result.observation.source.verification_status.value == "pending"
    assert result.observation.error is None
    lost = run(state("known_value", "known_value"), state())
    assert lost.snapshot is not None
    assert [change.field for change in lost.diff.changes] == [
        "registration_window",
        "track_membership",
    ]
    assert all(
        change.kind == FactChangeKind.OBSERVATION_STATE_CHANGED
        for change in lost.diff.changes
    )


def test_structured_value_change_is_only_value_changed():
    result = run(
        state("known_value"), state("known_value", end=END + timedelta(days=1))
    )
    assert len(result.diff.changes) == 1
    change = result.diff.changes[0]
    assert change.field == "registration_window.end_at"
    assert change.kind == FactChangeKind.VALUE_CHANGED
    assert change.before.value == END
    assert change.after.value == END + timedelta(days=1)


def test_known_track_set_change_preserves_exact_member_difference():
    result = run(
        state(tracks="known_value"), state(tracks="known_value", ids=("a", "b", "c"))
    )
    assert len(result.diff.changes) == 1
    change = result.diff.changes[0]
    assert (
        change.field == "track_membership"
        and change.kind == FactChangeKind.VALUE_CHANGED
    )
    assert set(change.after.value) - set(change.before.value) == {"c"}
    assert set(change.before.value) - set(change.after.value) == set()


def test_known_tracks_to_unknown_does_not_remove_members():
    result = run(state(tracks="known_value"), state())
    assert len(result.diff.changes) == 1
    change = result.diff.changes[0]
    assert change.kind == FactChangeKind.OBSERVATION_STATE_CHANGED
    assert change.before.value == ("a", "b") and change.after.value is None


@pytest.mark.parametrize("invalid", ["target", "earlier_time", "verification"])
def test_source_binding_violation_rejected_before_snapshot_or_diff(
    monkeypatch, invalid
):
    baseline = previous(state())
    context = request(
        baseline, source("pending") if invalid == "verification" else None
    )
    other = CompetitionTarget(competition_id="other", edition_id="other")
    observed = success(
        state(),
        target=other if invalid == "target" else TARGET,
        at=SOURCE_TIME if invalid == "earlier_time" else NOW,
    )

    def forbidden_creation(*args, **kwargs):
        pytest.fail("Invalid source binding must not create a Snapshot")

    monkeypatch.setattr(monitor_module, "CompetitionSnapshot", forbidden_creation)
    fake = FakeCompetitionObservationSource(observed)
    with pytest.raises(ValueError):
        OneShotCompetitionMonitor(fake, ForbiddenDiffEngine()).check(context)
    assert fake.calls == 1


def test_reverse_request_time_rejected_by_frozen_contract():
    with pytest.raises(ValidationError):
        request(previous(state(), NOW), at=BEFORE)


def test_initial_success_without_baseline_does_not_require_diff():
    fake = FakeCompetitionObservationSource(success(state()))
    result = OneShotCompetitionMonitor(fake, ForbiddenDiffEngine()).check(request(None))
    assert fake.calls == 1
    assert result.snapshot is not None and result.diff is None


def test_new_observation_provenance_is_preserved_not_replaced_by_baseline():
    original = state("known_value")
    current_source = source(at=NOW)
    current = state("known_value", metadata=current_source)
    result = run(original, current, current_source)
    assert result.snapshot.dynamic_state.registration_window.sources == (
        current_source,
    )
    assert (
        result.snapshot.dynamic_state.registration_window.sources
        != original.registration_window.sources
    )
    assert result.diff.changes == ()


def test_determinism_input_immutability_and_serialization():
    baseline = previous(state("known_value", "known_value"))
    observed = success(state("unknown", "known_value", ids=("a", "b", "c")))
    context = request(baseline)
    originals = (
        baseline.model_dump_json(),
        observed.model_dump_json(),
        context.model_dump_json(),
    )
    fake = FakeCompetitionObservationSource(observed)
    monitor = OneShotCompetitionMonitor(fake)
    first, second = monitor.check(context), monitor.check(context)
    assert fake.calls == 2
    assert first == second and first.model_dump_json() == second.model_dump_json()
    assert first.snapshot.snapshot_id == second.snapshot.snapshot_id
    assert originals == (
        baseline.model_dump_json(),
        observed.model_dump_json(),
        context.model_dump_json(),
    )
    assert [change.field for change in first.diff.changes] == [
        "registration_window",
        "track_membership",
    ]
    assert MonitorCheckResult.model_validate(first.model_dump(mode="json")) == first
    assert MonitorCheckResult.model_validate_json(first.model_dump_json()) == first
    with pytest.raises(ValidationError):
        first.snapshot.observed_at = BEFORE
    with pytest.raises(ValidationError):
        first.diff.changes[0].kind = FactChangeKind.VALUE_CHANGED
    with pytest.raises(AttributeError):
        first.diff.changes.append(None)


def test_untyped_source_return_is_contract_error_without_retry():
    fake = FakeCompetitionObservationSource(success(state()).model_dump())
    with pytest.raises(TypeError):
        OneShotCompetitionMonitor(fake, ForbiddenDiffEngine()).check(
            request(previous(state()))
        )
    assert fake.calls == 1
