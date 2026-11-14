# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the ODPi Egeria project.
"""The MCP server's startup sync writes a SHARED spec cache (spec-cache identity ruling, item 1): every MCP
caller reads the tier, so it may hold only specs everyone can read; a shared sync skips zoned specs."""
import pytest

from pyegeria.core import mcp_server
from pyegeria.view import egeria_spec_cache as esc

pytestmark = pytest.mark.unit


def test_startup_sync_is_shared(monkeypatch):
    calls = []

    class Report:
        def render(self):
            return "ok"

    def fake_sync(client, **kwargs):
        calls.append((client, kwargs))
        return Report()
    monkeypatch.setattr(esc, "sync_report_specs", fake_sync)
    mcp_server._startup_sync("client")
    assert calls == [("client", {"shared": True})]


def test_a_failed_startup_sync_never_stops_the_server(monkeypatch):
    def boom(client, **kwargs):
        raise RuntimeError("Egeria down")
    monkeypatch.setattr(esc, "sync_report_specs", boom)
    mcp_server._startup_sync("client")   # logs a warning, raises nothing
