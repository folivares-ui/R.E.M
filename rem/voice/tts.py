"""Texto -> voz mediante un proveedor enchufable.

Por diseño R.E.M. NO clona voces: solo usa voces predefinidas/sintéticas.
Proveedores:
- `kokoro`: voz sintética local (Kokoro-82M, CPU), voces predefinidas; sin clonación.
- `http`: una API de voz por HTTP que tú añadas (URL + variable de entorno con la clave).
- `none`: sin audio (AIRI puede usar su propio TTS).
- `command`: ejecuta un comando que TÚ configuras (lee el texto por stdin y escribe un WAV en la ruta
  que reemplaza a `{out}`), p. ej. un TTS local o un servicio que elijas y para el que tengas derechos.
Ver docs/VOZ.md.
"""
from __future__ import annotations

import json
import os
import threading
import wave
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
    def __init__(self, command: str, timeout: int = 120):
        if "{out}" not in command:
            raise ValueError("El comando TTS debe contener {out} (ruta del WAV de salida).")
        self.command = command
        self.timeout = timeout

    def synthesize(self, text: str) -> Path | None:
        out = Path(tempfile.mkstemp(suffix=".wav", prefix="rem_tts_")[1])
        # Dividir PRIMERO y sustituir después: shlex se comería las barras invertidas de rutas de Windows.
        argv = [a.replace("{out}", str(out)) for a in shlex.split(self.command, posix=(os.name != "nt"))]
        argv = [a[1:-1] if len(a) > 1 and a[0] == a[-1] and a[0] in "\"'" else a for a in argv]
        subprocess.run(argv, input=text.encode("utf-8"), check=True, timeout=self.timeout)
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


class KokoroTTS:
    """Voz sintética local con Kokoro-82M (ONNX, CPU). Voces PREDEFINIDAS del modelo: no clona a ninguna persona.

    Voces en español incluidas en el paquete de voces: `ef_dora` (femenina), `em_alex` y `em_santa` (masculinas).
    Archivos: `python scripts/download_kokoro.py` (modelo int8 ~92 MB + voces ~28 MB). Licencia: ver docs/VOZ.md.
    """

    def __init__(self, model_path: str, voices_path: str, voice: str = "ef_dora", speed: float = 1.0, lang: str = "es"):
        self.model_path, self.voices_path, self.voice, self.speed, self.lang = model_path, voices_path, voice, speed, lang
        self._k = None
        self._lock = threading.Lock()   # la sesión ONNX se comparte: una síntesis a la vez

    def _engine(self):
        if self._k is None:
            try:
                from kokoro_onnx import Kokoro
            except ImportError as exc:
                raise RuntimeError("Instala el extra: pip install 'rem-avatar[tts-kokoro]'") from exc
            for f in (self.model_path, self.voices_path):
                if not Path(f).is_file():
                    raise RuntimeError(f"Falta {f}. Ejecuta: python scripts/download_kokoro.py")
            self._k = Kokoro(self.model_path, self.voices_path)
        return self._k

    def synthesize(self, text: str, voice: str | None = None) -> Path | None:
        text = text.strip()
        if not text:
            return None
        import numpy as np

        with self._lock:
            k = self._engine()
            v = voice if voice in k.get_voices() else self.voice
            samples, sr = k.create(text, voice=v, speed=self.speed, lang=self.lang)
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
        out = Path(tempfile.mkstemp(suffix=".wav", prefix="rem_tts_")[1])
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())
        return out


def make_tts(voice_cfg: dict) -> TTSProvider:
    provider = (voice_cfg or {}).get("tts_provider", "none")
    if provider == "none":
        return NoTTS()
    if provider == "command":
        return CommandTTS(voice_cfg.get("tts_command", ""))
    if provider == "kokoro":
        return KokoroTTS(voice_cfg.get("kokoro_model", "models/kokoro-v1.0.int8.onnx"),
                         voice_cfg.get("kokoro_voices", "models/voices-v1.0.bin"),
                         voice_cfg.get("kokoro_voice", "ef_dora"), float(voice_cfg.get("kokoro_speed", 1.0)),
                         voice_cfg.get("kokoro_lang", "es"))
    if provider == "http":
        return HttpTTS(voice_cfg.get("tts_url", ""), voice_cfg.get("tts_api_key_env", "REM_TTS_API_KEY"),
                       voice_cfg.get("tts_model", ""), voice_cfg.get("tts_voice", ""), voice_cfg.get("tts_format", "wav"))
    raise ValueError(f"Proveedor TTS desconocido: {provider}")
