"""Offline real-integration fixtures, with immutable official data checks."""

import asyncio
import hashlib
import socket
from pathlib import Path

import pytest
from anyio import fail_after

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def run(monkeypatch):
    def hashes():
        return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (ROOT / "data").rglob("*") if p.is_file()}

    before = hashes()
    runner = asyncio.Runner()
    runner.get_loop()  # Windows loop wakeup, before denying sockets.

    def reject(*args, **kwargs):
        pytest.fail("Real MCP integration must not access network or listeners")

    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "bind", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)

    def execute(operation):
        async def bounded():
            with fail_after(30):
                return await operation()
        return runner.run(bounded())

    with runner:
        yield execute
    assert hashes() == before, "Integration changed official seed/policy/requirements data"
