"""``hermes askgina-os``: connect Hermes to an askgina/os control plane over MCP.

The agent token is a secret. It is written only to the profile's ``.env`` (as
``MCP_ASKGINA_OS_API_KEY``, the same convention ``hermes mcp add --auth header`` uses); config.yaml
holds the server URL and a ``Bearer ${MCP_ASKGINA_OS_API_KEY}`` template, never the token.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from typing import Optional
from urllib.parse import urlsplit

SERVER_NAME = "askgina_os"
DEFAULT_BASE_URL = "http://localhost:8080"

_SUBCOMMAND_HELP = (
    ("connect", "Save the os URL and agent token, then check the connection"),
    ("status", "Show whether os is configured and reachable (never prints the token)"),
    ("disconnect", "Remove the os MCP server and its token"),
)


def _is_loopback(host: str) -> bool:
    import ipaddress

    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def normalize_base_url(raw: str) -> str:
    """Return ``scheme://host[:port]`` for an os base URL with no path, query or fragment.

    The MCP endpoint is always ``<base>/mcp``; accepting a path here would let a typo point Hermes
    at the confirmation page or some other route. The agent token travels in a header, so plain
    http is allowed only to this machine (loopback); anything else must be https.
    """
    value = (raw or "").strip().rstrip("/")
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("the os URL must start with http:// or https:// and name a host")
    if parts.path or parts.query or parts.fragment:
        raise ValueError("give the os base URL only (e.g. http://localhost:8080), without a path")
    if parts.username or parts.password:
        raise ValueError("the os URL must not contain credentials")
    if parts.scheme == "http" and not _is_loopback(parts.hostname):
        raise ValueError("use https:// for a remote os; plain http is allowed only for localhost")
    return f"{parts.scheme}://{parts.netloc}"


def server_config(base_url: str) -> dict:
    from hermes_cli.mcp_config import _bearer_auth_headers

    return {"url": f"{base_url}/mcp", "headers": _bearer_auth_headers(SERVER_NAME)}


def _read_token(token_stdin: bool) -> str:
    if token_stdin or not sys.stdin.isatty():
        return sys.stdin.readline().strip()
    return getpass.getpass("  askgina/os agent token (input hidden): ").strip()


def _probe() -> Optional[list[tuple[str, str]]]:
    """List the server's tools through Hermes's own MCP probe; None (with a message) on failure."""
    from hermes_cli.mcp_config import _error, _get_mcp_servers, _probe_single_server, redact_mcp_probe_text

    config = _get_mcp_servers().get(SERVER_NAME)
    if config is None:
        _error("askgina/os is not configured. Run: hermes askgina-os connect")
        return None
    try:
        return _probe_single_server(SERVER_NAME, config, connect_timeout=15)
    except Exception as exc:  # the probe raises transport/auth errors of many types
        _error(f"Could not reach askgina/os: {redact_mcp_probe_text(exc)}")
        return None


def _report(tools: list[tuple[str, str]]) -> None:
    from hermes_cli.mcp_config import _info, _success

    names = sorted(name for name, _ in tools)
    _success(f"Connected: {len(names)} tool(s) ({', '.join(names)})")
    _info(f"Hermes calls them as mcp__{SERVER_NAME}__<tool>, e.g. mcp__{SERVER_NAME}__propose_transfer.")
    _info("Restart the gateway (or start a new session) so running sessions pick the server up.")


def cmd_connect(url: str, token_stdin: bool) -> int:
    from hermes_cli.mcp_config import _error, _save_bearer_auth_token, _save_mcp_server, _success

    try:
        base_url = normalize_base_url(url)
    except ValueError as exc:
        _error(str(exc))
        return 2
    token = _read_token(token_stdin)
    try:
        _save_bearer_auth_token(SERVER_NAME, token)
    except ValueError as exc:
        _error(str(exc))
        return 2
    if not _save_mcp_server(SERVER_NAME, server_config(base_url)):
        return 1
    _success(f"Saved askgina/os at {base_url} (token stored in this profile's .env)")
    tools = _probe()
    if tools is None:
        return 1
    _report(tools)
    return 0


def cmd_status() -> int:
    from hermes_cli.config import get_env_value
    from hermes_cli.mcp_config import _env_key_for_server, _get_mcp_servers, _info, _warning

    config = _get_mcp_servers().get(SERVER_NAME)
    token_set = bool(get_env_value(_env_key_for_server(SERVER_NAME)))
    _info(f"Server: {config['url'] if config else 'not configured'}")
    _info(f"Agent token: {'set' if token_set else 'missing'}")
    if not config or not token_set:
        _warning("Run: hermes askgina-os connect")
        return 1
    tools = _probe()
    if tools is None:
        return 1
    _report(tools)
    return 0


def cmd_disconnect() -> int:
    from hermes_cli.config import remove_env_value
    from hermes_cli.mcp_config import _env_key_for_server, _remove_mcp_server, _success

    removed_server = _remove_mcp_server(SERVER_NAME)
    removed_token = remove_env_value(_env_key_for_server(SERVER_NAME))
    _success("Removed askgina/os" if removed_server or removed_token else "askgina/os was not configured")
    return 0


def register_cli(subparser: argparse.ArgumentParser) -> None:
    """Build the ``hermes askgina-os`` argparse tree (called at plugin load time)."""
    subs = subparser.add_subparsers(dest="askgina_os_command")
    p = {name: subs.add_parser(name, help=help_) for name, help_ in _SUBCOMMAND_HELP}
    p["connect"].add_argument("--url", default=DEFAULT_BASE_URL,
                              help=f"os control-plane base URL (default {DEFAULT_BASE_URL})")
    p["connect"].add_argument("--token-stdin", action="store_true",
                              help="read the agent token from stdin instead of a hidden prompt")
    subparser.set_defaults(func=askgina_os_command)


def askgina_os_command(args: argparse.Namespace) -> int:
    command = getattr(args, "askgina_os_command", None)
    if command == "connect":
        return cmd_connect(args.url, args.token_stdin)
    if command == "status":
        return cmd_status()
    if command == "disconnect":
        return cmd_disconnect()
    print("usage: hermes askgina-os {connect,status,disconnect}")
    return 2
