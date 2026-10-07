from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def text_block(t: str) -> dict:
    return {"type": "text", "text": t}


def tool_use(id_: str, name: str, inp: dict) -> dict:
    return {"type": "tool_use", "id": id_, "name": name, "input": inp}


def resp(content: list[dict], stop: str) -> Any:
    return SimpleNamespace(content=content, stop_reason=stop)


class FakeBackend:
    """Respuestas guionadas; registra cada solicitud para inspeccionarla."""

    def __init__(self, script):
        self.script = script  # list de respuestas o callable(kwargs)->resp
        self.calls: list[dict] = []

    async def create(self, **kw):
        # copia superficial del historial para que mutaciones posteriores no alteren el registro
        kw = dict(kw)
        kw["messages"] = [dict(m) for m in kw["messages"]]
        self.calls.append(kw)
        if callable(self.script):
            return self.script(kw)
        return self.script.pop(0)
