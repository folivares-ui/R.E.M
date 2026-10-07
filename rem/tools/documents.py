"""Lectura de documentos: PDF, Word, Excel, PowerPoint, Project, bases de datos, texto/markdown.

Principios:
- Nada se trunca en silencio: la salida indica `offset`, `total_chars` y si hay más.
- Los formatos antiguos (.doc/.xls/.ppt) se convierten con LibreOffice si está instalado.
"""
from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .registry import Tool

DEFAULT_MAX_CHARS = 60_000
TEXT_EXT = {".md", ".markdown", ".txt", ".rst", ".json", ".yaml", ".yml", ".xml", ".html", ".htm",
            ".log", ".ini", ".toml", ".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs", ".go", ".rs",
            ".sql", ".sh", ".rtf"}
LEGACY_CONVERT = {".doc": "docx", ".xls": "xlsx", ".ppt": "pptx", ".odt": "docx", ".ods": "xlsx", ".odp": "pptx"}
DB_EXT = {".sqlite", ".sqlite3", ".db", ".duckdb"}


class DocumentError(Exception):
    pass


def _safe_path(path: str, root: Path | None) -> Path:
    p = Path(path).expanduser().resolve()
    if root is not None:
        r = root.resolve()
        if r != p and r not in p.parents:
            raise DocumentError(f"Ruta fuera de la carpeta permitida ({r}).")
    if not p.exists():
        raise DocumentError(f"No existe: {p}")
    if not p.is_file():
        raise DocumentError(f"No es un archivo: {p}")
    return p


def _read_pdf(p: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(p))
    if reader.is_encrypted:
        try:
            ok = reader.decrypt("")
        except Exception:  # noqa: BLE001
            ok = 0
        if not ok:
            raise DocumentError("PDF cifrado: se necesita contraseña.")
    parts = []
    for i, page in enumerate(reader.pages, 1):
        parts.append(f"--- Página {i} ---\n{(page.extract_text() or '').strip()}")
    text = "\n\n".join(parts)
    if not text.replace("-", "").strip() or all(not (pg.extract_text() or "").strip() for pg in reader.pages):
        text += "\n[Aviso: no se extrajo texto; puede ser un PDF escaneado (requiere OCR).]"
    return text


def _read_docx(p: Path) -> str:
    import docx

    d = docx.Document(str(p))
    out: list[str] = []
    for para in d.paragraphs:
        if not para.text.strip():
            continue
        style = (para.style.name or "") if para.style is not None else ""
        if style.lower().startswith("heading"):
            level = "".join(ch for ch in style if ch.isdigit()) or "1"
            out.append("#" * int(level) + " " + para.text.strip())
        else:
            out.append(para.text.strip())
    for ti, table in enumerate(d.tables, 1):
        out.append(f"\n[Tabla {ti}]")
        for row in table.rows:
            out.append(" | ".join(c.text.strip().replace("\n", " ") for c in row.cells))
    return "\n".join(out)


