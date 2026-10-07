"""Rem (líder) + especialistas: orquestación con delegación en paralelo."""
from __future__ import annotations

import logging
from typing import Any

from ..config import Config
from ..llm import AgentResult, MessagesClient, run_agent
from ..persona import REM_PERSONA
from ..tools.database import make_database_tools
from ..tools.documents import make_document_tools
from ..tools.registry import Tool, ToolRegistry
from ..tools.workspace import make_workspace_tools
from .specialists import SPECIALISTS, SpecialistSpec

log = logging.getLogger("rem.team")


class Team:
    def __init__(self, cfg: Config, backend: MessagesClient, extra_leader_tools: ToolRegistry | None = None):
        self.cfg = cfg
        self.backend = backend
        root = cfg.resolve(cfg.documents_root) if cfg.documents_root else None
        self._local = ToolRegistry()
        for t in (*make_document_tools(root), *make_database_tools(), *make_workspace_tools(cfg.resolve(cfg.workspace))):
            self._local.add(t)
        self._extra = extra_leader_tools or ToolRegistry()
        self.history: list[dict[str, Any]] = []
        self.delegations: list[tuple[str, str]] = []  # bitácora (agente, tarea) para auditoría/pruebas

    # --- especialistas ---------------------------------------------------------------------
    def _registry_for(self, spec: SpecialistSpec) -> ToolRegistry:
        reg = ToolRegistry()
        for name in spec.local_tools:
            reg.add(self._local._tools[name])
        return reg

    async def run_specialist(self, agent_id: str, task: str, context: str = "") -> str:
        spec = SPECIALISTS.get(agent_id)
        if spec is None:
            raise ValueError(f"Especialista desconocido: {agent_id}. Opciones: {', '.join(SPECIALISTS)}")
        self.delegations.append((agent_id, task))
        prompt = task if not context else f"Contexto:\n{context}\n\nTarea:\n{task}"
        res = await run_agent(
            self.backend,
            model=self.cfg.models.worker,
            system=spec.system,
            messages=[{"role": "user", "content": prompt}],
            tools=self._registry_for(spec),
            server_tools=list(spec.server_tools),
            effort=spec.effort or self.cfg.models.worker_effort,
        )
        return res.text or "(el especialista no devolvió texto)"

    # --- líder -----------------------------------------------------------------------------
    def _delegate_tool(self) -> Tool:
        async def handler(a: dict[str, Any]) -> str:
            return await self.run_specialist(a["agente"], a["tarea"], a.get("contexto", ""))

        return Tool(
            name="delegar",
            description=("Encarga una tarea a un especialista y devuelve su respuesta. Para varias tareas "
                         "independientes, llama a `delegar` varias veces en el mismo turno (se ejecutan en paralelo). "
                         "La tarea debe ser autosuficiente: el especialista no ve la conversación."),
            input_schema={
                "type": "object",
                "properties": {
                    "agente": {"type": "string", "enum": list(SPECIALISTS)},
                    "tarea": {"type": "string", "description": "Instrucción completa y autosuficiente."},
                    "contexto": {"type": "string", "description": "Datos relevantes (extractos de documentos, restricciones)."},
                },
                "required": ["agente", "tarea"],
            },
            handler=handler,
        )

    def leader_tools(self) -> ToolRegistry:
        reg = ToolRegistry([self._delegate_tool()])
        for name in ("leer_documento", "consultar_base_de_datos"):
            reg.add(self._local._tools[name])
        reg.extend(self._extra)
        return reg

    async def chat(self, user_text: str, *, source: str = "texto", history: list[dict[str, Any]] | None = None,
                   system_extra: str = "") -> AgentResult:
        """Un turno con Rem. `history` (opcional) reemplaza la memoria interna: así el puente AIRI es sin estado."""
        note = " (entrada por voz: responde breve)" if source == "voz" else ""
        msgs = self.history if history is None else history
        msgs.append({"role": "user", "content": user_text + note})
        return await run_agent(
            self.backend,
            model=self.cfg.models.leader,
            system=REM_PERSONA + (("\n" + system_extra) if system_extra else ""),
            messages=msgs,
            tools=self.leader_tools(),
            effort=self.cfg.models.leader_effort,
        )
