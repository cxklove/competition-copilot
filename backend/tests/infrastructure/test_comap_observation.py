"""Offline synthetic page/HTTP fixtures; no claims of live official updates."""

import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest
from pydantic import ValidationError

import competition_copilot.infrastructure.comap_observation as module
from competition_copilot.domain.digital_twin import CompetitionTarget, ObservationState
from competition_copilot.domain.monitoring import (
    MonitorCheckOutcome,
    MonitorCheckRequest,
    SourceCheckErrorCode,
)
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.infrastructure.comap_observation import (
    MAX_BODY_BYTES,
    OFFICIAL_URL,
    SUPPORTED_TARGET,
    ComapOfficialObservationAdapter,
    ComapPageResponse,
    ComapParseError,
    UrllibComapPageFetcher,
    parse_comap_schedule,
)

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)
FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures/comap_instructions/schedule.html"
)


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Default adapter tests must be offline")

    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setattr(socket, "create_connection", fail)


def request(status="verified", target=SUPPORTED_TARGET, url=OFFICIAL_URL):
    return MonitorCheckRequest(
        target=target,
        observed_at=NOW,
        source=SourceMetadata(
            source_url=url,
            source_type="official",
            observed_at=NOW - timedelta(days=1),
            verification_status=status,
        ),
    )


class FakeFetcher:
    def __init__(
        self,
        body=None,
        status=200,
        url=OFFICIAL_URL,
        content_type="text/html; charset=UTF-8",
        error=None,
    ):
        self.response = ComapPageResponse(
            status, FIXTURE.read_bytes() if body is None else body, url, content_type
        )
        self.error = error
        self.calls = 0

    def fetch(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response


def observe(body=None, **fetch_options):
    fetcher = FakeFetcher(body=body, **fetch_options)
    result = ComapOfficialObservationAdapter(fetcher).observe(request())
    assert fetcher.calls == 1
    return result


def assert_failure(result, code):
    assert result.outcome == MonitorCheckOutcome.CHECK_FAILED
    assert result.error.code == code
    assert result.dynamic_state is None


def test_happy_path_exact_est_times_partial_registration_and_provenance():
    context = request()
    original = context.model_dump_json()
    result = ComapOfficialObservationAdapter(FakeFetcher()).observe(context)
    assert (
        result.outcome == MonitorCheckOutcome.CHECK_SUCCEEDED and result.error is None
    )
    assert result.target == SUPPORTED_TARGET and result.observed_at == NOW
    registration = result.dynamic_state.registration_window
    competition = result.dynamic_state.competition_window
    assert registration.state == competition.state == ObservationState.KNOWN_VALUE
    assert registration.value.start_at is None
    assert registration.value.end_at.isoformat() == "2027-01-28T15:00:00-05:00"
    assert competition.value.start_at.isoformat() == "2027-01-28T17:00:00-05:00"
    assert competition.value.end_at.isoformat() == "2027-02-01T20:00:00-05:00"
    assert registration.sources == competition.sources == (result.source,)
    assert str(result.source.source_url) == OFFICIAL_URL
    assert result.source.source_type == context.source.source_type
    assert result.source.verification_status == context.source.verification_status
    assert result.source.observed_at == NOW
    assert context.model_dump_json() == original
    assert result.dynamic_state.track_membership.state == ObservationState.UNKNOWN
    assert result.dynamic_state.track_membership.value is None


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError(),
        URLError("connection unavailable"),
        ConnectionError(),
        HTTPError(OFFICIAL_URL, 503, "unavailable", {}, None),
    ],
)
def test_http_external_failures_are_typed_not_unknown_facts(error):
    assert_failure(observe(error=error), SourceCheckErrorCode.FETCH_FAILED)


@pytest.mark.parametrize(
    "status,code",
    [
        (404, "source_unavailable"),
        (410, "source_unavailable"),
        (500, "fetch_failed"),
        (503, "fetch_failed"),
        (302, "fetch_failed"),
    ],
)
def test_http_status_failure_is_not_known_absence(status, code):
    assert_failure(observe(status=status), SourceCheckErrorCode(code))


