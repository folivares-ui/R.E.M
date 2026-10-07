"""Bucle de agente sobre la API de Anthropic (SDK oficial, bucle manual).

Notas de la API (verificadas contra la documentación del SDK incluida en esta sesión):
- Modelos Opus 5.5 / Sonnet 5.5: `thinking={"type": "adaptive"}`; `budget_tokens` y
  `tool_choice` forzado devuelven 400, así que no se usan.
- `output_config={"effort": ...}` controla la profundidad de razonamiento.
- Los bloques de herramientas de servidor (web_search) pueden terminar en `pause_turn`:
  se reenvía el turno del asistente para continuar.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from .tools.registry import ToolRegistry

log = logging.getLogger("rem.llm")

MAX_TOKENS = 16000  # solicitud no streaming: se mantiene bajo los timeouts del SDK
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class MessagesClient(Protocol):
    async def create(self, **kwargs: Any) -> Any: ...


class AnthropicBackend:
    """Envoltorio fino para poder sustituir el cliente en pruebas."""

    def __init__(self, fallbacks: bool = True, client: Any | None = None):
        import anthropic

        self._client = client or anthropic.AsyncAnthropic()
        self._fallbacks = fallbacks

    async def create(self, **kwargs: Any) -> Any:
        if self._fallbacks:
            return await self._client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
        return await self._client.messages.create(**kwargs)


@dataclass
class AgentResult:
    text: str
    turns: int
    tool_calls: list[str] = field(default_factory=list)
    stop_reason: str | None = None


def _block_type(b: Any) -> str:
    return b["type"] if isinstance(b, dict) else b.type


def _get(b: Any, key: str, default: Any = None) -> Any:
    return b.get(key, default) if isinstance(b, dict) else getattr(b, key, default)


def extract_text(content: list[Any]) -> str:
    return "".join(_get(b, "text", "") for b in content if _block_type(b) == "text").strip()


def _to_param(block: Any) -> Any:
    """Convierte un bloque de respuesta en parámetro de mensaje (conserva thinking/tool_use tal cual)."""
    if isinstance(block, dict):
        return block
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    return block


async def run_agent(
    backend: MessagesClient,
    *,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    tools: ToolRegistry | None = None,
    server_tools: list[dict[str, Any]] | None = None,
    effort: str = "medium",
    max_turns: int = 12,
) -> AgentResult:
    """Ejecuta el bucle: modelo -> herramientas -> modelo, hasta `end_turn`.

    `messages` se modifica in situ (sirve como historial de conversación).
    """
    registry = tools or ToolRegistry()
    tool_schemas = registry.schemas() + list(server_tools or [])
    called: list[str] = []

    for turn in range(1, max_turns + 1):
        kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
        )
        if tool_schemas:
            kwargs["tools"] = tool_schemas
        resp = await backend.create(**kwargs)
        content = [_to_param(b) for b in resp.content]
        stop = resp.stop_reason

        if stop == "refusal":
            messages.append({"role": "assistant", "content": content})
            return AgentResult("Lo siento, no puedo ayudar con esa solicitud.", turn, called, stop)

        if stop == "pause_turn":  # herramienta de servidor: continuar con el mismo historial
            messages.append({"role": "assistant", "content": content})
            continue

        messages.append({"role": "assistant", "content": content})
        uses = [b for b in content if b.get("type") == "tool_use"]
        if stop != "tool_use" or not uses:
            if stop == "max_tokens":
                log.warning("Respuesta truncada por max_tokens")
            return AgentResult(extract_text(content), turn, called, stop)

        async def _run(use: dict[str, Any]) -> dict[str, Any]:
            called.append(use["name"])
            inp = use.get("input") or {}
            if "_invalid_arguments" in inp:  # modelo pequeño que devolvió JSON roto
                out, is_err = "Los argumentos no eran JSON válido; vuelve a llamar a la herramienta con JSON correcto.", True
            else:
                out, is_err = await registry.call(use["name"], inp)
            res: dict[str, Any] = {"type": "tool_result", "tool_use_id": use["id"], "content": out}
            if is_err:
                res["is_error"] = True
            return res

        # Todas las llamadas en paralelo, todos los resultados en UN solo mensaje de usuario.
        results = await asyncio.gather(*(_run(u) for u in uses))
        messages.append({"role": "user", "content": list(results)})

    return AgentResult("Me quedé sin pasos para terminar la tarea; dime si continúo.", max_turns, called, "max_turns")
