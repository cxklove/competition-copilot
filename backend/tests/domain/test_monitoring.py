"""Synthetic P9.5.1 contracts and fake source; no live observation/orchestration."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.application.monitoring import CompetitionObservationSource
from competition_copilot.domain.digital_twin import (
    CompetitionDynamicState,
    CompetitionSnapshot,
    CompetitionTarget,
    ObservedTimeWindow,
    ObservedTrackMembership,
    SnapshotDiff,
    SnapshotReference,
)
from competition_copilot.domain.monitoring import (
    MonitorCheckOutcome,
    MonitorCheckRequest,
    MonitorCheckResult,
    SourceCheckError,
    SourceCheckErrorCode,
    SourceObservationResult,
)
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.domain.temporal import TimeWindow

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)
BEFORE = NOW - timedelta(days=1)
TARGET = CompetitionTarget(competition_id="test-competition", edition_id="test-edition")


def source(status="verified", observed_at=BEFORE):
    return SourceMetadata(
        source_url="https://example.invalid/test-only-monitor-source",
        source_type="official",
        observed_at=observed_at,
        verification_status=status,
    )


def state(kind="unknown", metadata=None):
    return CompetitionDynamicState(
        registration_window=ObservedTimeWindow(
            state=kind,
            value=TimeWindow(end_at=NOW + timedelta(days=30))
            if kind == "known_value"
            else None,
            sources=(metadata or source(),) if kind != "unknown" else (),
        ),
        competition_window=ObservedTimeWindow(state="unknown"),
        track_membership=ObservedTrackMembership(state="unknown"),
    )


def request(previous=None, metadata=None, at=NOW):
    return MonitorCheckRequest(
        target=TARGET,
        observed_at=at,
        source=metadata or source(),
        previous_snapshot=previous,
    )


def observation(kind="unknown", metadata=None):
    return SourceObservationResult(
        target=TARGET,
        observed_at=NOW,
        source=metadata or source(),
        outcome="check_succeeded",
        dynamic_state=state(kind, metadata),
    )


def failure(code=SourceCheckErrorCode.FETCH_FAILED):
    return SourceObservationResult(
        target=TARGET,
        observed_at=NOW,
        source=source(),
        outcome="check_failed",
        error=SourceCheckError(code=code, message="TEST-ONLY source failure"),
    )


def snapshot(snapshot_id="current", at=NOW, facts=None):
    return CompetitionSnapshot(
        snapshot_id=snapshot_id,
        target=TARGET,
        observed_at=at,
        dynamic_state=facts or state(),
    )


def ref(item):
    return SnapshotReference(
        snapshot_id=item.snapshot_id, target=item.target, observed_at=item.observed_at
    )


def initial_success(kind="unknown"):
    observed = observation(kind)
    return MonitorCheckResult(
        request=request(),
        observation=observed,
        snapshot=snapshot(facts=observed.dynamic_state),
    )


class FakeSource(CompetitionObservationSource):
    def observe(self, context):
        return SourceObservationResult(
            target=context.target,
            observed_at=context.observed_at,
            source=context.source,
            outcome="check_succeeded",
            dynamic_state=state("known_value", context.source),
        )


def test_fake_source_returns_typed_success_and_preserves_context():
    context = request()
    before = context.model_dump_json()
    capability: CompetitionObservationSource = FakeSource()
    result = capability.observe(context)
    assert result.outcome == MonitorCheckOutcome.CHECK_SUCCEEDED
    assert result.target == context.target and result.observed_at == context.observed_at
    assert result.dynamic_state.registration_window.value.end_at is not None
    assert result.dynamic_state.registration_window.sources == (context.source,)
    assert context.model_dump_json() == before


@pytest.mark.parametrize("code", list(SourceCheckErrorCode))
def test_normal_source_failure_has_error_and_no_authoritative_observation(code):
    result = MonitorCheckResult(request=request(), observation=failure(code))
    assert result.outcome == MonitorCheckOutcome.CHECK_FAILED
    assert result.observation.error.code == code
    assert result.observation.dynamic_state is None
    assert result.snapshot is None and result.diff is None


def test_successful_unknown_facts_are_not_failed_checks():
    result = initial_success()
    assert MonitorCheckResult.model_validate_json(result.model_dump_json()) == result
    assert MonitorCheckResult.model_validate(result.model_dump(mode="json")) == result
    assert result.outcome == MonitorCheckOutcome.CHECK_SUCCEEDED
    assert result.observation.error is None
    assert result.snapshot.dynamic_state.registration_window.state.value == "unknown"
    assert (
        result.model_dump_json()
        != MonitorCheckResult(
            request=request(), observation=failure()
        ).model_dump_json()
    )
    pending = observation(metadata=source("pending"))
    assert pending.source.verification_status.value == "pending"
    assert pending.dynamic_state.registration_window.value is None


def test_known_absence_requires_explicit_state_not_none_or_failure():
    absent = initial_success("known_absent")
    assert (
        absent.snapshot.dynamic_state.registration_window.state.value == "known_absent"
    )
    assert (
        initial_success().snapshot.dynamic_state.registration_window.state.value
        == "unknown"
    )
    missing_state = state().model_dump()
    missing_state["registration_window"] = None
    with pytest.raises(ValidationError):
        CompetitionDynamicState.model_validate(missing_state)
    with pytest.raises(ValidationError):
        SourceObservationResult.model_validate(
            {**failure().model_dump(), "dynamic_state": state("known_absent")}
        )


@pytest.mark.parametrize(
    "model,payload",
    [
        (MonitorCheckRequest, request().model_dump()),
        (SourceObservationResult, observation().model_dump()),
    ],
)
def test_explicit_aware_time_required(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate({**payload, "observed_at": NOW.replace(tzinfo=None)})
    with pytest.raises(ValidationError):
        model.model_validate(
            {key: value for key, value in payload.items() if key != "observed_at"}
        )
    assert model.model_validate(payload).observed_at == NOW


@pytest.mark.parametrize(
    "updates",
    [
        {"error": SourceCheckError(code="parse_failed", message="TEST-ONLY")},
        {"dynamic_state": None},
    ],
)
def test_success_observation_requires_state_and_no_error(updates):
    with pytest.raises(ValidationError):
        SourceObservationResult.model_validate(
            {**observation().model_dump(), **updates}
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"error": None},
        {"dynamic_state": state()},
        {"dynamic_state": state("known_absent")},
    ],
)
def test_failed_observation_requires_error_and_forbids_unknown_or_absent_facts(updates):
    with pytest.raises(ValidationError):
        SourceObservationResult.model_validate({**failure().model_dump(), **updates})


def test_failed_monitor_forbids_snapshot_and_diff():
    baseline, current = snapshot("before", BEFORE), snapshot()
    diff = SnapshotDiff(before=ref(baseline), after=ref(current))
    for extra in ({"snapshot": current}, {"diff": diff}):
        with pytest.raises(ValidationError):
            MonitorCheckResult(
                request=request(baseline), observation=failure(), **extra
            )
    assert (
        MonitorCheckResult(request=request(baseline), observation=failure()).snapshot
        is None
    )


def test_successful_monitor_requires_snapshot_and_consistent_fact_binding():
    with pytest.raises(ValidationError):
        MonitorCheckResult(request=request(), observation=observation())
    with pytest.raises(ValidationError):
        MonitorCheckResult(
            request=request(),
            observation=observation(),
            snapshot=snapshot(facts=state("known_value")),
        )
    with pytest.raises(ValidationError):
        MonitorCheckResult(
            request=request(), observation=observation(), snapshot=snapshot(at=BEFORE)
        )


@pytest.mark.parametrize("same_snapshot", [False, True])
def test_zero_change_is_success_for_distinct_and_reflexive_observations(same_snapshot):
    current = snapshot()
    baseline = current if same_snapshot else snapshot("baseline", BEFORE)
    diff = SnapshotDiff(before=ref(baseline), after=ref(current))
    result = MonitorCheckResult(
        request=request(baseline),
        observation=observation(),
        snapshot=current,
        diff=diff,
    )
    assert result.outcome == MonitorCheckOutcome.CHECK_SUCCEEDED
    assert result.diff.changes == ()
    assert result.observation.error is None


def test_baseline_and_diff_reference_binding_fail_fast():
    baseline, current = snapshot("baseline", BEFORE), snapshot()
    with pytest.raises(ValidationError):
        MonitorCheckResult(
            request=request(baseline), observation=observation(), snapshot=current
        )
    wrong = SnapshotDiff(before=ref(snapshot("unrelated", BEFORE)), after=ref(current))
    with pytest.raises(ValidationError):
        MonitorCheckResult(
            request=request(baseline),
            observation=observation(),
            snapshot=current,
            diff=wrong,
        )
    correct = SnapshotDiff(before=ref(baseline), after=ref(current))
    with pytest.raises(ValidationError):
        MonitorCheckResult(
            request=request(), observation=observation(), snapshot=current, diff=correct
        )


def test_request_and_result_target_time_binding():
    wrong_target = CompetitionTarget(competition_id="other", edition_id="test-edition")
    with pytest.raises(ValidationError):
        MonitorCheckRequest(
            target=wrong_target,
            source=source(),
            observed_at=NOW,
            previous_snapshot=snapshot("baseline", BEFORE),
        )
    with pytest.raises(ValidationError):
        request(snapshot("future", NOW + timedelta(days=1)))
    for updates in ({"target": wrong_target}, {"observed_at": NOW + timedelta(days=1)}):
        altered = SourceObservationResult.model_validate(
            {**observation().model_dump(), **updates}
        )
        with pytest.raises(ValidationError):
            MonitorCheckResult(
                request=request(), observation=altered, snapshot=snapshot()
            )


def test_source_identity_and_verification_cannot_be_upgraded_or_rebound():
    with pytest.raises(ValidationError, match="upgrade"):
        MonitorCheckResult(
            request=request(metadata=source("pending")),
            observation=observation(),
            snapshot=snapshot(),
        )
    with pytest.raises(ValidationError):
        SourceObservationResult(
            target=TARGET,
            observed_at=NOW,
            source=source("pending"),
            outcome="check_succeeded",
            dynamic_state=state("known_value"),
        )
    different = SourceMetadata.model_validate(
        {**source().model_dump(), "source_url": "https://example.invalid/different"}
    )
    with pytest.raises(ValidationError):
        MonitorCheckResult(
            request=request(metadata=different),
            observation=observation(),
            snapshot=snapshot(),
        )


def test_same_snapshot_id_cannot_hide_different_observed_content():
    baseline = snapshot()
    current = snapshot(facts=state("known_value"))
    zero = SnapshotDiff(before=ref(baseline), after=ref(current))
    with pytest.raises(ValidationError, match="different snapshot content"):
        MonitorCheckResult(
            request=request(baseline),
            observation=observation("known_value"),
            snapshot=current,
            diff=zero,
        )


def test_source_timestamps_cannot_follow_check_time():
    future = source(observed_at=NOW + timedelta(days=1))
    with pytest.raises(ValidationError):
        request(metadata=future)
    with pytest.raises(ValidationError):
        observation(metadata=future)


@pytest.mark.parametrize(
    "model",
    [
        request(),
        observation("known_value"),
        initial_success("known_value"),
        MonitorCheckResult(request=request(), observation=failure()),
    ],
)
def test_frozen_models_and_stable_serialization(model):
    payload = model.model_dump(mode="json")
    serialized = model.model_dump_json()
    assert type(model).model_validate(payload) == model
    assert type(model).model_validate_json(serialized).model_dump_json() == serialized
    with pytest.raises(ValidationError):
        setattr(model, next(iter(type(model).model_fields)), None)
    with pytest.raises(TypeError):
        model.model_copy(update={})
    if isinstance(model, MonitorCheckResult) and model.snapshot is not None:
        with pytest.raises(ValidationError):
            model.snapshot.dynamic_state.registration_window.value.end_at = NOW
        with pytest.raises(AttributeError):
            model.observation.dynamic_state.registration_window.sources.append(source())


def test_errors_are_closed_machine_codes_and_contract_has_no_execution_policy():
    with pytest.raises(ValidationError):
        SourceCheckError(code="deadline_changed", message="TEST-ONLY")
    with pytest.raises(ValidationError):
        SourceCheckError(code="fetch_failed", message=" ")
    forbidden = {
        "event",
        "impact",
        "severity",
        "plan",
        "retry_count",
        "timeout",
        "cron",
        "notification",
    }
    for model in (MonitorCheckRequest, SourceObservationResult, MonitorCheckResult):
        assert not forbidden.intersection(model.model_fields)
