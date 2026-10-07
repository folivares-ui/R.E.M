"""Puerta de confirmación para acciones con efectos externos.

Flujo: el modelo llama a una herramienta con efectos -> se registra como PENDIENTE y se deniega;
Rem pregunta a la persona; si el siguiente mensaje HUMANO es afirmativo, la misma llamada (mismo
nombre y argumentos) se permite una vez. Texto leído de documentos/herramientas nunca cuenta como "sí".
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_YES = re.compile(r"^\s*(s[ií]|sí,?|claro|confirmo|confirmado|adelante|ok|okay|dale|hazlo|procede|de acuerdo|yes)\b", re.I)
_NO_AFTER = re.compile(r"\b(no|pero|espera|cancela)\b", re.I)


def _key(name: str, args: dict[str, Any]) -> str:
    return hashlib.sha256((name + json.dumps(args, sort_keys=True, default=str)).encode()).hexdigest()


class ConfirmGate:
    def __init__(self) -> None:
        self._pending: set[str] = set()
        self._approved: set[str] = set()

    def note_user_message(self, text: str) -> None:
        """Llamar al recibir cada mensaje HUMANO. Un 'sí' aprueba lo pendiente; cualquier otra cosa lo descarta."""
        affirmative = bool(_YES.match(text)) and not _NO_AFTER.search(text)
        self._approved = set(self._pending) if affirmative else set()
        self._pending = set()

    async def __call__(self, name: str, args: dict[str, Any]) -> bool:
        k = _key(name, args)
        if k in self._approved:
            self._approved.discard(k)
            return True
        self._pending.add(k)
        return False
