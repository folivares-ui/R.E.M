"""Voz -> texto con faster-whisper (local). No verificado aquí: sin micrófono ni descarga de modelos."""
from __future__ import annotations


class Transcriber:  # pragma: no cover
    def __init__(self, model_size: str = "small", language: str = "es"):
        from faster_whisper import WhisperModel

        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
        self.language = language

    def transcribe(self, audio_f32_16k) -> str:
        segments, _info = self._model.transcribe(audio_f32_16k, language=self.language, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()