def _read_xlsx(p: Path) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(str(p), data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        out.append(f"=== Hoja: {ws.title} ===")
        for row in ws.iter_rows(values_only=True):
            if row is None or all(c is None for c in row):
                continue
            out.append("\t".join("" if c is None else str(c) for c in row))
    return "\n".join(out)


def _read_pptx(p: Path) -> str:
    from pptx import Presentation

    prs = Presentation(str(p))
    out = []
    for i, slide in enumerate(prs.slides, 1):
        out.append(f"--- Diapositiva {i} ---")
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                out.append(shape.text_frame.text.strip())
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    out.append(" | ".join(c.text.strip() for c in row.cells))
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            out.append("[Notas] " + slide.notes_slide.notes_text_frame.text.strip())
    return "\n".join(out)


def _read_csv(p: Path) -> str:
    with p.open(newline="", encoding="utf-8", errors="replace") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel
        return "\n".join("\t".join(r) for r in csv.reader(f, dialect))


def _read_mpp(p: Path) -> str:
    """Microsoft Project (.mpp, .mpx, .xml MSPDI...) vía MPXJ (requiere Java y `pip install mpxj`)."""
    try:
        import jpype
        import mpxj  # noqa: F401  (añade el classpath)
    except ImportError as exc:
        raise DocumentError("Para leer Project instala el extra: pip install 'rem-avatar[project]' (y Java).") from exc
    if not jpype.isJVMStarted():
        jpype.startJVM()
    from org.mpxj.reader import UniversalProjectReader  # type: ignore[import-not-found]

    project = UniversalProjectReader().read(str(p))
    if project is None:
        raise DocumentError("MPXJ no reconoció el formato del archivo de Project.")
    out = ["id\tnombre\tinicio\tfin\t%completado"]
    for t in project.getTasks():
        if t.getName() is None:
            continue
        out.append("\t".join(str(x) for x in (t.getID(), t.getName(), t.getStart(), t.getFinish(), t.getPercentageComplete())))
    return "\n".join(out)


def _sqlite_summary(p: Path, max_rows: int = 5) -> str:
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        out = []
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for t in tables:
            cols = con.execute(f'PRAGMA table_info("{t}")').fetchall()
            n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            out.append(f"Tabla {t} ({n} filas): " + ", ".join(f"{c[1]} {c[2]}" for c in cols))
            for row in con.execute(f'SELECT * FROM "{t}" LIMIT {max_rows}'):
                out.append("  " + " | ".join(map(str, row)))
        return "\n".join(out) or "(base de datos sin tablas)"
    finally:
        con.close()


def _convert_legacy(p: Path) -> Path:
    target = LEGACY_CONVERT[p.suffix.lower()]
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise DocumentError(f"{p.suffix} es un formato antiguo; instala LibreOffice para convertirlo o guárdalo como .{target}.")
    outdir = Path(tempfile.mkdtemp(prefix="rem_conv_"))
    r = subprocess.run([soffice, "--headless", "--convert-to", target, "--outdir", str(outdir), str(p)],
                       capture_output=True, text=True, timeout=180)
    out = outdir / (p.stem + "." + target)
    if r.returncode != 0 or not out.exists():
        raise DocumentError(f"Fallo al convertir {p.name}: {r.stderr.strip()[:300]}")
    return out


def extract_text(p: Path) -> str:
    ext = p.suffix.lower()
    if ext == ".pdf":
        return _read_pdf(p)
    if ext in LEGACY_CONVERT:
        return extract_text(_convert_legacy(p))
    if ext in (".docx", ".docm"):
        return _read_docx(p)
    if ext in (".xlsx", ".xlsm"):
        return _read_xlsx(p)
    if ext == ".pptx":
        return _read_pptx(p)
    if ext in (".csv", ".tsv"):
        return _read_csv(p)
    if ext in (".mpp", ".mpt", ".mpx"):
        return _read_mpp(p)
    if ext in DB_EXT:
        if ext == ".duckdb":
            raise DocumentError("Para DuckDB usa la herramienta `consultar_base_de_datos` con una URL duckdb:///ruta.")
        return _sqlite_summary(p)
    if ext in TEXT_EXT or ext == "":
        return p.read_text(encoding="utf-8", errors="replace")
    # Último recurso: ¿es texto?
    raw = p.read_bytes()[:4096]
    if b"\x00" not in raw:
        return p.read_text(encoding="utf-8", errors="replace")
    raise DocumentError(f"Formato no soportado: {ext}")


def read_document(path: str, root: Path | None = None, offset: int = 0, max_chars: int = DEFAULT_MAX_CHARS) -> dict[str, Any]:
    p = _safe_path(path, root)
    text = extract_text(p)
    total = len(text)
    chunk = text[offset: offset + max_chars]
    end = offset + len(chunk)
    return {
        "file": p.name,
        "total_chars": total,
        "offset": offset,
        "returned_chars": len(chunk),
        "has_more": end < total,
        "next_offset": end if end < total else None,
        "text": chunk,
    }


def make_document_tools(root: Path | None) -> list[Tool]:
    def handler(a: dict[str, Any]) -> str:
        res = read_document(a["path"], root, int(a.get("offset", 0)), int(a.get("max_chars", DEFAULT_MAX_CHARS)))
        return json.dumps(res, ensure_ascii=False)

    return [Tool(
        name="leer_documento",
        description=("Lee un archivo local y devuelve su texto: PDF, Word (.docx/.doc), Excel (.xlsx/.xls/.csv), "
                     "PowerPoint (.pptx/.ppt), Microsoft Project (.mpp), SQLite (.db/.sqlite), Markdown y texto. "
                     "Si `has_more` es true, vuelve a llamar con `offset=next_offset` para seguir leyendo."),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del archivo."},
                "offset": {"type": "integer", "description": "Carácter desde el que leer (por defecto 0)."},
                "max_chars": {"type": "integer", "description": f"Máximo de caracteres (por defecto {DEFAULT_MAX_CHARS})."},
            },
            "required": ["path"],
        },
        handler=handler,
    )]
