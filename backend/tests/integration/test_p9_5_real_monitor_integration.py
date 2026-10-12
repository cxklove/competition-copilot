"""Real production chain with CONTROLLED OFFLINE FIXTURE transport only.

Fixture dates/provenance exercise the approved source mapping, not a claim of
live official facts or historical changes. Repository artifacts remain read-only.
"""

import socket
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from competition_copilot.application.competition_snapshots import (
    CompetitionSnapshotBuilder,
)
from competition_copilot.application.monitor_checks import OneShotCompetitionMonitor
from competition_copilot.domain.digital_twin import CompetitionTarget, FactChangeKind
from competition_copilot.domain.monitoring import MonitorCheckRequest
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.infrastructure.comap_observation import (
    OFFICIAL_URL,
    SUPPORTED_TARGET,
    ComapOfficialObservationAdapter,
    ComapPageResponse,
)
from competition_copilot.infrastructure.repositories import (
    JsonSeedCompetitionRepository,
)

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
SEED = DATA / "seed"
PAGE = Path(__file__).resolve().parents[1] / "fixtures/comap_instructions/schedule.html"
T1 = datetime(2030, 1, 1, tzinfo=timezone.utc)
T2 = datetime(2030, 1, 2, tzinfo=timezone.utc)
T3 = datetime(2030, 1, 3, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def offline_read_only(monkeypatch):
    original_open = Path.open

    def guarded_open(path, mode="r", *args, **kwargs):
        if path.resolve().is_relative_to(DATA):
            assert path.resolve().is_relative_to(SEED)
            assert not any(flag in mode for flag in "wax+")
        return original_open(path, mode, *args, **kwargs)

    def no_network(*args, **kwargs):
        pytest.fail("P9.5.4 default integration must remain offline")

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)


