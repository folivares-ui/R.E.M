"""Convenciones del escenario AIRI: etiquetas de emoción para animar al avatar.

Formato verificado en el código de AIRI (packages/stage-ui): `<|ACT {"emotion":{"name":"happy","intensity":1}}|>`
con nombres: happy, sad, angry, think, surprised, awkward, question, curious, neutral.
"""
from __future__ import annotations

import re

EMOTIONS = ("happy", "sad", "angry", "think", "surprised", "awkward", "question", "curious", "neutral")

STAGE_ADDENDUM = """
Estás encarnada en un avatar animado. Para que tu cuerpo exprese emociones, puedes intercalar \
etiquetas con este formato exacto, antes de la frase a la que aplican:
<|ACT {"emotion":{"name":"happy","intensity":1}}|>
Nombres válidos: happy, sad, angry, think, surprised, awkward, question, curious, neutral. \
Intensidad entre 0 y 1. Usa pocas (0-2 por respuesta) y nunca las expliques ni las menciones. \
Todo el texto fuera de las etiquetas se pronuncia en voz alta: sin markdown, sin listas ni tablas; \
si hay datos extensos, resume en voz y ofrece el detalle por escrito.
"""

_ACT = re.compile(r"<\|ACT\s*\{.*?\}\s*\|>", re.S)
_DELAY = re.compile(r"<\|DELAY:[^|]*\|>")


def strip_stage_tokens(text: str) -> str:
    return _DELAY.sub("", _ACT.sub("", text)).strip()
