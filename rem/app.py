"""Ensamblado: configuración + cliente + MCP + equipo."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from .agents.team import Team
from .config import Config, ModelConfig
from .backends.openai_compat import OpenAICompatBackend
from .llm import AnthropicBackend
from .tools.confirm import ConfirmGate
from .tools.mcp_bridge import McpHub


def make_backend(m: ModelConfig) -> Any:
    if m.provider in ("ollama", "openai_compat"):
        return OpenAICompatBackend(m.base_url, m.api_key_env, m.timeout, m.temperature, m.max_tokens)
    if m.provider == "anthropic":  # de pago: solo si lo eliges explícitamente
        return AnthropicBackend(fallbacks=m.fallbacks)
    raise ValueError(f"Proveedor de modelos desconocido: {m.provider}")


@asynccontextmanager
async def build_team(cfg: Config, backend: Any | None = None) -> AsyncIterator[tuple[Team, ConfirmGate, McpHub]]:
    gate = ConfirmGate()
    hub = McpHub(cfg.mcp_servers, confirm=gate)
    await hub.start()
    team = Team(cfg, backend or make_backend(cfg.models), extra_leader_tools=hub.registry)
    try:
        yield team, gate, hub
    finally:
        await hub.close()
