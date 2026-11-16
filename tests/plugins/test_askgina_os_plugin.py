"""askgina_os plugin: the os agent token stays in .env, the URL rules keep it off plaintext links."""

from __future__ import annotations

import io
import stat

import pytest

from hermes_cli.config import get_config_path, get_env_path, get_env_value, load_config, read_raw_config
from plugins.askgina_os import cli

TOKEN = "os_agent_token_for_tests_0123456789"


@pytest.fixture
def no_probe(monkeypatch):
    """The probe dials the server; these tests cover what is saved, not the network."""
    monkeypatch.setattr(cli, "_probe", lambda: [("whoami", ""), ("propose_transfer", "")])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://localhost:8080", "http://localhost:8080"),
        ("http://localhost:8080/", "http://localhost:8080"),
        ("http://127.0.0.1:8080", "http://127.0.0.1:8080"),
        ("http://[::1]:8080", "http://[::1]:8080"),
        ("https://os.example.com", "https://os.example.com"),
    ],
)
def test_base_url_accepts_loopback_http_and_any_https(raw, expected):
    assert cli.normalize_base_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "http://example.com",  # the bearer token would cross the network in plaintext
        "http://10.0.0.5:8080",
        "ftp://localhost:8080",
        "localhost:8080",
        "http://localhost:8080/mcp",  # a path could point Hermes at another route
        "https://os.example.com/?x=1",
        "https://user:pass@os.example.com",
        "",
    ],
)
def test_base_url_rejects_unsafe_or_ambiguous_urls(raw):
    with pytest.raises(ValueError):
        cli.normalize_base_url(raw)


def test_connect_keeps_the_token_out_of_config(monkeypatch, no_probe):
    monkeypatch.setattr("sys.stdin", io.StringIO(f"Bearer {TOKEN}\n"))

    assert cli.cmd_connect("http://localhost:8080", token_stdin=True) == 0
    # read_raw_config: load_config() expands ${...}; what matters is what reaches the disk.
    server = read_raw_config()["mcp_servers"]["askgina_os"]
    assert server["url"] == "http://localhost:8080/mcp"
    assert server["headers"] == {"Authorization": "Bearer ${MCP_ASKGINA_OS_API_KEY}"}
    assert TOKEN not in get_config_path().read_text()
    assert get_env_value("MCP_ASKGINA_OS_API_KEY") == TOKEN  # "Bearer " prefix stripped
    assert stat.S_IMODE(get_env_path().stat().st_mode) & 0o077 == 0


def test_connect_refuses_a_remote_http_url_before_saving_anything(monkeypatch, no_probe):
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{TOKEN}\n"))

    assert cli.cmd_connect("http://os.example.com", token_stdin=True) == 2

    assert "askgina_os" not in (load_config().get("mcp_servers") or {})
    assert not get_env_value("MCP_ASKGINA_OS_API_KEY")


def test_connect_refuses_an_empty_token(monkeypatch, no_probe):
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))

    assert cli.cmd_connect("http://localhost:8080", token_stdin=True) == 2
    assert "askgina_os" not in (load_config().get("mcp_servers") or {})


def test_status_never_prints_the_token(monkeypatch, capsys, no_probe):
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{TOKEN}\n"))
    cli.cmd_connect("http://localhost:8080", token_stdin=True)
    capsys.readouterr()

    assert cli.cmd_status() == 0
    out = capsys.readouterr().out
    assert TOKEN not in out
    assert "Agent token: set" in out


def test_disconnect_removes_server_and_token(monkeypatch, no_probe):
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{TOKEN}\n"))
    cli.cmd_connect("http://localhost:8080", token_stdin=True)

    assert cli.cmd_disconnect() == 0

    assert "askgina_os" not in (load_config().get("mcp_servers") or {})
    assert not get_env_value("MCP_ASKGINA_OS_API_KEY")
