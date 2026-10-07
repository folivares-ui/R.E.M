import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rem.agents.team import Team
from rem.app import make_backend
from rem.backends.openai_compat import (OpenAICompatBackend, from_openai_response, to_openai_messages, to_openai_tools)
from rem.config import Config, ModelConfig
from rem.llm import AnthropicBackend, run_agent
from rem.tools.registry import Tool, ToolRegistry
from rem.tools.web import WebError, assert_public_url, fetch_url, html_to_text, make_web_tools


def test_default_provider_is_free_local():
    m = ModelConfig()
    assert m.provider == "ollama" and "11434" in m.base_url and not m.api_key_env
    assert isinstance(make_backend(m), OpenAICompatBackend)
    with pytest.raises(ValueError):
        make_backend(ModelConfig(provider="inventado"))


def test_translate_messages_both_ways():
    msgs = [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": [{"type": "thinking", "thinking": "x"}, {"type": "text", "text": "voy"},
                                          {"type": "tool_use", "id": "c1", "name": "eco", "input": {"x": 1}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "ok"},
                                     {"type": "tool_result", "tool_use_id": "c2", "content": "mal", "is_error": True}]},
    ]
    out = to_openai_messages("SYS", msgs)
    assert out[0] == {"role": "system", "content": "SYS"}
    assert out[2]["tool_calls"][0]["function"] == {"name": "eco", "arguments": '{"x": 1}'} and out[2]["content"] == "voy"
    assert out[3] == {"role": "tool", "tool_call_id": "c1", "content": "ok"}
    assert out[4]["content"].startswith("[ERROR]")


def test_server_tools_are_dropped_and_schema_mapped():
    tools = to_openai_tools([{"name": "a", "description": "d", "input_schema": {"type": "object"}},
                             {"type": "web_search_20260209", "name": "web_search"}])
    assert [t["function"]["name"] for t in tools] == ["a"]


def test_response_parsing_variants():
    r = from_openai_response({"choices": [{"finish_reason": "stop", "message": {"content": None, "tool_calls": [
        {"function": {"name": "t", "arguments": '{"a": 1}'}}]}}]})
    assert r.stop_reason == "tool_use" and r.content[0]["input"] == {"a": 1} and r.content[0]["id"].startswith("call_")
    bad = from_openai_response({"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [
        {"id": "z", "function": {"name": "t", "arguments": "{roto"}}]}}]})
    assert "_invalid_arguments" in bad.content[0]["input"]
    assert from_openai_response({"choices": [{"finish_reason": "length", "message": {"content": "x"}}]}).stop_reason == "max_tokens"


async def test_invalid_json_arguments_reach_model_as_error():
    class B:
        calls = 0
        async def create(self, **kw):
            B.calls += 1
            return from_openai_response({"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [
                {"id": "z", "function": {"name": "t", "arguments": "{roto"}}]}}]}) if B.calls == 1 else \
                from_openai_response({"choices": [{"finish_reason": "stop", "message": {"content": "listo"}}]})
    msgs = [{"role": "user", "content": "x"}]
    reg = ToolRegistry([Tool("t", "t", {"type": "object", "properties": {}}, lambda a: "no debe ejecutarse")])
    out = await run_agent(B(), model="m", system="s", messages=msgs, tools=reg)
    assert out.text == "listo" and msgs[-2]["content"][0]["is_error"]


class FakeOpenAIServer:
    """Imita Ollama /v1/chat/completions con tool calling; guioniza según quién pregunta."""
    def __init__(self):
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append((self.path, body, self.headers.get("Authorization")))
                is_leader = "Eres Rem" in body["messages"][0]["content"]
                last = body["messages"][-1]
                if is_leader and last["role"] == "user":
                    msg = {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {
                        "name": "delegar", "arguments": json.dumps({"agente": "datos", "tarea": "suma 2+2"})}}]}
                    fin = "tool_calls"
                elif is_leader:
                    msg, fin = {"role": "assistant", "content": "Datos dice: " + last["content"]}, "stop"
                else:
                    msg, fin = {"role": "assistant", "content": "4"}, "stop"
                out = json.dumps({"choices": [{"index": 0, "message": msg, "finish_reason": fin}]}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out)

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_port}/v1"


async def test_team_end_to_end_on_openai_compatible_server(tmp_path, monkeypatch):
    monkeypatch.setenv("MI_CLAVE", "k")
    fs = FakeOpenAIServer()
    try:
        cfg = Config(workspace=tmp_path / "w", base_dir=tmp_path)
        cfg.models.leader = cfg.models.worker = "qwen3:8b"
        team = Team(cfg, OpenAICompatBackend(fs.url, api_key_env="MI_CLAVE"))
        res = await team.chat("¿cuánto es 2+2? pregúntale a datos")
    finally:
        fs.srv.shutdown()
    assert res.text == "Datos dice: 4" and team.delegations == [("datos", "suma 2+2")]
    path, body, auth = fs.requests[0]
    assert path == "/v1/chat/completions" and auth == "Bearer k"
    assert body["model"] == "qwen3:8b" and body["tools"][0]["function"]["name"] in {"delegar", "leer_documento", "consultar_base_de_datos", "buscar_web", "wikipedia"}
    assert all("web_search" != t["function"]["name"] for r in fs.requests for t in r[1].get("tools", []))  # sin herramientas de servidor
    assert "thinking" not in body and "output_config" not in body


async def test_connection_error_is_actionable():
    with pytest.raises(RuntimeError, match="ollama"):
        await OpenAICompatBackend("http://127.0.0.1:9/v1", timeout=2).create(model="m", system="", messages=[{"role": "user", "content": "x"}])


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://localhost:8080", "http://169.254.169.254/latest", "http://10.0.0.5/",
                                 "http://[::1]/", "file:///etc/passwd", "ftp://x/y", "http://0.0.0.0/"])
def test_ssrf_blocked(url):
    with pytest.raises(WebError):
        assert_public_url(url)


def test_fetch_url_refuses_private_without_network():
    with pytest.raises(WebError):
        fetch_url("http://127.0.0.1:1/")


def test_html_to_text_strips_scripts():
    t = html_to_text("<html><head><title>x</title></head><body><script>evil()</script><p>Hola</p><style>a{}</style><p>mundo</p></body></html>")
    assert "Hola" in t and "mundo" in t and "evil" not in t


def test_web_tools_registered_and_search_needs_extra(monkeypatch):
    names = {t.name for t in make_web_tools()}
    assert names == {"buscar_web", "wikipedia", "leer_url"}


def test_think_tags_are_stripped_from_visible_text():
    def r(c):
        return from_openai_response({"choices": [{"finish_reason": "stop", "message": {"content": c}}]}).content
    assert r("<think>razono\nmucho</think>\n\nHola") == [{"type": "text", "text": "Hola"}]
    assert r("pensamiento sin apertura</think>Hola") == [{"type": "text", "text": "Hola"}]
    assert r("<think>solo pienso</think>") == []
    assert r("Texto normal") == [{"type": "text", "text": "Texto normal"}]
