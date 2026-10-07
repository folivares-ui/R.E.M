"""Texto -> voz mediante un proveedor enchufable.

Por diseño NO incluyo ni activo clonación de la voz de ninguna persona real sin su permiso.
Proveedores:
- `clonar_voz`: servidor local Clonar-voz (Qwen3-TTS + llama.cpp), voz de referencia con permiso registrado.
- `http`: una API de voz por HTTP que tú añadas (URL + variable de entorno con la clave).
- `none`: sin audio (AIRI puede usar su propio TTS).
- `command`: ejecuta un comando que TÚ configuras (lee el texto por stdin y escribe un WAV en la ruta
  que reemplaza a `{out}`), p. ej. un TTS local o un servicio que elijas y para el que tengas derechos.
Ver docs/VOZ.md.
"""
from __future__ import annotations

import json
import mimetypes
import os
import uuid
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


class ClonarVozTTS:
    """Cliente del servidor local «Clonar-voz» (https://github.com/jceronch1/Clonar-voz, MIT).

    Usa su API: `POST /api/generar` -> id de tarea -> SSE `/api/tarea/{id}/eventos` hasta `fin` ->
    `GET /api/salidas/{archivo}` (WAV). La síntesis ocurre 100 % en tu equipo.
    La voz (`voice_id`) es una entrada de SU biblioteca: se registra con `rem voice register`, que exige
    dejar constancia de que la voz es tuya o de que tienes permiso explícito de la persona.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8080", voice_id: str = "", language: str = "es",
                 device: str = "auto", timeout: int = 600):
        if not base_url.startswith(("http://127.0.0.1", "http://localhost")):
            raise ValueError("Clonar-voz no tiene autenticación: solo se admite una URL local (127.0.0.1/localhost).")
        self.base, self.voice_id, self.language, self.device, self.timeout = base_url.rstrip("/"), voice_id, language, device, timeout

    def _json(self, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"},
                                     method="POST" if body is not None else "GET")
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - URL local validada arriba
            return json.loads(r.read())

    def status(self) -> dict:
        return self._json("/api/estado")

    def voices(self) -> list[dict]:
        return self._json("/api/voces")

    def register_voice(self, wav_path: Path, name: str, transcript: str = "") -> dict:
        """Sube una muestra de referencia a la biblioteca de Clonar-voz (multipart)."""
        boundary = uuid.uuid4().hex
        parts: list[bytes] = []
        for k, v in (("nombre", name), ("transcripcion", transcript)):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        ctype = mimetypes.guess_type(wav_path.name)[0] or "application/octet-stream"
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="{wav_path.name}"\r\n'
                      f"Content-Type: {ctype}\r\n\r\n").encode() + wav_path.read_bytes() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(self.base + "/api/voces", data=b"".join(parts), method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310
            return json.loads(r.read())

    def synthesize(self, text: str) -> Path | None:
        if not text.strip():
            return None
        body = {"texto": text, "idioma": self.language, "dispositivo": self.device}
        if self.voice_id:
            body["voz"] = self.voice_id
        job = self._json("/api/generar", body)
        archivo = None
        req = urllib.request.Request(f"{self.base}/api/tarea/{job['id']}/eventos")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                ev = json.loads(line[5:])
                if ev["tipo"] == "fin":
                    archivo = ev["archivo"]
                    break
                if ev["tipo"] in ("error", "cancelada"):
                    raise RuntimeError(f"Clonar-voz: {ev.get('mensaje', ev['tipo'])}")
        if not archivo:
            return None
        with urllib.request.urlopen(f"{self.base}/api/salidas/{archivo}", timeout=60) as r:  # noqa: S310
            data = r.read()
        out = Path(tempfile.mkstemp(suffix=".wav", prefix="rem_tts_")[1])
        out.write_bytes(data)
        return out


def make_tts(voice_cfg: dict) -> TTSProvider:
    provider = (voice_cfg or {}).get("tts_provider", "none")
    if provider == "none":
        return NoTTS()
    if provider == "command":
        return CommandTTS(voice_cfg.get("tts_command", ""), voice_cfg.get("reference_wav"))
    if provider == "clonar_voz":
        return ClonarVozTTS(voice_cfg.get("clonar_voz_url", "http://127.0.0.1:8080"), voice_cfg.get("clonar_voz_voice_id", ""),
                            voice_cfg.get("clonar_voz_language", "es"), voice_cfg.get("clonar_voz_device", "auto"))
    if provider == "http":
        return HttpTTS(voice_cfg.get("tts_url", ""), voice_cfg.get("tts_api_key_env", "REM_TTS_API_KEY"),
                       voice_cfg.get("tts_model", ""), voice_cfg.get("tts_voice", ""), voice_cfg.get("tts_format", "wav"))
    raise ValueError(f"Proveedor TTS desconocido: {provider}")