class FixtureTransport:
    """Only HTTP is replaced; real Adapter parsing and Monitor logic execute."""

    def __init__(self, body=None, error=None):
        self.response = ComapPageResponse(
            status=200,
            body=PAGE.read_bytes() if body is None else body,
            final_url=OFFICIAL_URL,
        )
        self.error = error
        self.calls = 0

    def fetch(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response


@pytest.fixture
def real_chain():
    repository = JsonSeedCompetitionRepository(SEED)
    baseline = CompetitionSnapshotBuilder(repository).build(SUPPORTED_TARGET, T1)
    source = repository.get_edition(SUPPORTED_TARGET.edition_id).source
    return repository, baseline, source


def context(baseline, source, observed_at=T2):
    return MonitorCheckRequest(
        target=baseline.target,
        previous_snapshot=baseline,
        source=source,
        observed_at=observed_at,
    )


def run(request, transport):
    return OneShotCompetitionMonitor(
        ComapOfficialObservationAdapter(transport)
    ).check(request)


def changes(result):
    return [(change.field, change.kind.value) for change in result.diff.changes]


def assert_json(model):
    assert type(model).model_validate_json(model.model_dump_json()) == model
    assert type(model).model_validate(model.model_dump(mode="json")) == model


def repository_state(repository):
    return tuple(
        entity.model_dump_json()
        for entity in (
            repository.get_competition(SUPPORTED_TARGET.competition_id),
            repository.get_edition(SUPPORTED_TARGET.edition_id),
            *repository.list_tracks(SUPPORTED_TARGET.edition_id),
        )
    )


def test_case_a_real_baseline_then_same_fixture_observation_zero_diff(real_chain):
    repository, baseline, source = real_chain
    original = repository_state(repository)
    baseline_json = baseline.model_dump_json()
    assert baseline.dynamic_state.track_membership.value == ()
    assert baseline.dynamic_state.track_membership.state.value == "known_value"
    assert baseline.dynamic_state.registration_window.sources == (source,)
    assert baseline.dynamic_state.competition_window.sources == (source,)

    first = run(context(baseline, source), FixtureTransport())
    assert first.outcome.value == "check_succeeded"
    # Repository has complete known-empty children, while this page has no track
    # authority. Do not falsify the real baseline to obtain a zero-change result.
    assert changes(first) == [("track_membership", "observation_state_changed")]
    assert first.diff.changes[0].after.state.value == "unknown"
    assert first.snapshot.dynamic_state.registration_window.value == (
        baseline.dynamic_state.registration_window.value
    )
    assert first.snapshot.dynamic_state.competition_window.value == (
        baseline.dynamic_state.competition_window.value
    )
    # CONTROLLED OFFLINE FIXTURE same-state case, using a production Monitor's
    # output as previous observation; no claim that the live website is unchanged.
    second = run(context(first.snapshot, source, T3), FixtureTransport())
    assert second.outcome.value == "check_succeeded"
    assert second.snapshot is not None and second.diff.changes == ()
    assert first.snapshot.snapshot_id != second.snapshot.snapshot_id
    assert second.diff.before.snapshot_id == first.snapshot.snapshot_id
    assert second.diff.after.snapshot_id == second.snapshot.snapshot_id
    assert first.observation.source.source_url == source.source_url
    assert first.observation.source.source_type == source.source_type
    assert first.observation.source.verification_status == source.verification_status
    assert first.observation.source.observed_at == T2
    assert second.observation.source.observed_at == T3
    assert source.observed_at != T1
    assert baseline.model_dump_json() == baseline_json
    assert repository_state(repository) == original
    for result in (first, second):
        for model in (result, result.observation, result.snapshot, result.diff):
            assert_json(model)


def test_case_b_successful_missing_optional_fact_is_observation_loss(real_chain):
    _, baseline, source = real_chain
    html = PAGE.read_text(encoding="utf-8")
    line = next(line for line in html.splitlines() if "Registration Deadline:" in line)
    result = run(context(baseline, source), FixtureTransport(html.replace(line, "").encode()))
    assert result.outcome.value == "check_succeeded"
    assert result.snapshot is not None and result.observation.error is None
    assert result.snapshot.dynamic_state.registration_window.state.value == "unknown"
    assert changes(result) == [
        ("registration_window", "observation_state_changed"),
        ("track_membership", "observation_state_changed"),
    ]
    assert all(change.kind != FactChangeKind.PRESENCE_CHANGED for change in result.diff.changes)
    assert_json(result)


def test_case_c_controlled_offline_boundary_value_change(real_chain):
    _, baseline, source = real_chain
    # CONTROLLED OFFLINE FIXTURE: synthetic clock change, not official history.
    body = PAGE.read_bytes().replace(b"Before 3:00 p.m.", b"Before 4:00 p.m.")
    result = run(context(baseline, source), FixtureTransport(body))
    assert result.outcome.value == "check_succeeded"
    assert changes(result) == [
        ("registration_window.end_at", "value_changed"),
        ("track_membership", "observation_state_changed"),
    ]
    change = result.diff.changes[0]
    assert change.before.value.hour == 15 and change.after.value.hour == 16
    assert change.before.sources == (source,)
    assert change.after.sources == (result.observation.source,)
    assert_json(result)


@pytest.mark.parametrize("error", [TimeoutError(), ConnectionError()])
def test_case_e_transport_failure_no_snapshot_or_diff(real_chain, error):
    _, baseline, source = real_chain
    original = baseline.model_dump_json()
    transport = FixtureTransport(error=error)
    result = run(context(baseline, source), transport)
    assert transport.calls == 1
    assert result.outcome.value == "check_failed"
    assert result.observation.error.code.value == "fetch_failed"
    assert result.observation.dynamic_state is None
    assert result.snapshot is None and result.diff is None
    assert baseline.model_dump_json() == original
    assert_json(result)


def test_case_f_parse_failure_no_snapshot_or_diff(real_chain):
    _, baseline, source = real_chain
    result = run(context(baseline, source), FixtureTransport(b"<html>wrong page</html>"))
    assert result.outcome.value == "check_failed"
    assert result.observation.error.code.value == "parse_failed"
    assert result.observation.dynamic_state is None
    assert result.snapshot is None and result.diff is None
    assert_json(result)


def test_case_g_unsupported_real_target_safe_failure(real_chain):
    repository, _, source = real_chain
    other = CompetitionTarget(competition_id="huawei-ict", edition_id="huawei-ict-2026")
    baseline = CompetitionSnapshotBuilder(repository).build(other, T1)
    transport = FixtureTransport()
    result = run(context(baseline, source), transport)
    assert transport.calls == 0
    assert result.outcome.value == "check_failed"
    assert result.observation.error.code.value == "source_unavailable"
    assert result.snapshot is None and result.diff is None


def test_case_h_reverse_time_rejected_before_fetch(real_chain):
    _, baseline, source = real_chain
    later = run(context(baseline, source), FixtureTransport()).snapshot
    with pytest.raises(ValidationError, match="Baseline observation cannot follow"):
        context(later, source, T1)


def test_case_i_determinism_input_and_output_immutability(real_chain):
    repository, baseline, source = real_chain
    request = context(baseline, source)
    original = request.model_dump_json()
    original_repository = repository_state(repository)
    transport = FixtureTransport()
    original_response = transport.response
    first, second = run(request, transport), run(request, transport)
    assert transport.calls == 2 and transport.response == original_response
    assert first.observation.model_dump_json() == second.observation.model_dump_json()
    assert first.snapshot.snapshot_id == second.snapshot.snapshot_id
    assert first.diff.model_dump_json() == second.diff.model_dump_json()
    assert first.model_dump_json() == second.model_dump_json()
    assert request.model_dump_json() == original
    assert repository_state(repository) == original_repository
    for model, field, value in (
        (first, "snapshot", None),
        (first.snapshot, "snapshot_id", "changed"),
        (first.diff.changes[0], "kind", "value_changed"),
    ):
        with pytest.raises(ValidationError):
            setattr(model, field, value)
    with pytest.raises(AttributeError):
        first.diff.changes.append(None)


def test_successful_fetch_does_not_upgrade_pending_source(real_chain):
    _, baseline, source = real_chain
    pending = SourceMetadata(
        source_url=source.source_url,
        source_type=source.source_type,
        observed_at=source.observed_at,
        verification_status="pending",
    )
    result = run(context(baseline, pending), FixtureTransport())
    assert result.outcome.value == "check_failed"
    assert result.observation.source.verification_status.value == "pending"
    assert result.observation.error.code.value == "invalid_observation"
    assert result.snapshot is None and result.diff is None
