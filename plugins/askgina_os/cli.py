"""``hermes askgina-os``: connect Hermes to an askgina/os control plane over MCP.

The agent token is a secret. It is written only to the profile's ``.env`` (as
``MCP_ASKGINA_OS_API_KEY``); config.yaml holds the server URL and a
``Bearer ${MCP_ASKGINA_OS_API_KEY}`` template, never the token.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from . import client

_SUBCOMMAND_HELP = (
    ("connect", "Save the os URL and agent token, then check the connection"),
    ("status", "Show whether os is configured and reachable (never prints the token)"),
    ("disconnect", "Remove the os MCP server and its token"),
)


def _read_token(token_stdin: bool) -> str:
    if token_stdin or not sys.stdin.isatty():
        return sys.stdin.readline().strip()
    return getpass.getpass("  askgina/os agent token (input hidden): ").strip()


def _check(os_target: client.OsTarget) -> int:
    """Call whoami and summarize who Hermes is on os; 1 with a reason when that fails."""
    try:
        (me,) = client.call_tools(os_target, [("whoami", {})])
    except client.OsError as exc:
        print(f"  ✗ {exc}")
        return 1
    wallets = me.get("wallets") or []
    print(f"  ✓ Connected as agent '{me.get('agent', {}).get('name')}' "
          f"({len(wallets)} wallet(s), {len(me.get('mandates') or [])} live mandate(s))")
    for wallet in wallets:
        print(f"    wallet {wallet.get('address')}{'  (default)' if wallet.get('isDefault') else ''}")
    print(f"  Hermes calls the os tools as mcp__{client.SERVER_NAME}__<tool>.")
    print("  Restart the gateway (or start a new session) so running sessions pick the server up.")
    return 0


def cmd_connect(url: str, token_stdin: bool) -> int:
    try:
        base_url = client.normalize_base_url(url)
    except ValueError as exc:
        print(f"  ✗ {exc}")
        return 2
    token = client.strip_bearer(_read_token(token_stdin))
    if not token:
        print("  ✗ the agent token is empty")
        return 2
    client.save(base_url, token)
    print(f"  ✓ Saved askgina/os at {base_url} (token stored in this profile's .env)")
    return _check(client.OsTarget(base_url=base_url, token=token))


def cmd_status() -> int:
    base_url = client.configured_base_url()
    print(f"  Server: {base_url or 'not configured'}")
    print(f"  Agent token: {'set' if client.token_present() else 'missing'}")
    os_target = client.target()
    if os_target is None:
        print("  Run: hermes askgina-os connect")
        return 1
    return _check(os_target)


def cmd_disconnect() -> int:
    print("  ✓ Removed askgina/os" if client.remove() else "  askgina/os was not configured")
    return 0


def register_cli(subparser: argparse.ArgumentParser) -> None:
    """Build the ``hermes askgina-os`` argparse tree (called at plugin load time)."""
    subs = subparser.add_subparsers(dest="askgina_os_command")
    p = {name: subs.add_parser(name, help=help_) for name, help_ in _SUBCOMMAND_HELP}
    p["connect"].add_argument("--url", default=client.DEFAULT_BASE_URL,
                              help=f"os control-plane base URL (default {client.DEFAULT_BASE_URL})")
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
