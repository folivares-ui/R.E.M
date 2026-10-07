"""Activación por nombre: ¿alguien llamó a Rem?  Funciones puras (sin hardware)."""
from __future__ import annotations

import difflib
import re
import unicodedata


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9\s-]", " ", s)


def detect_wake(transcript: str, names: list[str], threshold: float = 0.8) -> tuple[bool, str]:
    """Devuelve (llamada, texto). `texto` es la frase original completa (el modelo entiende "Rem, lee esto").

    Tolera errores típicos del reconocimiento (mayúsculas, tildes, 'Rem,' 'rem-chan').
    Una coincidencia aproximada exige longitud similar para evitar falsos positivos.
    """
    tokens = _norm(transcript).split()
    wake = {_norm(n).strip() for n in names}
    wake_words = {w for n in wake for w in n.split() if w}
    for i, tok in enumerate(tokens):
        tok_clean = tok.strip("-")
        hit = tok_clean in wake or tok_clean in wake_words or any(
            abs(len(tok_clean) - len(w)) <= 1 and len(w) >= 4 and difflib.SequenceMatcher(None, tok_clean, w).ratio() >= threshold
            for w in wake_words
        )
        if hit:
            return True, transcript.strip()
    return False, ""