@pytest.mark.parametrize(
    "body",
    [
        b"<html><title>Login</title></html>",
        b"",
        b"<strong>2027 Contest Dates and Times:</strong><ul><li>TBA</li></ul>",
        FIXTURE.read_bytes().replace(b"2027 Contest Dates", b"2028 Contest Dates"),
        FIXTURE.read_bytes().replace(b"</ul>", b""),
    ],
)
def test_missing_or_wrong_required_root_is_parse_failure(body):
    assert_failure(observe(body), SourceCheckErrorCode.PARSE_FAILED)


def test_optional_fact_missing_is_successful_unknown_not_absence():
    html = FIXTURE.read_text(encoding="utf-8")
    line = next(line for line in html.splitlines() if "Registration Deadline:" in line)
    result = observe(html.replace(line, "").encode())
    assert result.outcome == MonitorCheckOutcome.CHECK_SUCCEEDED
    assert result.dynamic_state.registration_window.state == ObservationState.UNKNOWN
    assert result.dynamic_state.registration_window.value is None
    assert result.dynamic_state.competition_window.state == ObservationState.KNOWN_VALUE
    assert "known_absent" not in result.model_dump_json()


def test_changed_list_structure_is_failure_not_successful_all_unknown():
    body = (
        "<title>Contest Rules, Registration and Instructions</title>"
        "<p><strong>2027 Contest Dates and Times:</strong></p>"
        "<ul><li>Unrecognized replacement page content</li></ul>"
    )
    assert_failure(observe(body.encode()), SourceCheckErrorCode.PARSE_FAILED)


@pytest.mark.parametrize(
    "replacement",
    [
        "Thursday, January 28, 2027.",
        "Before 3:00 p.m. on Thursday, January 28, 2027.",
        "Before 3:00 p.m. PST on Thursday, January 28, 2027.",
    ],
)
def test_date_only_missing_or_unreviewed_zone_remains_unknown(replacement):
    body = (
        FIXTURE.read_text(encoding="utf-8")
        .replace("Before 3:00 p.m. EST on Thursday, January 28, 2027.", replacement)
        .encode()
    )
    result = observe(body)
    assert result.outcome == MonitorCheckOutcome.CHECK_SUCCEEDED
    assert result.dynamic_state.registration_window.state == ObservationState.UNKNOWN
    assert result.dynamic_state.registration_window.value is None


@pytest.mark.parametrize(
    "replacement",
    [
        "Before 25:00 p.m. EST on Thursday, January 28, 2027.",
        "Before 3:00 p.m. EST on Friday, January 28, 2027.",
        "random unsupported value",
    ],
)
def test_invalid_labeled_format_does_not_pretend_success(replacement):
    body = (
        FIXTURE.read_text(encoding="utf-8")
        .replace("Before 3:00 p.m. EST on Thursday, January 28, 2027.", replacement)
        .encode()
    )
    assert_failure(observe(body), SourceCheckErrorCode.PARSE_FAILED)


def test_duplicate_labels_are_not_silently_resolved():
    body = FIXTURE.read_text(encoding="utf-8")
    line = next(line for line in body.splitlines() if "Registration Deadline:" in line)
    assert_failure(
        observe(body.replace(line, line + line).encode()),
        SourceCheckErrorCode.PARSE_FAILED,
    )


def test_dates_outside_schedule_list_do_not_supply_missing_facts():
    html = FIXTURE.read_text(encoding="utf-8")
    line = next(line for line in html.splitlines() if "Registration Deadline:" in line)
    result = observe(
        html.replace(line, "").replace("</body>", line + "</body>").encode()
    )
    assert result.dynamic_state.registration_window.state == ObservationState.UNKNOWN


