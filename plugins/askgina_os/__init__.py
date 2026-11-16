"""askgina_os plugin: pay through askgina/os without ever holding a key.

askgina/os is a self-hosted signer. Hermes reaches it as the MCP server ``askgina_os`` and can only
propose: the signer checks the wallet's policy and, for each payment, either a person's passkey
approval on the signer's own confirmation page or a mandate a person granted in advance. This
plugin adds ``hermes askgina-os connect|status|disconnect`` and a skill that teaches the agent that
flow. It adds no tools of its own: the tools are the os MCP server's.
"""

from __future__ import annotations

from pathlib import Path

from .cli import askgina_os_command, register_cli

_SKILL = Path(__file__).with_name("SKILL.md")


def register(ctx) -> None:
    """Register the CLI command group and the payments skill (called once by the plugin loader)."""
    ctx.register_cli_command(
        name="askgina-os", help="Pay through askgina/os (connect, status, disconnect)",
        setup_fn=register_cli, handler_fn=askgina_os_command,
        description=("Connect Hermes to an askgina/os signer over MCP. Hermes proposes payments; "
                     "a person approves each with a passkey, or a mandate they granted covers it."))
    ctx.register_skill("payments", _SKILL,
                       description="Propose payments through askgina/os and follow them to a result.")
