"""Ensamblado: configuración + cliente + MCP + equipo."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from .agents.team import Team
from .config import Config
from .llm import AnthropicBackend
from .tools.confirm import ConfirmGate
from .tools.mcp_bridge import McpHub


@asynccontextmanager
async def build_team(cfg: Config, backend: Any | None = None) -> AsyncIterator[tuple[Team, ConfirmGate, McpHub]]:
    gate = ConfirmGate()
    hub = McpHub(cfg.mcp_servers, confirm=gate)
    await hub.start()
    team = Team(cfg, backend or AnthropicBackend(fallbacks=cfg.models.fallbacks), extra_leader_tools=hub.registry)
    try:
        yield team, gate, hub
    finally:
        await hub.close()
