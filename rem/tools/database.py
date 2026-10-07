"""Consultas de solo lectura a bases de datos (SQLite nativo; el resto vía SQLAlchemy).

Salvaguardas: solo SELECT/WITH/PRAGMA table_info/EXPLAIN, una sola sentencia, límite de filas.
La salvaguarda de texto NO sustituye a un usuario de base de datos con permisos de solo lectura:
para PostgreSQL/MySQL/SQL Server usa credenciales de solo lectura.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from .registry import Tool

MAX_ROWS = 200
_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|replace\s+into|truncate|attach|detach|vacuum|grant|revoke|merge|call|exec|execute)\b", re.I)


def validate_readonly_sql(sql: str) -> str:
    s = sql.strip().rstrip(";").strip()
    if not s:
        raise ValueError("Consulta vacía.")
    if ";" in s:
        raise ValueError("Solo se permite una sentencia.")
    s_nocomment = re.sub(r"--[^\n]*|/\*.*?\*/", " ", s, flags=re.S)
    head = s_nocomment.lstrip().split(None, 1)[0].lower()
    if head not in {"select", "with", "explain", "pragma"}:
        raise ValueError("Solo se permiten consultas de lectura (SELECT/WITH/EXPLAIN).")
    if head == "pragma" and not re.match(r"\s*pragma\s+(table_info|table_list|index_list)\b", s_nocomment, re.I):
        raise ValueError("PRAGMA no permitido.")
    if _FORBIDDEN.search(s_nocomment):
        raise ValueError("La consulta contiene palabras reservadas de escritura.")
    return s


def run_query(url: str, sql: str, max_rows: int = MAX_ROWS) -> dict[str, Any]:
    sql = validate_readonly_sql(sql)
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            cur = con.execute(sql)
            cols = [d[0] for d in cur.description or []]
            rows = cur.fetchmany(max_rows + 1)
        finally:
            con.close()
    else:
        try:
            import sqlalchemy as sa
        except ImportError as exc:
            raise RuntimeError("Instala el extra: pip install 'rem-avatar[dbs]' para bases de datos distintas de SQLite.") from exc
        engine = sa.create_engine(url)
        with engine.connect() as conn:
            res = conn.execute(sa.text(sql))
            cols = list(res.keys())
            rows = res.fetchmany(max_rows + 1)
    truncated = len(rows) > max_rows
    return {"columns": cols, "rows": [list(r) for r in rows[:max_rows]], "truncated": truncated, "row_limit": max_rows}


def make_database_tools() -> list[Tool]:
    def handler(a: dict[str, Any]) -> str:
        return json.dumps(run_query(a["url"], a["sql"], int(a.get("max_rows", MAX_ROWS))), ensure_ascii=False, default=str)

    return [Tool(
        name="consultar_base_de_datos",
        description=("Ejecuta UNA consulta de solo lectura (SELECT/WITH) y devuelve columnas y filas (máx. 200). "
                     "`url` es una URL SQLAlchemy: sqlite:///ruta.db, postgresql://..., mysql+pymysql://..., duckdb:///ruta."),
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "sql": {"type": "string"},
                "max_rows": {"type": "integer"},
            },
            "required": ["url", "sql"],
        },
        handler=handler,
    )]
