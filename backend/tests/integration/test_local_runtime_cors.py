"""Exact-origin browser transport on real Local HTTP; no external network/model."""

from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

pytest.importorskip("langgraph")

import test_local_runtime

from competition_copilot.integrations.local_runtime.http import create_server

ORIGIN = "http://127.0.0.1:5173"
hosted = test_local_runtime.hosted
offline = test_local_runtime.offline
post = test_local_runtime.post


def options(url, *, origin=ORIGIN, method="POST", headers="content-type", route="/runtime/invoke"):
    values = {}
    for name, value in (("Origin", origin), ("Access-Control-Request-Method", method),
                        ("Access-Control-Request-Headers", headers)):
        if value is not None:
            values[name] = value
    call = Request(url + route, method="OPTIONS", headers=values)
    try:
        response = urlopen(call, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.read(), response.headers


def assert_cors(headers, origin):
    assert headers.get("Access-Control-Allow-Origin") == origin
    assert "Origin" in headers["Vary"].split(", ")
    assert headers.get("Access-Control-Allow-Origin") != "*"
    assert headers.get("Access-Control-Allow-Credentials") is None


@pytest.mark.parametrize("origin", [ORIGIN, "http://localhost:5173"])
@pytest.mark.parametrize("requested", ["content-type", "Content-Type", None])
def test_preflight_exact_origin_and_headers_without_invocation(hosted, origin, requested):
    host, url, calls = hosted
    status, body, headers = options(url, origin=origin, headers=requested)
    assert status == 204 and body == b""
    assert_cors(headers, origin)
    assert headers["Access-Control-Allow-Methods"] == "POST"
    assert headers["Access-Control-Allow-Headers"] == "Content-Type"
    assert host.handler_invocations == 0 and calls == []


@pytest.mark.parametrize("origin", ["https://external.invalid", "http://127.0.0.1:5173.evil.invalid", "null", None])
def test_preflight_forbidden_or_missing_origin_has_no_access(hosted, origin):
    host, url, calls = hosted
    status, _, headers = options(url, origin=origin)
    assert status == 403 and headers.get("Access-Control-Allow-Origin") is None
    assert headers.get("Access-Control-Allow-Methods") is None
    assert host.handler_invocations == 0 and calls == []


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE", None])
def test_preflight_rejects_other_or_missing_methods(hosted, method):
    host, url, calls = hosted
    status, _, headers = options(url, method=method)
    assert status == 403 and headers.get("Access-Control-Allow-Methods") is None
    assert host.handler_invocations == 0 and calls == []


@pytest.mark.parametrize("requested", ["Authorization", "content-type, x-custom", "content-type,,", "Cookie"])
def test_preflight_rejects_unapproved_headers(hosted, requested):
    host, url, calls = hosted
    status, _, headers = options(url, headers=requested)
    assert status == 403 and headers.get("Access-Control-Allow-Headers") is None
    assert host.handler_invocations == 0 and calls == []


@pytest.mark.parametrize("origin", [ORIGIN, "http://localhost:5173"])
def test_allowed_post_exposes_real_response_and_invokes_once(hosted, origin):
    host, url, calls = hosted
    assert options(url, origin=origin)[0] == 204
    assert host.handler_invocations == 0
    status, result, headers = post(url, {"request": {"request_id": "cors", "user_message": "discovery"}},
                                    headers={"Origin": origin})
    assert status == 200 and result["runtime"]["response"]["outcome"] == "COMPLETED"
    assert_cors(headers, origin)
    assert host.handler_invocations == 1 and calls == [("run", "cors")]


def test_no_origin_post_remains_supported_without_cors_access(hosted):
    host, url, _ = hosted
    status, result, headers = post(url, {"request": {"request_id": "non-browser", "user_message": "discovery"}})
    assert status == 200 and result["runtime"]["response"]["outcome"] == "COMPLETED"
    assert headers.get("Access-Control-Allow-Origin") is None and host.handler_invocations == 1


def test_forbidden_post_never_reflects_or_invokes(hosted):
    host, url, calls = hosted
    status, _, headers = post(url, {"discard": "x" * 65536}, headers={"Origin": "https://external.invalid"})
    assert status == 403 and headers.get("Access-Control-Allow-Origin") is None
    assert host.handler_invocations == 0 and calls == []


@pytest.mark.parametrize("route,extra,status", [
    ("/eligibility", {}, 404), ("/runtime/invoke", {"Content-Type": "text/plain"}, 415),
])
def test_early_error_with_allowed_origin_has_cors_and_no_invocation(hosted, route, extra, status):
    host, url, calls = hosted
    code, _, headers = post(url, {}, route=route, headers={"Origin": ORIGIN, **extra})
    assert code == status
    assert_cors(headers, ORIGIN)
    assert host.handler_invocations == 0 and calls == []


def test_payload_limit_error_keeps_cors_without_sending_rejected_body(hosted):
    host, url, calls = hosted
    # Advertise an oversized payload without sending bytes that cannot be drained
    # under the existing 1 MiB bound. Header handling must not rely on a TCP reset.
    call = Request(url + "/runtime/invoke", data=b"", headers={"Origin": ORIGIN,
        "Content-Type": "application/json", "Content-Length": "1048577"})
    with pytest.raises(HTTPError) as error:
        urlopen(call, timeout=10)
    with error.value as response:
        assert response.status == 413
        assert_cors(response.headers, ORIGIN)
        assert response.read()
    assert host.handler_invocations == 0 and calls == []


def test_invalid_preflight_path_is_not_business_endpoint(hosted):
    host, url, calls = hosted
    status, _, headers = options(url, route="/eligibility")
    assert status == 404 and headers.get("Access-Control-Allow-Methods") is None
    assert host.handler_invocations == 0 and calls == []


def test_invalid_payload_and_sanitized_runtime_error_keep_cors(hosted):
    host, url, _ = hosted
    status, body, headers = post(url, {"state": {}}, headers={"Origin": ORIGIN})
    assert status == 200 and body["runtime"]["error"]["code"] == "INVALID_RUNTIME_PAYLOAD"
    assert_cors(headers, ORIGIN)

    def broken(request):
        raise RuntimeError("private traceback")

    host.factory = broken
    status, body, headers = post(url, {"request": {"request_id": "broken", "user_message": "discovery"}},
                                headers={"Origin": ORIGIN})
    assert status == 200 and body["runtime"]["error"]["code"] == "RUNTIME_DEPENDENCY_ERROR"
    assert_cors(headers, ORIGIN)


def test_wildcard_config_is_rejected_and_origin_allowlist_is_authoritative():
    with pytest.raises(ValueError, match="Wildcard"):
        create_server(None, port=0, origins=("*",))
