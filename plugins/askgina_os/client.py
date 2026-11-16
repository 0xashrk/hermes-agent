"""The askgina_os plugin's one door to askgina/os: config, the agent token and MCP tool calls.

Shared by the ``hermes askgina-os`` CLI and the Wallet panel's backend router, so the token is
read in exactly one place and never leaves this process. Uses only the published plugin API
(``hermes_cli.config``, ``agent.redact``) and the MCP SDK.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlsplit

SERVER_NAME = "askgina_os"
# The `hermes mcp add --auth header` convention: MCP_<SERVER>_API_KEY in the profile's .env.
TOKEN_ENV = "MCP_ASKGINA_OS_API_KEY"
DEFAULT_BASE_URL = "http://localhost:8080"


class OsError(Exception):
    """askgina/os could not be reached, refused the token, or answered with a tool error."""


@dataclass(frozen=True)
class OsTarget:
    base_url: str
    token: str

    @property
    def mcp_url(self) -> str:
        return f"{self.base_url}/mcp"


def _is_loopback(host: str) -> bool:
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


def server_entry(base_url: str) -> dict:
    """The mcp_servers entry: the URL and a header template; the token stays in .env."""
    return {"url": f"{base_url}/mcp", "headers": {"Authorization": f"Bearer ${{{TOKEN_ENV}}}"}}


def strip_bearer(token: str) -> str:
    """The bare token: a pasted ``Bearer `` prefix is dropped, and ``Bearer`` alone is no token."""
    value = (token or "").strip()
    if value.lower() == "bearer":
        return ""
    return value[7:].strip() if value[:7].lower() == "bearer " else value


def configured_base_url() -> Optional[str]:
    from hermes_cli.config import read_raw_config

    entry = (read_raw_config().get("mcp_servers") or {}).get(SERVER_NAME)
    url = entry.get("url") if isinstance(entry, dict) else None
    if not isinstance(url, str) or not url.endswith("/mcp"):
        return None
    return url[: -len("/mcp")]


def _token() -> Optional[str]:
    """The agent token for the ACTIVE profile. ``agent.secret_scope`` keeps a multiplexed gateway
    from reading another profile's token and raises ``UnscopedSecretError`` (fail closed) when no
    scope is installed there; callers let that propagate."""
    from agent.secret_scope import get_secret

    return get_secret(TOKEN_ENV)


def token_present() -> bool:
    return bool(_token())


def target() -> Optional[OsTarget]:
    """The configured os, or None when the server entry or the token is missing."""
    base_url = configured_base_url()
    token = _token()
    if not base_url or not token:
        return None
    return OsTarget(base_url=base_url, token=token)


def save(base_url: str, token: str) -> None:
    """Store the token in .env and the server entry (URL + header template) in config.yaml."""
    from hermes_cli.config import load_config, save_config, save_env_value

    clean = strip_bearer(token)
    if not clean:
        raise ValueError("the agent token is empty")
    save_env_value(TOKEN_ENV, clean)
    config = load_config()
    config.setdefault("mcp_servers", {})[SERVER_NAME] = server_entry(base_url)
    save_config(config)


def remove() -> bool:
    """Drop the server entry and the token; True when anything was there."""
    from hermes_cli.config import load_config, remove_env_value, save_config

    config = load_config()
    servers = config.get("mcp_servers") or {}
    had_server = servers.pop(SERVER_NAME, None) is not None
    if had_server:
        if servers:
            config["mcp_servers"] = servers
        else:
            config.pop("mcp_servers", None)
        save_config(config)
    had_token = remove_env_value(TOKEN_ENV)
    return had_server or bool(had_token)


def _redact(text: str, token: str) -> str:
    from agent.redact import redact_sensitive_text

    return redact_sensitive_text(text.replace(token, "***") if token else text, force=True)


async def call_tools_async(os_target: OsTarget, calls: list[tuple[str, dict]], *, timeout: float = 15) -> list[Any]:
    """Call os MCP tools in one session; return each result's JSON. Raises OsError."""
    from mcp import ClientSession
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

    async def run() -> list[Any]:
        headers = {"Authorization": f"Bearer {os_target.token}"}
        async with create_mcp_http_client(headers=headers) as http:
            async with streamable_http_client(os_target.mcp_url, http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    results = []
                    for name, arguments in calls:
                        answer = await session.call_tool(name, arguments)
                        text = "".join(getattr(part, "text", "") for part in answer.content)
                        if answer.isError:
                            raise OsError(f"{name}: {text or 'error'}")
                        results.append(json.loads(text) if text else None)
                    return results

    try:
        return await asyncio.wait_for(run(), timeout)
    except OsError as exc:
        raise OsError(_redact(str(exc), os_target.token)) from None
    except BaseException as exc:  # transport errors arrive wrapped in exception groups of many types
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise OsError(_redact(f"could not reach askgina/os: {_first_cause(exc)}", os_target.token)) from None


def _first_cause(exc: BaseException) -> str:
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


def call_tools(os_target: OsTarget, calls: list[tuple[str, dict]], *, timeout: float = 15) -> list[Any]:
    return asyncio.run(call_tools_async(os_target, calls, timeout=timeout))


def approval_page(base_url: str, workspace_id: str, intent_id: str) -> str:
    """The control plane's page for one pending request; it links on to the signer's own page."""
    return f"{base_url}/w/{workspace_id}/approvals/{intent_id}"
