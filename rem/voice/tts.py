"""Texto -> voz mediante un proveedor enchufable.

Por diseño NO incluyo ni activo clonación de la voz de ninguna persona real sin su permiso.
Proveedores:
- `http`: una API de voz por HTTP que tú añadas (URL + variable de entorno con la clave).
- `none`: sin audio (AIRI puede usar su propio TTS).
- `command`: ejecuta un comando que TÚ configuras (lee el texto por stdin y escribe un WAV en la ruta
  que reemplaza a `{out}`), p. ej. un TTS local o un servicio que elijas y para el que tengas derechos.
Ver docs/VOZ.md.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
import urllib.request
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


class HttpTTS:
    """TTS por API HTTP con el formato `POST {url}` + JSON `{model, input, voice, response_format}` -> audio.

    Es la convención de los endpoints "OpenAI-compatible" de voz (`/v1/audio/speech`). No incluyo ni asumo
    ningún proveedor: tú pones la URL, el modelo, la voz y el NOMBRE de la variable de entorno con la clave
    (la clave nunca va en el YAML ni en git). Si tu proveedor usa otro formato, usa `command`.
    """

    def __init__(self, url: str, api_key_env: str = "REM_TTS_API_KEY", model: str = "", voice: str = "",
                 fmt: str = "wav", timeout: int = 60):
        if not url.startswith(("http://", "https://")):
            raise ValueError("tts_url debe empezar por http:// o https://")
        self.url, self.api_key_env, self.model, self.voice, self.fmt, self.timeout = url, api_key_env, model, voice, fmt, timeout

    def synthesize(self, text: str) -> Path | None:
        body: dict = {"input": text, "response_format": self.fmt}
        if self.model:
            body["model"] = self.model
        if self.voice:
            body["voice"] = self.voice
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 - URL configurada por el usuario
            data = r.read()
        if not data:
            return None
        out = Path(tempfile.mkstemp(suffix="." + self.fmt, prefix="rem_tts_")[1])
        out.write_bytes(data)
        return out


def make_tts(voice_cfg: dict) -> TTSProvider:
    provider = (voice_cfg or {}).get("tts_provider", "none")
    if provider == "none":
        return NoTTS()
    if provider == "command":
        return CommandTTS(voice_cfg.get("tts_command", ""), voice_cfg.get("reference_wav"))
    if provider == "http":
        return HttpTTS(voice_cfg.get("tts_url", ""), voice_cfg.get("tts_api_key_env", "REM_TTS_API_KEY"),
                       voice_cfg.get("tts_model", ""), voice_cfg.get("tts_voice", ""), voice_cfg.get("tts_format", "wav"))
    raise ValueError(f"Proveedor TTS desconocido: {provider}")