def test_partial_competition_window_keeps_known_start():
    html = FIXTURE.read_text(encoding="utf-8")
    line = next(line for line in html.splitlines() if "Contest Ends:" in line)
    result = observe(html.replace(line, "").encode())
    assert result.outcome == MonitorCheckOutcome.CHECK_SUCCEEDED
    assert result.dynamic_state.competition_window.state == ObservationState.KNOWN_VALUE
    assert result.dynamic_state.competition_window.value.end_at is None
    assert result.dynamic_state.competition_window.value.start_at is not None


@pytest.mark.parametrize(
    "target,url",
    [
        (CompetitionTarget(competition_id="other", edition_id="other"), OFFICIAL_URL),
        (
            CompetitionTarget(competition_id="comap-mcm", edition_id="comap-mcm-2028"),
            OFFICIAL_URL,
        ),
        (
            CompetitionTarget(
                competition_id="comap-mcm", edition_id="comap-mcm-2027", track_id="fake"
            ),
            OFFICIAL_URL,
        ),
        (SUPPORTED_TARGET, "https://127.0.0.1/internal"),
        (SUPPORTED_TARGET, "https://contest.comap.com/unapproved"),
    ],
)
def test_unsupported_target_or_url_rejected_before_fetch(target, url):
    fake = FakeFetcher()
    result = ComapOfficialObservationAdapter(fake).observe(
        request(target=target, url=url)
    )
    assert_failure(result, SourceCheckErrorCode.SOURCE_UNAVAILABLE)
    assert fake.calls == 0


@pytest.mark.parametrize(
    "options",
    [
        {"url": "https://127.0.0.1/internal"},
        {"url": "https://other.example/instructions"},
        {"body": b"x" * (MAX_BODY_BYTES + 1)},
        {"body": b"\xff"},
        {"content_type": "application/json"},
    ],
)
def test_invalid_response_is_failure(options):
    assert_failure(observe(**options), SourceCheckErrorCode.FETCH_FAILED)


def test_existing_verification_is_not_upgraded_by_fetch_success():
    result = ComapOfficialObservationAdapter(FakeFetcher()).observe(request("pending"))
    assert_failure(result, SourceCheckErrorCode.INVALID_OBSERVATION)
    assert result.source.verification_status.value == "pending"


def test_parser_and_adapter_determinism_serialization_immutability():
    adapter = ComapOfficialObservationAdapter(FakeFetcher())
    first, second = adapter.observe(request()), adapter.observe(request())
    assert first == second and first.model_dump_json() == second.model_dump_json()
    assert type(first).model_validate_json(first.model_dump_json()) == first
    assert type(first).model_validate(first.model_dump(mode="json")) == first
    facts = parse_comap_schedule(FIXTURE.read_text(encoding="utf-8"), first.source)
    assert facts == first.dynamic_state
    with pytest.raises(ValidationError):
        first.source.verification_status = "verified"


def test_parser_root_validation_is_independent_of_fetch():
    with pytest.raises(ComapParseError):
        parse_comap_schedule("<html></html>", request().source)


def test_stdlib_fetcher_fixed_url_bounded_read_and_redirect_denial(monkeypatch):
    captured = {}

    class Response:
        status = 200
        headers = {"Content-Type": "text/html; charset=UTF-8"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def geturl(self):
            return OFFICIAL_URL

        def read(self, size):
            captured["size"] = size
            return FIXTURE.read_bytes()

    class Opener:
        def open(self, req, timeout):
            captured["url"] = req.full_url
            captured["timeout"] = timeout
            return Response()

    def fake_opener(*handlers):
        captured["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(module, "build_opener", fake_opener)
    response = UrllibComapPageFetcher().fetch()
    assert response.status == 200
    assert captured["url"] == OFFICIAL_URL and captured["size"] == MAX_BODY_BYTES + 1
    redirect = next(
        handler
        for handler in captured["handlers"]
        if isinstance(handler, module._NoRedirect)
    )
    assert (
        redirect.redirect_request(None, None, 302, "", {}, "http://127.0.0.1/") is None
    )
