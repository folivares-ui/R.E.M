"""Registro de herramientas locales expuestas a Claude."""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

Handler = Callable[[dict[str, Any]], Any | Awaitable[Any]]


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Handler

    def api_schema(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {}
        for t in tools or []:
            self.add(t)

    def add(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Herramienta duplicada: {tool.name}")
        self._tools[tool.name] = tool

    def extend(self, other: "ToolRegistry") -> None:
        for t in other._tools.values():
            self.add(t)

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [t.api_schema() for t in self._tools.values()]

    async def call(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        """Devuelve (texto, es_error). Nunca lanza: los errores vuelven al modelo."""
        tool = self._tools.get(name)
        if tool is None:
            return f"Herramienta desconocida: {name}", True
        try:
            out = tool.handler(args)
            if inspect.isawaitable(out):
                out = await out
        except Exception as exc:  # noqa: BLE001 - se devuelve al modelo como error de herramienta
            return f"{type(exc).__name__}: {exc}", True
        if isinstance(out, str):
            return out, False
        return json.dumps(out, ensure_ascii=False, default=str), False
