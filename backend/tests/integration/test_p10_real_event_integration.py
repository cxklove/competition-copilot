"""Real components with CONTROLLED OFFLINE CHANGE FIXTURES only.

The approved minimal COMAP fixture/body variants are not official historical
updates or live website claims. Only HTTP transport is replaced. Real Repository
baseline, parser, Monitor, Diff, primitive Event and canonical aggregation execute.
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
from competition_copilot.domain.event_aggregation import CompetitionEventAggregator
from competition_copilot.domain.event_engine import CompetitionEventEngine
from competition_copilot.domain.monitoring import MonitorCheckRequest
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
FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures/comap_instructions/schedule.html"
)
T1 = datetime(2030, 1, 1, tzinfo=timezone.utc)
T2 = datetime(2030, 1, 2, tzinfo=timezone.utc)
T3 = datetime(2030, 1, 3, tzinfo=timezone.utc)
DETECTED = datetime(2030, 1, 4, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def offline_read_only_data(monkeypatch):
    original_open = Path.open

    def guarded_open(path, mode="r", *args, **kwargs):
        resolved = path.resolve()
        if resolved.is_relative_to(DATA):
            assert resolved.is_relative_to(SEED), "Only Repository Seed reads allowed"
            assert not any(flag in mode for flag in "wax+"), (
                "Reviewed data is read-only"
            )
        return original_open(path, mode, *args, **kwargs)

    def forbidden_network(*args, **kwargs):
        pytest.fail("Default P10.4 integration must not use network/DNS")

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(socket.socket, "connect", forbidden_network)
    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden_network)


class FixtureHttpTransport:
    """TEST-ONLY response body; never a Fake ObservationSource."""

    def __init__(self, body=None, error=None):
        self.response = ComapPageResponse(
            status=200,
            body=FIXTURE.read_bytes() if body is None else body,
            final_url=OFFICIAL_URL,
        )
        self.error = error
        self.calls = 0

    def fetch(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response


def real_baseline():
    repository = JsonSeedCompetitionRepository(SEED)
    baseline = CompetitionSnapshotBuilder(repository).build(SUPPORTED_TARGET, T1)
    source = repository.get_edition(SUPPORTED_TARGET.edition_id).source
    return repository, baseline, source


def repository_state(repository):
    return tuple(
        entity.model_dump_json()
        for entity in (
            repository.get_competition(SUPPORTED_TARGET.competition_id),
            repository.get_edition(SUPPORTED_TARGET.edition_id),
            *repository.list_tracks(SUPPORTED_TARGET.edition_id),
        )
    )


def check_chain(previous, source, observed_at, transport):
    request = MonitorCheckRequest(
        target=SUPPORTED_TARGET,
        previous_snapshot=previous,
        source=source,
        observed_at=observed_at,
    )
    before = request.model_dump_json()
    monitor = OneShotCompetitionMonitor(ComapOfficialObservationAdapter(transport))
    result = monitor.check(request)
    assert transport.calls == 1
    assert request.model_dump_json() == before
    if result.outcome.value == "check_failed":
        # Test composition stops at failed source check; P10 receives no Diff.
        return result, None, None
    primitives = CompetitionEventEngine().interpret(result.diff, detected_at=DETECTED)
    canonical = CompetitionEventAggregator().normalize(primitives)
    return result, primitives, canonical


def prime_from_real_baseline(baseline, source):
    result, primitives, canonical = check_chain(
        baseline, source, T2, FixtureHttpTransport()
    )
    # Repository is known-empty; page coverage is UNKNOWN. This real baseline
    # difference is retained, not hidden to manufacture a zero-change case.
    assert [(change.field, change.kind.value) for change in result.diff.changes] == [
        ("track_membership", "observation_state_changed"),
    ]
    assert len(primitives) == len(canonical) == 1
    assert canonical[0].event_type.value == "observation_coverage_changed"
    return result.snapshot


def missing_registration_body():
    html = FIXTURE.read_text(encoding="utf-8")
    line = next(line for line in html.splitlines() if "Registration Deadline:" in line)
    return html.replace(line, "").encode()


def controlled_competition_body():
    # CONTROLLED OFFLINE FIXTURE: two supported boundary value changes,
    # not a COMAP historical update. Source-explicit EST format is unchanged.
    return (
        FIXTURE.read_bytes()
        .replace(b"5:00 p.m.", b"6:00 p.m.")
        .replace(b"8:00 p.m.", b"7:00 p.m.")
    )


def assert_serializable(model):
    assert type(model).model_validate_json(model.model_dump_json()) == model
    assert type(model).model_validate(model.model_dump(mode="json")) == model


def assert_end_to_end(result, primitives, canonical):
    assert result.outcome.value == "check_succeeded"
    assert (
        result.snapshot.target
        == result.diff.before.target
        == result.diff.after.target
        == SUPPORTED_TARGET
    )
    assert (
        result.diff.before.snapshot_id == result.request.previous_snapshot.snapshot_id
    )
    assert result.diff.after.snapshot_id == result.snapshot.snapshot_id
    assert len(primitives) == len(result.diff.changes)
    assert tuple(event.source_changes[0] for event in primitives) == result.diff.changes
    primitive_fields = tuple(event.source_change_fields[0] for event in primitives)
    selected_fields = tuple(
        field for event in canonical for field in event.source_change_fields
    )
    assert set(selected_fields) == set(primitive_fields)
    assert len(selected_fields) == len(primitive_fields)
    for event in primitives + canonical:
        assert event.target == SUPPORTED_TARGET
        assert event.source_diff == result.diff
        assert event.observed_at == DETECTED and event.occurred_at is None
        for change in event.source_changes:
            assert change in result.diff.changes
        assert any(
            event.source == provenance
            for change in event.source_changes
            for fact in (change.before, change.after)
            for provenance in fact.sources
        )
        assert_serializable(event)
    for model in (result, result.observation, result.snapshot, result.diff):
        assert_serializable(model)


def test_case_a_real_baseline_then_same_fixture_zero_diff_zero_events():
    repository, baseline, source = real_baseline()
    original = repository_state(repository)
    assert baseline.dynamic_state.registration_window.sources == (source,)
    assert baseline.dynamic_state.competition_window.sources == (source,)
    assert baseline.dynamic_state.track_membership.value == ()
    baseline_json = baseline.model_dump_json()
    previous = prime_from_real_baseline(baseline, source)
    # Production Monitor output, not a manually fabricated baseline, now has
    # the same observation coverage as the next CONTROLLED OFFLINE FIXTURE.
    result, primitives, canonical = check_chain(
        previous, source, T3, FixtureHttpTransport()
    )
    assert result.diff.changes == () and primitives == canonical == ()
    assert result.snapshot.snapshot_id != previous.snapshot_id
    assert result.observation.source.source_url == source.source_url
    assert result.observation.source.verification_status == source.verification_status
    assert result.observation.source.observed_at == T3
    assert source.observed_at != T3
    assert baseline.model_dump_json() == baseline_json
    assert repository_state(repository) == original
    assert_end_to_end(result, primitives, canonical)


def test_case_b_controlled_registration_end_only_supported_adapter_scope():
    _, baseline, source = real_baseline()
    previous = prime_from_real_baseline(baseline, source)
    # Registration start+end case is NOT_APPLICABLE: frozen Adapter never parses
    # registration start. Verify its supported end only; do not expand the parser.
    body = FIXTURE.read_bytes().replace(b"Before 3:00 p.m.", b"Before 4:00 p.m.")
    result, primitives, canonical = check_chain(
        previous, source, T3, FixtureHttpTransport(body)
    )
    assert previous.dynamic_state.registration_window.value.start_at is None
    assert result.snapshot.dynamic_state.registration_window.value.start_at is None
    assert len(result.diff.changes) == len(primitives) == len(canonical) == 1
    assert canonical[0].event_type.value == "registration_window_changed"
    assert canonical[0].source_change_fields == ("registration_window.end_at",)
    assert_end_to_end(result, primitives, canonical)


def test_case_c_j_controlled_competition_start_end_aggregate_and_permutation():
    _, baseline, source = real_baseline()
    previous = prime_from_real_baseline(baseline, source)
    result, primitives, canonical = check_chain(
        previous, source, T3, FixtureHttpTransport(controlled_competition_body())
    )
    assert [change.field for change in result.diff.changes] == [
        "competition_window.start_at",
        "competition_window.end_at",
    ]
    assert len(primitives) == 2 and len(canonical) == 1
    assert all(
        event.event_type.value == "competition_window_changed" for event in primitives
    )
    assert canonical[0].source_change_fields == (
        "competition_window.start_at",
        "competition_window.end_at",
    )
    assert canonical[0].id not in tuple(event.id for event in primitives)
    primitive_json = tuple(event.model_dump_json() for event in primitives)
    reordered = CompetitionEventAggregator().normalize(tuple(reversed(primitives)))
    assert tuple(event.model_dump_json() for event in reordered) == tuple(
        event.model_dump_json() for event in canonical
    )
    assert tuple(event.model_dump_json() for event in primitives) == primitive_json
    assert_end_to_end(result, primitives, canonical)
    with pytest.raises(ValidationError):
        canonical[0].id = "changed"
    with pytest.raises(AttributeError):
        canonical[0].source_change_fields.append("other")


def test_case_e_successful_unknown_becomes_coverage_event_not_fact_event():
    _, baseline, source = real_baseline()
    previous = prime_from_real_baseline(baseline, source)
    result, primitives, canonical = check_chain(
        previous, source, T3, FixtureHttpTransport(missing_registration_body())
    )
    assert result.observation.error is None
    assert result.snapshot.dynamic_state.registration_window.state.value == "unknown"
    assert len(result.diff.changes) == len(primitives) == len(canonical) == 1
    assert result.diff.changes[0].kind.value == "observation_state_changed"
    assert canonical[0].event_type.value == "observation_coverage_changed"
    assert canonical[0].source_change_fields == ("registration_window",)
    assert_end_to_end(result, primitives, canonical)


def test_case_f_registration_and_track_coverage_remain_separate():
    _, baseline, source = real_baseline()
    result, primitives, canonical = check_chain(
        baseline, source, T2, FixtureHttpTransport(missing_registration_body())
    )
    # Both are coverage loss, including the real known-empty Repository membership
    # -> Adapter UNKNOWN boundary, not a fabricated track removal/change case.
    assert len(primitives) == len(canonical) == 2
    assert all(
        event.event_type.value == "observation_coverage_changed" for event in canonical
    )
    assert [event.source_change_fields for event in canonical] == [
        ("registration_window",),
        ("track_membership",),
    ]
    assert_end_to_end(result, primitives, canonical)


@pytest.mark.parametrize("failure", ["fetch", "parse"])
def test_cases_g_h_failure_stops_before_p10_no_diff_or_events(monkeypatch, failure):
    _, baseline, source = real_baseline()
    original = baseline.model_dump_json()

    def must_not_run(*args, **kwargs):
        pytest.fail("P10 must not run when Monitor has no authoritative Diff")

    monkeypatch.setattr(CompetitionEventEngine, "interpret", must_not_run)
    monkeypatch.setattr(CompetitionEventAggregator, "normalize", must_not_run)
    transport = (
        FixtureHttpTransport(error=TimeoutError())
        if failure == "fetch"
        else FixtureHttpTransport(b"<html>wrong page</html>")
    )
    result, primitives, canonical = check_chain(baseline, source, T2, transport)
    assert result.outcome.value == "check_failed"
    assert result.observation.error.code.value == failure + "_failed"
    assert result.observation.dynamic_state is None
    assert result.snapshot is None and result.diff is None
    assert primitives is None and canonical is None
    assert baseline.model_dump_json() == original
    assert_serializable(result)


@pytest.mark.parametrize("body_kind", ["same", "value", "unknown"])
def test_case_i_repeat_complete_chain_is_deterministic_read_only(body_kind):
    def execute():
        repository, baseline, source = real_baseline()
        original = repository_state(repository)
        baseline_json = baseline.model_dump_json()
        previous = prime_from_real_baseline(baseline, source)
        previous_json = previous.model_dump_json()
        body = (
            controlled_competition_body()
            if body_kind == "value"
            else missing_registration_body()
            if body_kind == "unknown"
            else FIXTURE.read_bytes()
        )
        transport = FixtureHttpTransport(body)
        response = transport.response
        result, primitives, canonical = check_chain(previous, source, T3, transport)
        assert baseline.model_dump_json() == baseline_json
        assert previous.model_dump_json() == previous_json
        assert transport.response == response
        assert repository_state(repository) == original
        assert_end_to_end(result, primitives, canonical)
        return (
            baseline.snapshot_id,
            previous.snapshot_id,
            result.snapshot.snapshot_id,
            result.model_dump_json(),
            result.diff.model_dump_json(),
            tuple(event.id for event in primitives),
            tuple(event.model_dump_json() for event in primitives),
            tuple(event.id for event in canonical),
            tuple(event.model_dump_json() for event in canonical),
        )

    assert execute() == execute()
