"""Puente hacia servidores MCP externos (God's Eye View, OpenMausBot...).

Cada servidor se lanza por stdio y sus herramientas se exponen a Claude con un prefijo
(`gev__...`, `maus__...`) para evitar colisiones de nombres.

Las herramientas con efectos (OpenMausBot puede enviar trabajo a bots) pasan por `confirm`:
una función async que debe devolver True para permitir la llamada.
"""
from __future__ import annotations

import logging
import re
from contextlib import AsyncExitStack
from typing import Any, Awaitable, Callable

from ..config import McpServerConfig
from .registry import Tool, ToolRegistry

log = logging.getLogger("rem.mcp")

Confirm = Callable[[str, dict[str, Any]], Awaitable[bool]]

# Herramientas de solo lectura conocidas por prefijo de nombre; todo lo demás pide confirmación.
READ_ONLY_HINTS = ("list", "get", "search", "read", "show", "find", "query", "status")


def _attr(obj: Any, snake: str, camel: str, default: Any = None) -> Any:
    """El SDK `mcp` 2.x usa snake_case y el 1.x camelCase: se aceptan ambos."""
    v = getattr(obj, snake, None)
    return v if v is not None else getattr(obj, camel, default)


def _is_read_only(tool_name: str, annotations: Any) -> bool:
    ro = _attr(annotations, "read_only_hint", "readOnlyHint")
    if ro is True:
        return True
    if ro is False:
        return False
    base = tool_name.lower().split("__")[-1]
    return base.startswith(READ_ONLY_HINTS)


def flatten_result(result: Any) -> str:
    parts = []
    for c in getattr(result, "content", None) or []:
        t = getattr(c, "type", None)
        if t == "text":
            parts.append(c.text)
        elif t == "image":
            parts.append("[imagen omitida]")
        else:
            parts.append(str(c))
    return "\n".join(parts) if parts else str(_attr(result, "structured_content", "structuredContent", "") or "")


class McpHub:
    def __init__(self, servers: dict[str, McpServerConfig], confirm: Confirm | None = None):
        self.servers = {k: v for k, v in servers.items() if v.enabled}
        self.confirm = confirm
        self._stack = AsyncExitStack()
        self._sessions: dict[str, Any] = {}
        self.registry = ToolRegistry()
        self.errors: dict[str, str] = {}

    async def start(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        for key, cfg in self.servers.items():
            try:
                params = StdioServerParameters(command=cfg.command, args=cfg.args, env=cfg.env or None)
                read, write = await self._stack.enter_async_context(stdio_client(params))
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self._sessions[key] = session
                listing = await session.list_tools()
                for t in listing.tools:
                    self._register(key, cfg, session, t)
                log.info("MCP %s: %d herramientas", key, len(listing.tools))
            except Exception as exc:  # noqa: BLE001 - un servidor caído no debe tumbar a Rem
                self.errors[key] = f"{type(exc).__name__}: {exc}"
                log.warning("MCP %s no disponible: %s", key, exc)

    def _register(self, key: str, cfg: McpServerConfig, session: Any, t: Any) -> None:
        name = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{cfg.prefix}__{t.name}")[:64]  # restricción de nombres de la API
        read_only = _is_read_only(t.name, getattr(t, "annotations", None))

        async def handler(args: dict[str, Any], _s=session, _n=t.name, _full=name, _ro=read_only) -> str:
            if not _ro:
                if self.confirm is None or not await self.confirm(_full, args):
                    return "Acción no ejecutada: requiere confirmación explícita de la persona."
            res = await _s.call_tool(_n, args)
            text = flatten_result(res)
            return ("ERROR: " + text) if _attr(res, "is_error", "isError", False) else text

        raw_schema = _attr(t, "input_schema", "inputSchema")
        schema = raw_schema if isinstance(raw_schema, dict) else {"type": "object", "properties": {}}
        desc = (t.description or t.name) + ("" if read_only else " [Requiere confirmación de la persona]")
        self.registry.add(Tool(name=name, description=desc[:1500], input_schema=schema, handler=handler))

    async def close(self) -> None:
        await self._stack.aclose()
