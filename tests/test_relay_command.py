from pathlib import Path

import pytest
from click.testing import CliRunner

import fastmcp.client.transports
import fastmcp.server.server
import windows_mcp.__main__ as cli
from windows_mcp.__main__ import main


class _FakeProxy:
    def __init__(self, calls: dict) -> None:
        self._calls = calls

    def run(self, **kwargs) -> None:
        self._calls["run"] = kwargs


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict:
    calls: dict = {}
    monkeypatch.setattr(cli, "CONFIG_FILE", tmp_path / "config.toml")

    def fake_transport(url, headers=None):
        calls["url"] = url
        calls["headers"] = headers
        return "backend"

    def fake_create_proxy(backend, **settings):
        calls["backend"] = backend
        return _FakeProxy(calls)

    monkeypatch.setattr(fastmcp.client.transports, "StreamableHttpTransport", fake_transport)
    monkeypatch.setattr(fastmcp.server.server, "create_proxy", fake_create_proxy)
    return calls


def test_relay_sends_the_saved_key_to_the_local_server(calls: dict) -> None:
    cli.CONFIG_FILE.write_text('[server]\nauth_key = "tok"\n', encoding="utf-8")

    result = CliRunner().invoke(main, ["relay", "--port", "8123"])

    assert result.exit_code == 0, result.output
    assert calls["url"] == "http://127.0.0.1:8123/mcp"
    assert calls["headers"] == {"Authorization": "Bearer tok"}
    assert calls["backend"] == "backend"
    assert calls["run"] == {"transport": "stdio", "show_banner": False}


def test_relay_without_a_config_sends_no_key(calls: dict) -> None:
    result = CliRunner().invoke(main, ["relay"])

    assert result.exit_code == 0, result.output
    assert calls["url"] == "http://127.0.0.1:8000/mcp"
    assert calls["headers"] == {}
