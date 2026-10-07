"""Texto -> voz mediante un proveedor enchufable.

Por diseño NO incluyo ni activo clonación de la voz de ninguna persona real sin su permiso.
Proveedores:
- `none`: sin audio (AIRI puede usar su propio TTS).
- `command`: ejecuta un comando que TÚ configuras (lee el texto por stdin y escribe un WAV en la ruta
  que reemplaza a `{out}`), p. ej. un TTS local o un servicio que elijas y para el que tengas derechos.
Ver docs/VOZ.md.
"""
from __future__ import annotations

import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol


class TTSProvider(Protocol):
    def synthesize(self, text: str) -> Path | None: ...


class NoTTS:
    def synthesize(self, text: str) -> Path | None:
        return None


class CommandTTS:
    def __init__(self, command: str, reference_wav: str | None = None, timeout: int = 120):
        if "{out}" not in command:
            raise ValueError("El comando TTS debe contener {out} (ruta del WAV de salida).")
        self.command = command
        self.reference_wav = reference_wav
        self.timeout = timeout

    def synthesize(self, text: str) -> Path | None:
        out = Path(tempfile.mkstemp(suffix=".wav", prefix="rem_tts_")[1])
        cmd = self.command.replace("{out}", str(out)).replace("{ref}", self.reference_wav or "")
        subprocess.run(shlex.split(cmd), input=text.encode("utf-8"), check=True, timeout=self.timeout)
        return out if out.exists() and out.stat().st_size > 0 else None


def make_tts(voice_cfg: dict) -> TTSProvider:
    provider = (voice_cfg or {}).get("tts_provider", "none")
    if provider == "none":
        return NoTTS()
    if provider == "command":
        return CommandTTS(voice_cfg.get("tts_command", ""), voice_cfg.get("reference_wav"))
    raise ValueError(f"Proveedor TTS desconocido: {provider}")
