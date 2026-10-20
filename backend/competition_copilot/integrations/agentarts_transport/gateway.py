"""ExecuteRuntime HTTP forwarding. Credentials and gateway URL stay server-side."""

import http.client
import ipaddress
import json
import math
import re
from dataclasses import dataclass, field
from urllib.parse import urlencode, urlsplit

from competition_copilot.agents.contracts import AgentResponse
from competition_copilot.integrations.agentarts.contracts import (
    AgentArtsInvocationEnvelope,
    RuntimeError,
)

RUNTIME_NAME = re.compile(r"[a-z][a-z0-9-]{0,46}[a-z0-9]\Z")
SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class GatewayFailure(Exception):
    def __init__(self, code, status=502):
        super().__init__(code)  # Never retain upstream prose, headers or exceptions.
        self.code, self.status = code, status


def require(value):
    if not value:
        raise ValueError("INVALID_AGENTARTS_SERVER_CONFIG")


@dataclass(frozen=True)
class GatewayConfig:
    gateway_url: str
    runtime_name: str
    authorization: str = field(repr=False)
    endpoint: str | None = None
    gateway_user_id: str | None = None
    timeout: float = 15
    allow_loopback_http: bool = False  # Explicit test harness only; TLS otherwise.

    def __post_init__(self):
        try:
            require(isinstance(self.allow_loopback_http, bool))
            url = urlsplit(self.gateway_url)
            loopback = self.allow_loopback_http and ipaddress.ip_address(url.hostname).is_loopback if url.scheme == "http" else False
            require((url.scheme == "https" or loopback) and url.hostname)
            require(not (url.username or url.password or url.query or url.fragment))
            require(url.path in ("", "/") and url.port != 0)
            require(isinstance(self.runtime_name, str) and RUNTIME_NAME.fullmatch(self.runtime_name))
            require(isinstance(self.authorization, str) and self.authorization.startswith("Bearer "))
            require(self.authorization == self.authorization.strip() and 7 < len(self.authorization) <= 4096)
            require(all(32 <= ord(c) < 127 for c in self.authorization))
            require(self.endpoint is None or re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,46}[A-Za-z0-9]", self.endpoint))
            require(self.gateway_user_id is None or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.gateway_user_id))
            require(not isinstance(self.timeout, bool) and math.isfinite(self.timeout) and 0 < self.timeout <= 120)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("INVALID_AGENTARTS_SERVER_CONFIG") from None

    @property
    def invocation_path(self):
        path = f"/runtimes/{self.runtime_name}/invocations"
        return path + ("?" + urlencode({"endpoint": self.endpoint}) if self.endpoint else "")


def safe_delivery(value):
    """Fail closed before raw P12 GraphInput could leave the trusted boundary.

    This only guards the existing hosting projection; browser P14.1/P14.4 validators
    still validate the complete consumer contract. No new business result model.
    """
    invalid = {"runtime": None, "presentation": None}
    try:
        json.dumps(value, allow_nan=False)
        if not isinstance(value, dict) or set(value) - {"runtime", "presentation"}:
            return invalid
        runtime = value["runtime"]
        if not isinstance(runtime, dict) or set(runtime) - {"response", "error", "continuation_ref", "continuation"}:
            return invalid
        if runtime.get("continuation") is not None:
            return invalid
        if (runtime.get("response") is None) == (runtime.get("error") is None):
            return invalid
        if runtime.get("response") is not None:
            response = AgentResponse.model_validate(runtime["response"])
            pending = response.outcome in ("NEEDS_CLARIFICATION", "WAITING_FOR_APPROVAL")
            handle = runtime.get("continuation_ref")
            if (pending and not (isinstance(handle, str) and bool(handle.strip()))) or (not pending and handle is not None):
                return invalid
        else:
            error = RuntimeError.model_validate(runtime["error"])
            if runtime.get("continuation_ref") is not None:
                return invalid
            # Runtime errors are codes, never an upstream diagnostic/secret echo.
            return {"runtime": {"error": {"code": error.code.value, "message": error.code.value}}, "presentation": None}
        return value
    except (ValueError, TypeError, KeyError):
        return invalid


class AgentArtsGatewayClient:
    def __init__(self, config: GatewayConfig):
        self.config = config

    def invoke(self, payload, session_id):
        if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
            raise GatewayFailure("INVALID_AGENTARTS_SESSION", 400)
        try:
            AgentArtsInvocationEnvelope.model_validate(payload)
            body = json.dumps(payload, allow_nan=False).encode("utf-8")
        except (ValueError, TypeError):
            raise GatewayFailure("INVALID_RUNTIME_PAYLOAD", 400) from None
        config = self.config
        url = urlsplit(config.gateway_url)
        connection = (http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection)(
            url.hostname, url.port, timeout=config.timeout)
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   "Authorization": config.authorization, "X-Hw-Agentarts-Session-Id": session_id}
        if config.gateway_user_id:
            headers["X-Hw-Agentgateway-User-Id"] = config.gateway_user_id
        try:
            # Exactly one request; no redirects, environment proxy, retries or SDK IO.
            connection.request("POST", config.invocation_path, body=body, headers=headers)
            response = connection.getresponse()
            if response.status != 200:
                code = ("AGENTARTS_AUTH_ERROR" if response.status in (401, 403) else
                        "AGENTARTS_RUNTIME_NOT_FOUND" if response.status == 404 else
                        "AGENTARTS_SERVER_ERROR" if response.status >= 500 else "AGENTARTS_HTTP_ERROR")
                raise GatewayFailure(code)
            if response.getheader("Content-Type", "").split(";", 1)[0].strip() != "application/json":
                return {"runtime": None, "presentation": None}
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                return {"runtime": None, "presentation": None}
            try:
                return safe_delivery(json.loads(raw))
            except (ValueError, UnicodeError):
                return {"runtime": None, "presentation": None}
        except GatewayFailure:
            raise
        except TimeoutError:
            raise GatewayFailure("AGENTARTS_TIMEOUT", 504) from None
        except (OSError, http.client.HTTPException):
            raise GatewayFailure("AGENTARTS_NETWORK_ERROR") from None
        finally:
            connection.close()
