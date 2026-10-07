#!/usr/bin/env python3
"""Descarga el modelo Kokoro (int8) y el paquete de voces a ./models, verificando SHA-256.

Los hashes son los de los archivos con los que PROBÉ la síntesis en español (2026-10-07), descargados de los
releases del proyecto kokoro-onnx. Si no coinciden, el archivo se rechaza (puede haber cambiado o estar corrupto):
revisa el origen antes de actualizar el hash.
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = {
    "kokoro-v1.0.int8.onnx": "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb",
    "voices-v1.0.bin": "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(dest: Path = Path("models")) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    for name, digest in FILES.items():
        target = dest / name
        if target.exists() and sha256(target) == digest:
            print(f"✔ {name} ya está verificado")
            continue
        tmp = target.with_suffix(target.suffix + ".part")
        print(f"↓ {name} ...")
        urllib.request.urlretrieve(BASE + name, tmp)  # noqa: S310 - URL fija
        if sha256(tmp) != digest:
            tmp.unlink(missing_ok=True)
            print(f"✘ {name}: el SHA-256 no coincide; descarga rechazada", file=sys.stderr)
            return 1
        tmp.replace(target)
        print(f"✔ {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
