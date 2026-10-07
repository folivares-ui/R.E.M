"""Modo en vivo: micrófono -> STT -> llamada por nombre -> Rem -> (TTS) + cámara.

NO verificado en este entorno (sin micrófono, cámara ni modelos descargados). Es el esqueleto para
probar en tu equipo; ver docs/PERCEPCION.md. Requiere: pip install 'rem-avatar[voice,vision,faces]'.
"""
from __future__ import annotations

import asyncio
import logging
import time

from .app import build_team
from .config import load_config
from .perception.faces import FaceRegistry
from .perception.wake import detect_wake
from .stage import strip_stage_tokens
from .voice.tts import make_tts

log = logging.getLogger("rem.live")
SAMPLE_RATE = 16000
CONVERSATION_WINDOW_S = 12  # tras oír su nombre, sigue escuchando sin repetirlo


async def run_live(config_path: str | None = None) -> None:  # pragma: no cover
    import numpy as np
    import sounddevice as sd

    from .perception.camera import run_camera
    from .voice.stt import Transcriber

    cfg = load_config(config_path)
    stt = Transcriber(cfg.voice.get("stt_model", "small"), cfg.language)
    tts = make_tts(cfg.voice)
    registry = FaceRegistry(cfg.resolve(cfg.data_dir) / "faces")
    stop = asyncio.Event()
    awake_until = 0.0
    pending_events: list[str] = []

    async with build_team(cfg) as (team, gate, _hub):
        async def on_event(kind: str, data: dict) -> None:
            if kind == "persona":
                pending_events.append(f"[Cámara] Reconoces a {data['name']}, que acaba de aparecer. Salúdale brevemente.")
            elif kind == "gesto":
                pending_events.append(f"[Cámara] {data['description']}")

        cam = None
        if cfg.perception.get("gestures", True) or cfg.perception.get("faces", True):
            model = cfg.perception.get("gesture_model")
            cam = asyncio.create_task(run_camera(cfg.perception, registry, on_event, model, stop))

        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()

        def callback(indata, frames, t, status):  # hilo de audio
            loop.call_soon_threadsafe(q.put_nowait, indata[:, 0].copy())

        buf: list = []
        silent = 0
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback, blocksize=1600):
            log.warning("MICRÓFONO ACTIVO: escuchando; solo respondo si dices %s", cfg.wake_names)
            while not stop.is_set():
                chunk = await q.get()
                loud = float(np.sqrt(np.mean(chunk ** 2))) > 0.01
                if loud:
                    buf.append(chunk)
                    silent = 0
                elif buf:
                    silent += 1
                    buf.append(chunk)
                    if silent > 8:  # ~0.8 s de silencio cierra la frase
                        audio = np.concatenate(buf)
                        buf, silent = [], 0
                        text = await loop.run_in_executor(None, stt.transcribe, audio)
                        if not text:
                            continue
                        called, _ = detect_wake(text, cfg.wake_names) if cfg.perception.get("wake_by_name", True) else (True, text)
                        now = time.monotonic()
                        if called:
                            awake_until = now + CONVERSATION_WINDOW_S
                        elif now > awake_until:
                            continue  # nadie la llamó: se descarta sin guardar
                        gate.note_user_message(text)
                        prompt = "\n".join([*pending_events, text])
                        pending_events.clear()
                        res = await team.chat(prompt, source="voz")
                        reply = strip_stage_tokens(res.text)
                        print(f"{cfg.name}> {reply}")
                        wav = await loop.run_in_executor(None, tts.synthesize, reply)
                        if wav:
                            print(f"(audio: {wav})")
                        awake_until = time.monotonic() + CONVERSATION_WINDOW_S
        stop.set()
        if cam:
            await cam
