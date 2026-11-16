"""askgina_os plugin: the os agent token stays in .env, the URL rules keep it off plaintext links,
and the Wallet panel's summary never carries the token."""

from __future__ import annotations

import importlib.util
import io
import stat
import sys
from pathlib import Path

import pytest

from hermes_cli.config import get_config_path, get_env_path, get_env_value, load_config, read_raw_config
from plugins.askgina_os import cli, client

TOKEN = "os_agent_token_for_tests_0123456789"
WHOAMI = {"agent": {"name": "Hermes"}, "workspaceId": "wsp_1",
          "wallets": [{"walletId": "wal_1", "address": "0xabc", "isDefault": True}], "mandates": []}


@pytest.fixture
def fake_os(monkeypatch):
    """The checks dial the server; these tests cover what is saved, not the network."""
    calls = []

    def fake(os_target, requested, **_):
        calls.append((os_target, requested))
        return [WHOAMI for _ in requested]

    monkeypatch.setattr(client, "call_tools", fake)
    return calls


def _router():
    path = Path(__file__).resolve().parents[2] / "plugins" / "askgina_os" / "dashboard" / "plugin_api.py"
    spec = importlib.util.spec_from_file_location("_askgina_os_plugin_api_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
    assert client.normalize_base_url(raw) == expected


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
        client.normalize_base_url(raw)


def test_connect_keeps_the_token_out_of_config(monkeypatch, fake_os):
    monkeypatch.setattr("sys.stdin", io.StringIO(f"Bearer {TOKEN}\n"))

    assert cli.cmd_connect("http://localhost:8080", token_stdin=True) == 0

    # read_raw_config: load_config() expands ${...}; what matters is what reaches the disk.
    server = read_raw_config()["mcp_servers"]["askgina_os"]
    assert server["url"] == "http://localhost:8080/mcp"
    assert server["headers"] == {"Authorization": "Bearer ${MCP_ASKGINA_OS_API_KEY}"}
    assert TOKEN not in get_config_path().read_text()
    assert get_env_value("MCP_ASKGINA_OS_API_KEY") == TOKEN  # "Bearer " prefix stripped
    assert stat.S_IMODE(get_env_path().stat().st_mode) & 0o077 == 0
    # The check dials the configured server with the clean token.
    assert fake_os[0][0] == client.OsTarget(base_url="http://localhost:8080", token=TOKEN)


def test_connect_refuses_a_remote_http_url_before_saving_anything(monkeypatch, fake_os):
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{TOKEN}\n"))

    assert cli.cmd_connect("http://os.example.com", token_stdin=True) == 2

    assert "askgina_os" not in (load_config().get("mcp_servers") or {})
    assert not get_env_value("MCP_ASKGINA_OS_API_KEY")
    assert fake_os == []


def test_connect_refuses_an_empty_token(monkeypatch, fake_os):
    monkeypatch.setattr("sys.stdin", io.StringIO("Bearer \n"))

    assert cli.cmd_connect("http://localhost:8080", token_stdin=True) == 2
    assert "askgina_os" not in (load_config().get("mcp_servers") or {})


def test_status_never_prints_the_token(monkeypatch, capsys, fake_os):
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{TOKEN}\n"))
    cli.cmd_connect("http://localhost:8080", token_stdin=True)
    capsys.readouterr()

    assert cli.cmd_status() == 0
    out = capsys.readouterr().out
    assert TOKEN not in out
    assert "Agent token: set" in out


def test_disconnect_removes_server_and_token(monkeypatch, fake_os):
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{TOKEN}\n"))
    cli.cmd_connect("http://localhost:8080", token_stdin=True)

    assert cli.cmd_disconnect() == 0

    assert "askgina_os" not in (load_config().get("mcp_servers") or {})
    assert not get_env_value("MCP_ASKGINA_OS_API_KEY")


def test_wallet_summary_formats_amounts_and_links_only_pending_person_approvals():
    router = _router()
    me = {
        **WHOAMI,
        "wallets": [{"walletId": "wal_1", "address": "0xabc", "isDefault": True, "policy": {
            "limits": [{"chainId": "eip155:31337", "asset": "native",
                        "maxPerTx": "10000000000000000", "maxPerDay": "50000000000000000"}],
            "recipients": {"mode": "allowlist", "addresses": ["0x1", "0x2"]}, "approvalsNeeded": 1}}],
        "mandates": [{"mandateId": "mnd_1", "purpose": "invoices", "recipients": ["0x1"], "usesLeft": 4,
                      "notAfter": 1, "assets": [{"chainId": "eip155:31337", "asset": "native",
                                                  "maxPerAction": "20000000000000000",
                                                  "maxTotal": "100000000000000000",
                                                  "usedTotal": "20000000000000000"}]}],
    }
    balances = {"balances": [{"chainId": "eip155:31337", "asset": "native", "symbol": "ETH",
                              "decimals": 18, "amount": "1000000000000000000"}]}
    intents = {"intents": [
        {"intentId": "int_wait", "status": "pending_approval", "authorizedBy": "person", "amount": "0.01"},
        {"intentId": "int_mandate", "status": "approved", "authorizedBy": "mandate", "amount": "0.02"},
        {"intentId": "int_done", "status": "confirmed", "authorizedBy": "person", "amount": "0.01"},
    ]}

    view = router.summarize(me, balances, intents, "http://localhost:8080")

    assert view["balances"] == [{"chainId": "eip155:31337", "symbol": "ETH", "amount": "1"}]
    assert view["wallets"][0]["limits"] == [
        {"chainId": "eip155:31337", "symbol": "ETH", "perPayment": "0.01", "perDay": "0.05"}]
    assert view["wallets"][0]["recipients"] == "2 allowed address(es)"
    assert view["mandates"][0]["assets"] == [
        {"symbol": "ETH", "perPayment": "0.02", "total": "0.1", "usedTotal": "0.02"}]
    assert [p["intentId"] for p in view["pending"]] == ["int_wait"]
    assert view["pending"][0]["approvalPage"] == "http://localhost:8080/w/wsp_1/approvals/int_wait"
    assert [r["intentId"] for r in view["recent"]] == ["int_mandate", "int_done"]
    assert all("approvalPage" not in r for r in view["recent"])
