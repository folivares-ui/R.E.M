"""Carga de configuración (YAML) a dataclasses simples."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ModelConfig:
    leader: str = "claude-opus-5-5"
    worker: str = "claude-sonnet-5-5"
    leader_effort: str = "medium"
    worker_effort: str = "medium"
    fallbacks: bool = True


@dataclass
class McpServerConfig:
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    prefix: str = ""
    enabled: bool = False


@dataclass
class Config:
    name: str = "Rem"
    wake_names: list[str] = field(default_factory=lambda: ["rem"])
    language: str = "es"
    models: ModelConfig = field(default_factory=ModelConfig)
    workspace: Path = Path("workspace")
    data_dir: Path = Path("data")
    documents_root: Path | None = None
    mcp_servers: dict[str, McpServerConfig] = field(default_factory=dict)
    perception: dict[str, Any] = field(default_factory=dict)
    voice: dict[str, Any] = field(default_factory=dict)
    bridge: dict[str, Any] = field(default_factory=lambda: {"host": "127.0.0.1", "port": 8765})
    base_dir: Path = Path(".")

    def resolve(self, p: str | Path) -> Path:
        p = Path(p)
        return p if p.is_absolute() else (self.base_dir / p)


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path or os.environ.get("REM_CONFIG", "config/rem.yaml"))
    raw: dict[str, Any] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    base = path.resolve().parent.parent if path.exists() else Path.cwd()
    models = ModelConfig(**{k: v for k, v in (raw.get("models") or {}).items() if k in ModelConfig.__dataclass_fields__})
    paths = raw.get("paths") or {}
    servers = {}
    for key, spec in (raw.get("mcp_servers") or {}).items():
        servers[key] = McpServerConfig(
            command=spec["command"],
            args=list(spec.get("args") or []),
            env={k: str(v) for k, v in (spec.get("env") or {}).items()},
            prefix=spec.get("prefix") or key,
            enabled=bool(spec.get("enabled", False)),
        )
    docs_root = paths.get("documents_root")
    return Config(
        name=raw.get("name", "Rem"),
        wake_names=[w.lower() for w in raw.get("wake_names", ["rem"])],
        language=raw.get("language", "es"),
        models=models,
        workspace=Path(paths.get("workspace", "workspace")),
        data_dir=Path(paths.get("data", "data")),
        documents_root=Path(docs_root) if docs_root else None,
        mcp_servers=servers,
        perception=raw.get("perception") or {},
        voice=raw.get("voice") or {},
        bridge={**{"host": "127.0.0.1", "port": 8765}, **(raw.get("bridge") or {})},
        base_dir=base,
    )
