"""Gestos de mano -> intenciones.

Reconocimiento: MediaPipe Gesture Recognizer (API `mediapipe.tasks.python.vision`), que necesita un
archivo de modelo `gesture_recognizer.task` descargado aparte (ver docs/PERCEPCION.md).
Las categorías integradas que espero (verificar en la documentación de MediaPipe vigente):
Closed_Fist, Open_Palm, Pointing_Up, Thumb_Down, Thumb_Up, Victory, ILoveYou.
"""
from __future__ import annotations

from dataclasses import dataclass

GESTURE_TO_INTENT = {
    "Open_Palm": ("saludo", "Saluda con la mano abierta."),
    "Thumb_Up": ("aprobado", "Hace un pulgar arriba (aprobación)."),
    "Thumb_Down": ("rechazo", "Hace un pulgar abajo (desaprobación)."),
    "Closed_Fist": ("pausa", "Cierra el puño (pide pausa/silencio)."),
    "Pointing_Up": ("atencion", "Levanta el índice (pide atención/pregunta)."),
    "Victory": ("paz", "Hace la señal de victoria."),
    "ILoveYou": ("cariño", "Hace el gesto de 'te quiero'."),
}


def gesture_to_intent(category: str | None) -> tuple[str, str] | None:
    return GESTURE_TO_INTENT.get(category or "")


@dataclass
class Debouncer:
    """Evita disparar el mismo evento en cada fotograma: exige N fotogramas seguidos y un enfriamiento."""
    frames_required: int = 5
    cooldown_frames: int = 60
    _last: str | None = None
    _count: int = 0
    _cool: int = 0

    def update(self, label: str | None) -> str | None:
        if self._cool > 0:
            self._cool -= 1
        if label is None or label != self._last:
            self._last, self._count = label, 1 if label else 0
            return None
        self._count += 1
        if self._count >= self.frames_required and self._cool == 0:
            self._cool = self.cooldown_frames
            return label
        return None


class GestureRecognizerWrapper:  # pragma: no cover - requiere mediapipe + modelo + cámara
    def __init__(self, model_path: str):
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        opts = vision.GestureRecognizerOptions(base_options=mp_python.BaseOptions(model_asset_path=model_path))
        self._rec = vision.GestureRecognizer.create_from_options(opts)
        self._mp = mp

    def recognize(self, frame_rgb) -> str | None:
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=frame_rgb)
        res = self._rec.recognize(image)
        if res.gestures and res.gestures[0]:
            top = res.gestures[0][0]
            if top.score >= 0.6 and top.category_name != "None":
                return top.category_name
        return None
