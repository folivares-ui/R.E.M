"""Backend para modelos GRATUITOS: cualquier servidor compatible con la API de chat de OpenAI.

Sirve para Ollama (local, `http://127.0.0.1:11434/v1`), llama.cpp `llama-server`, LM Studio, vLLM, y también para
servicios en la nube con capa gratuita que ofrezcan ese formato (OpenRouter `:free`, Groq, Gemini...).

Traduce en ambos sentidos entre el formato interno (bloques tipo Anthropic: text / tool_use / tool_result) y el de
OpenAI (messages + tool_calls), de modo que el bucle de agente (`rem/llm.py`) no cambia.
Se ignoran parámetros propios de Anthropic (`thinking`, `output_config`) y las herramientas de servidor
(web_search...), que aquí no existen: la búsqueda web la hacen herramientas locales (`buscar_web`).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from types import SimpleNamespace
from typing import Any

_THINK = re.compile(r"<think>.*?</think>\s*", re.S)
FINISH_MAP = {"stop": "end_turn", "tool_calls": "tool_use", "function_call": "tool_use", "length": "max_tokens",
              "content_filter": "refusal"}


def to_openai_messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
    for m in messages:
        role, content = m["role"], m["content"]
        if role == "system":
            out.append({"role": "system", "content": content if isinstance(content, str) else str(content)})
            continue
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        if role == "assistant":
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            calls = [{"id": b["id"], "type": "function",
                      "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False)}}
                     for b in content if b.get("type") == "tool_use"]
            msg: dict[str, Any] = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)  # los bloques `thinking` de otros proveedores se descartan
        else:  # user: tool_result -> un mensaje `tool` por resultado; texto -> user
            texts = []
            for b in content:
                if b.get("type") == "tool_result":
                    c = b.get("content")
                    c = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False, default=str)
                    out.append({"role": "tool", "tool_call_id": b["tool_use_id"],
                                "content": ("[ERROR] " + c) if b.get("is_error") else c})
                elif b.get("type") == "text":
                    texts.append(b["text"])
            if texts:
                out.append({"role": "user", "content": "\n".join(texts)})
    return out


def to_openai_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    res = []
    for t in tools or []:
        if "input_schema" not in t:  # herramienta de servidor de Anthropic: no existe aquí
            continue
        res.append({"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                                      "parameters": t["input_schema"]}})
    return res


def from_openai_response(data: dict[str, Any]) -> Any:
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    blocks: list[dict[str, Any]] = []
    # Algunos modelos (p. ej. Qwen3 en modo razonamiento) incluyen su cadena de pensamiento entre <think>: no es para el usuario.
    content = _THINK.sub("", msg.get("content") or "")
    content = re.sub(r"^.*?</think>\s*", "", content, flags=re.S) if "</think>" in content else content
    if content.strip():
        blocks.append({"type": "text", "text": content.strip()})
    for call in msg.get("tool_calls") or []:
        fn = call.get("function") or {}
        raw = fn.get("arguments")
        if isinstance(raw, dict):
            args: Any = raw
        else:
            try:
                args = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                args = {"_invalid_arguments": str(raw)[:500]}
        blocks.append({"type": "tool_use", "id": call.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                       "name": fn.get("name", ""), "input": args})
    stop = FINISH_MAP.get(choice.get("finish_reason") or "stop", "end_turn")
    if any(b["type"] == "tool_use" for b in blocks):
        stop = "tool_use"  # algunos servidores devuelven "stop" aun con tool_calls
    return SimpleNamespace(content=blocks, stop_reason=stop, usage=data.get("usage"))


class OpenAICompatBackend:
    supports_server_tools = False

    def __init__(self, base_url: str = "http://127.0.0.1:11434/v1", api_key_env: str = "", timeout: int = 900,
                 temperature: float | None = 0.3, max_tokens: int = 4096, extra_body: dict[str, Any] | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key_env, self.timeout, self.temperature = api_key_env, timeout, temperature
        self.max_tokens, self.extra_body = max_tokens, extra_body or {}

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env) if self.api_key_env else None
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(body).encode("utf-8"),
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 - URL configurada por el usuario
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"El servidor de modelos respondió {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"No se pudo conectar con {self.base_url} ({exc.reason}). "
                               "¿Está en marcha Ollama (`ollama serve`) y descargaste el modelo?") from exc

    async def create(self, **kw: Any) -> Any:
        body: dict[str, Any] = {
            "model": kw["model"],
            "messages": to_openai_messages(kw.get("system", ""), kw["messages"]),
            "max_tokens": min(int(kw.get("max_tokens", self.max_tokens)), self.max_tokens),
            "stream": False,
            **self.extra_body,
        }
        if self.temperature is not None:
            body["temperature"] = self.temperature
        tools = to_openai_tools(kw.get("tools"))
        if tools:
            body["tools"] = tools
        data = await asyncio.to_thread(self._post, body)
        return from_openai_response(data)
