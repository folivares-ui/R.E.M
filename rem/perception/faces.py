"""Registro de rostros CON CONSENTIMIENTO.

- Solo se reconoce a quien se inscribió explícitamente (`enroll(..., consent=True)`).
- Se guardan únicamente embeddings (vectores) y el sello de consentimiento, nunca fotos.
- Todo queda en `data/faces/` (ignorado por git). `forget(name)` borra a la persona.
- Los rostros no inscritos se tratan como "desconocido": nunca se intenta identificarlos.

Detección/embeddings: InsightFace (`FaceAnalysis`, `face.normed_embedding`) — no verificado en este
entorno (sin cámara/GPU). Revisa la licencia de los modelos preentrenados antes de cualquier uso fuera del prototipo.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path


def cosine(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


class FaceRegistry:
    def __init__(self, directory: Path, threshold: float = 0.45):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.threshold = threshold  # a calibrar con tus propias cámaras

    def _file(self, name: str) -> Path:
        safe = "".join(c for c in name.lower() if c.isalnum() or c in "-_") or "persona"
        return self.dir / f"{safe}.json"

    def enroll(self, name: str, embedding: list[float], consent: bool) -> None:
        if not consent:
            raise PermissionError("No se puede inscribir un rostro sin consentimiento explícito.")
        self._file(name).write_text(json.dumps({
            "name": name, "embedding": list(map(float, embedding)),
            "consent_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }), encoding="utf-8")

    def forget(self, name: str) -> bool:
        f = self._file(name)
        if f.exists():
            f.unlink()
            return True
        return False

    def people(self) -> list[str]:
        return sorted(json.loads(f.read_text(encoding="utf-8"))["name"] for f in self.dir.glob("*.json"))

    def identify(self, embedding: list[float]) -> tuple[str | None, float]:
        best, best_score = None, -1.0
        for f in self.dir.glob("*.json"):
            rec = json.loads(f.read_text(encoding="utf-8"))
            s = cosine(embedding, rec["embedding"])
            if s > best_score:
                best, best_score = rec["name"], s
        return (best, best_score) if best_score >= self.threshold else (None, best_score)


class FaceEmbedder:  # pragma: no cover - requiere insightface + onnxruntime
    def __init__(self):
        from insightface.app import FaceAnalysis

        self._app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        self._app.prepare(ctx_id=-1, det_size=(640, 640))

    def embeddings(self, frame_bgr) -> list[list[float]]:
        return [f.normed_embedding.tolist() for f in self._app.get(frame_bgr)]
