"""Bucle de cámara: gestos + rostros -> eventos de texto para Rem.

No se ejecuta en CI ni en este sandbox (no hay cámara). Los eventos se entregan a un callback async.
Indicador de privacidad: se registra en el log cada vez que la cámara se abre.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from .faces import FaceRegistry
from .gestures import Debouncer, gesture_to_intent

log = logging.getLogger("rem.camera")
EventCb = Callable[[str, dict], Awaitable[None]]


async def run_camera(cfg_perception: dict, registry: FaceRegistry | None, on_event: EventCb,
                     gesture_model: str | None, stop: asyncio.Event) -> None:  # pragma: no cover
    import cv2

    from .faces import FaceEmbedder
    from .gestures import GestureRecognizerWrapper

    cap = cv2.VideoCapture(int(cfg_perception.get("camera_index", 0)))
    if not cap.isOpened():
        raise RuntimeError("No se pudo abrir la cámara.")
    log.warning("CÁMARA ACTIVA (los vídeos no se guardan; solo se emiten eventos)")
    gr = GestureRecognizerWrapper(gesture_model) if (cfg_perception.get("gestures", True) and gesture_model) else None
    fe = FaceEmbedder() if (cfg_perception.get("faces", True) and registry is not None) else None
    deb, seen_people, i = Debouncer(), {}, 0
    try:
        while not stop.is_set():
            ok, frame = cap.read()
            if not ok:
                await asyncio.sleep(0.1)
                continue
            i += 1
            if gr is not None:
                label = gr.recognize(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                fired = deb.update(label)
                if fired and (info := gesture_to_intent(fired)):
                    await on_event("gesto", {"gesture": fired, "intent": info[0], "description": info[1]})
            if fe is not None and registry is not None and i % 15 == 0:
                now = asyncio.get_event_loop().time()
                for emb in fe.embeddings(frame):
                    name, score = registry.identify(emb)
                    if name and now - seen_people.get(name, -1e9) > 300:  # saluda 1 vez cada 5 min
                        seen_people[name] = now
                        await on_event("persona", {"name": name, "score": round(score, 2)})
            await asyncio.sleep(0.03)
    finally:
        cap.release()
        log.info("Cámara cerrada")
