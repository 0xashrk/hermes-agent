"""Wallet panel backend, mounted at /api/plugins/askgina_os/.

``GET /overview``: who Hermes is on askgina/os, its wallet, balances and limits, live mandates,
payments waiting for a person, and recent payments. It calls os over MCP with the agent token,
which it reads server-side and never returns: the Desktop panel only ever sees this summary and
the control-plane page of each pending request, which it opens in the system browser.

``POST /pair/start``, ``/pair/poll``, ``/pair/cancel``: connect with no token to copy. os shows
the person the same code the panel shows; once they allow it, the poll collects the token and
saves it like ``hermes askgina-os connect``. The poll secret and the token stay in this process.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


def _load_client():
    # This file is imported by path, outside the plugin package, so load the sibling module the
    # same way under a private name.
    name = "_askgina_os_wallet_client"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent.parent / "client.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


client = _load_client()

WAITING = {"proposed", "pending_approval"}


def _units(base_units: Any, decimals: int) -> str:
    """Base units to a readable amount, trailing zeros trimmed (e.g. 50000000000000000 -> 0.05)."""
    try:
        value = Decimal(int(str(base_units))) / (Decimal(10) ** decimals)
    except (ValueError, TypeError):
        return str(base_units)
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def summarize(me: dict, balances: dict, intents: dict, base_url: str) -> dict:
    """Shape the three os answers into the panel's view model (pure; covered by tests)."""
    tokens = {(b["chainId"], b["asset"]): b for b in balances.get("balances") or []}

    def meta(chain_id: str, asset: str) -> tuple[str, int]:
        known = tokens.get((chain_id, asset))
        if known:
            return known.get("symbol") or asset, int(known.get("decimals") or 18)
        return ("native" if asset == "native" else asset), 18

    wallets = []
    for wallet in me.get("wallets") or []:
        policy = wallet.get("policy") or {}
        limits = []
        for limit in policy.get("limits") or []:
            symbol, decimals = meta(limit["chainId"], limit["asset"])
            limits.append({"chainId": limit["chainId"], "symbol": symbol,
                           "perPayment": _units(limit.get("maxPerTx"), decimals),
                           "perDay": _units(limit.get("maxPerDay"), decimals)})
        recipients = policy.get("recipients") or {}
        wallets.append({
            "walletId": wallet.get("walletId"), "address": wallet.get("address"),
            "label": wallet.get("label"), "isDefault": bool(wallet.get("isDefault")),
            "hasPolicy": bool(policy), "approvalsNeeded": policy.get("approvalsNeeded"),
            "limits": limits,
            "recipients": "any address" if recipients.get("mode") == "any"
            else f"{len(recipients.get('addresses') or [])} allowed address(es)" if recipients else None,
        })

    mandates = []
    for mandate in me.get("mandates") or []:
        assets = []
        for limit in mandate.get("assets") or []:
            symbol, decimals = meta(limit["chainId"], limit["asset"])
            assets.append({"symbol": symbol,
                           "perPayment": _units(limit.get("maxPerAction"), decimals),
                           "total": _units(limit.get("maxTotal"), decimals),
                           "usedTotal": _units(limit.get("usedTotal"), decimals)})
        mandates.append({"mandateId": mandate.get("mandateId"), "purpose": mandate.get("purpose"),
                         "recipients": mandate.get("recipients") or [], "usesLeft": mandate.get("usesLeft"),
                         "notAfter": mandate.get("notAfter"), "assets": assets})

    workspace_id = me.get("workspaceId")
    pending, recent = [], []
    for intent in intents.get("intents") or []:
        row = {key: intent.get(key) for key in (
            "intentId", "status", "title", "amount", "asset", "to", "memo", "createdAt",
            "authorizedBy", "explorerUrl", "failureCode")}
        if intent.get("status") in WAITING and intent.get("authorizedBy") == "person" and workspace_id:
            row["approvalPage"] = client.approval_page(base_url, workspace_id, intent["intentId"])
            pending.append(row)
        else:
            recent.append(row)

    return {
        "configured": True,
        "baseUrl": base_url,
        "agent": {"name": (me.get("agent") or {}).get("name")},
        "wallets": wallets,
        "balances": [{"chainId": b.get("chainId"), "symbol": b.get("symbol") or b.get("asset"),
                      "amount": _units(b.get("amount"), int(b.get("decimals") or 18))}
                     for b in balances.get("balances") or []],
        "mandates": mandates,
        "pending": pending,
        "recent": recent[:10],
    }


@router.get("/overview")
async def overview() -> dict:
    from agent.secret_scope import UnscopedSecretError

    try:
        os_target = client.target()
    except UnscopedSecretError as exc:  # multiplexed gateway with no profile scope: fail closed
        return {"configured": False, "baseUrl": client.configured_base_url(), "error": str(exc)}
    if os_target is None:
        return {"configured": False, "baseUrl": client.configured_base_url(),
                "tokenSet": client.token_present()}
    try:
        me, balances, intents = await client.call_tools_async(
            os_target, [("whoami", {}), ("get_balances", {}), ("list_intents", {"limit": 20})])
    except client.OsError as exc:
        return {"configured": True, "baseUrl": os_target.base_url, "error": str(exc)}
    return summarize(me or {}, balances or {}, intents or {}, os_target.base_url)


# --- pairing --------------------------------------------------------------------------------------

# One pairing in flight per profile (keyed by its config.yaml). Sync routes run in FastAPI's thread
# pool, so the lock guards the map.
_pairings: dict[str, Any] = {}
_pairings_lock = threading.Lock()


def _profile_key() -> str:
    from hermes_cli.config import get_config_path

    return str(get_config_path())


class PairStart(BaseModel):
    baseUrl: Optional[str] = None


@router.post("/pair/start")
def pair_start(body: PairStart) -> dict:
    try:
        base_url = client.normalize_base_url(body.baseUrl or client.DEFAULT_BASE_URL)
        pairing = client.start_pairing(base_url)
    except (ValueError, client.OsError) as exc:
        return {"status": "error", "error": str(exc)}
    with _pairings_lock:
        _pairings[_profile_key()] = pairing
    return {
        "status": "pending",
        "userCode": pairing.user_code,
        "verificationUrl": pairing.verification_url,
        "expiresAt": pairing.expires_at,
    }


@router.post("/pair/poll")
def pair_poll() -> dict:
    key = _profile_key()
    with _pairings_lock:
        pairing = _pairings.get(key)
    if pairing is None:
        return {"status": "none"}
    try:
        status = client.poll_pairing(pairing)
    except client.OsError as exc:
        return {"status": "error", "error": str(exc)}
    if status != "pending":
        with _pairings_lock:
            if _pairings.get(key) is pairing:
                del _pairings[key]
    return {"status": status}


@router.post("/pair/cancel")
def pair_cancel() -> dict:
    with _pairings_lock:
        _pairings.pop(_profile_key(), None)
    return {}
