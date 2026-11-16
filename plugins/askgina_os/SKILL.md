---
name: payments
description: Propose payments through askgina/os; a person approves.
version: 0.1.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [payments, wallet, crypto, askgina-os, approvals]
---

# Payments through askgina/os

Use this when the user asks to pay, send, transfer or tip, or asks what wallet, balance, limits or
pre-approved budgets (mandates) you have.

You cannot sign anything. askgina/os holds the wallet keys in a separate signer. You **propose**;
the signer checks the wallet's policy and then needs either a person's passkey approval on the
signer's own confirmation page, or a mandate a person approved in advance. Never ask anyone for a
private key, seed phrase or passkey.

The tools come from the `askgina_os` MCP server. Hermes exposes them as
`mcp__askgina_os__<tool>`. If they are missing, tell the user to open **Wallet** in Hermes and
press **Connect wallet** (or run `hermes askgina-os connect`), then start a new session: a session
that was already open does not see tools added after it started.

## Flow

1. **Know your limits first.** Call `mcp__askgina_os__whoami` (your wallets, chains, per-transaction
   and daily limits, live mandates and what is left of them) and, when amounts matter,
   `mcp__askgina_os__get_balances`.
2. **Propose exactly what the user asked.** Call `mcp__askgina_os__propose_transfer` with `chainId`,
   `to` (the full address), `amount` (whole units, e.g. `"0.01"`), `asset` (`"native"` or the token
   contract) and a short `memo` saying why. Never round, guess or change the recipient, amount,
   asset or chain. If the user named a contact rather than an address, ask for the address.
3. **Read `authorizedBy` in the answer.**
   - `"person"`: nothing is sent yet. Give the user the `approvalUrl` and say: open it in your
     browser, check the address bar shows the os confirmation host, read the payment there (it is
     built from the signer's own records, not from this chat) and approve it with your passkey
     before `expiresAt`.
   - `"mandate"`: it was signed with no person asked, under the named `mandateId`. Say so.
4. **Follow it to a result.** Call `mcp__askgina_os__get_intent` with the `intentId` and
   `waitSeconds` (up to 50), repeating until the status is final: `confirmed`, `reverted`, `stuck`,
   `rejected`, `expired`, `cancelled`, `denied`, `failed` or `voided`. Report the status and the
   explorer link. `stuck` is not a failure: the server raises the fee itself, and only people can
   speed it up or cancel it.

## Refusals are final

A `policy_denied` error (for example `over_daily_cap`, `recipient_not_allowed`,
`asset_not_allowed`, `chain_not_allowed`, `mandate_over_window_cap`, `mandate_expired`) means the
signer refused and nothing was recorded. Explain the code in plain words and stop. Do **not** retry
with a smaller amount, a different recipient, another chain or another wallet to get around it, and
never split a payment into parts to fit under a cap. Only the people who manage the wallet can
change its limits, on the os control plane.

## Other tools

- `mcp__askgina_os__list_intents`: your recent proposals and their status.
- `mcp__askgina_os__cancel_intent`: withdraw a proposal no one has approved yet.
- `mcp__askgina_os__propose_contract_call` and `mcp__askgina_os__propose_order` follow the same
  propose, approve, follow flow. A person always approves an order.
