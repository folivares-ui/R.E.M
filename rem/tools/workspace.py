"""Archivos de trabajo del programador: lectura/escritura confinadas a una carpeta."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .registry import Tool

MAX_WRITE = 500_000


def _inside(root: Path, rel: str) -> Path:
    root = root.resolve()
    p = (root / rel).resolve()
    if root != p and root not in p.parents:
        raise ValueError("La ruta sale de la carpeta de trabajo.")
    return p


def make_workspace_tools(root: Path) -> list[Tool]:
    root.mkdir(parents=True, exist_ok=True)

    def write(a: dict[str, Any]) -> str:
        content = a["content"]
        if len(content) > MAX_WRITE:
            raise ValueError("Contenido demasiado grande.")
        p = _inside(root, a["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Escrito {p.relative_to(root.resolve())} ({len(content)} caracteres)."

    def read(a: dict[str, Any]) -> str:
        return _inside(root, a["path"]).read_text(encoding="utf-8", errors="replace")

    def ls(a: dict[str, Any]) -> str:
        base = _inside(root, a.get("path", "."))
        return "\n".join(sorted(str(q.relative_to(root.resolve())) for q in base.rglob("*") if q.is_file())) or "(vacío)"

    obj = lambda props, req: {"type": "object", "properties": props, "required": req}  # noqa: E731
    return [
        Tool("workspace_escribir", "Crea o sobrescribe un archivo dentro de la carpeta de trabajo.",
             obj({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]), write),
        Tool("workspace_leer", "Lee un archivo de la carpeta de trabajo.", obj({"path": {"type": "string"}}, ["path"]), read),
        Tool("workspace_listar", "Lista los archivos de la carpeta de trabajo.", obj({"path": {"type": "string"}}, []), ls),
    ]
