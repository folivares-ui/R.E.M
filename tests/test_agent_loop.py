from rem.config import Config
from rem.agents.team import Team
from rem.agents.specialists import SPECIALISTS
from rem.llm import run_agent
from rem.tools.registry import Tool, ToolRegistry
from conftest import FakeBackend, resp, text_block, tool_use


async def test_tool_loop_returns_all_results_in_one_message():
    seen = []
    reg = ToolRegistry([Tool("eco", "eco", {"type": "object", "properties": {}}, lambda a: seen.append(a) or f"eco:{a['x']}")])
    be = FakeBackend([
        resp([tool_use("t1", "eco", {"x": 1}), tool_use("t2", "eco", {"x": 2})], "tool_use"),
        resp([text_block("listo")], "end_turn"),
    ])
    msgs = [{"role": "user", "content": "hola"}]
    out = await run_agent(be, model="m", system="s", messages=msgs, tools=reg)
    assert out.text == "listo" and out.tool_calls == ["eco", "eco"]
    results = msgs[-2]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"] and msgs[-2]["role"] == "user"
    # parámetros de API: thinking adaptativo, sin tool_choice forzado, sin budget_tokens
    kw = be.calls[0]
    assert kw["thinking"] == {"type": "adaptive"} and "tool_choice" not in kw


async def test_tool_error_goes_back_to_model():
    def boom(a):
        raise ValueError("falló")
    reg = ToolRegistry([Tool("x", "x", {"type": "object", "properties": {}}, boom)])
    be = FakeBackend([resp([tool_use("t", "x", {})], "tool_use"), resp([text_block("ok")], "end_turn")])
    msgs = [{"role": "user", "content": "a"}]
    await run_agent(be, model="m", system="s", messages=msgs, tools=reg)
    r = msgs[-2]["content"][0]
    assert r["is_error"] and "falló" in r["content"]


async def test_pause_turn_continues_and_refusal_is_handled():
    be = FakeBackend([resp([text_block("...")], "pause_turn"), resp([text_block("fin")], "end_turn")])
    out = await run_agent(be, model="m", system="s", messages=[{"role": "user", "content": "q"}])
    assert out.text == "fin" and out.turns == 2
    be2 = FakeBackend([resp([], "refusal")])
    out2 = await run_agent(be2, model="m", system="s", messages=[{"role": "user", "content": "q"}])
    assert out2.stop_reason == "refusal"


async def test_leader_delegates_in_parallel_to_specialists(tmp_path):
    cfg = Config(workspace=tmp_path / "ws", base_dir=tmp_path)
    cfg.models.leader, cfg.models.worker = "LEADER", "WORKER"

    def script(kw):
        if kw["model"] == "LEADER":
            last = kw["messages"][-1]
            if last["role"] == "user" and isinstance(last["content"], str):
                return resp([
                    tool_use("a", "delegar", {"agente": "abogado", "tarea": "¿cláusula X?"}),
                    tool_use("b", "delegar", {"agente": "datos", "tarea": "resume ventas"}),
                ], "tool_use")
            return resp([text_block("Síntesis final")], "end_turn")
        return resp([text_block(f"respuesta de {kw['system'][:20]}")], "end_turn")

    be = FakeBackend(script)
    team = Team(cfg, be)
    res = await team.chat("necesito legal y datos")
    assert res.text == "Síntesis final"
    assert {a for a, _ in team.delegations} == {"abogado", "datos"}
    worker_calls = [c for c in be.calls if c["model"] == "WORKER"]
    assert len(worker_calls) == 2
    # los especialistas con búsqueda web la reciben como herramienta de servidor; "datos" no
    def tools_of(keyword):
        c = next(c for c in worker_calls if keyword in c["system"])
        return [t.get("name") for t in c.get("tools", [])]

    assert "web_search" in tools_of("abogado")
    assert "web_search" not in tools_of("analista de datos")
    assert "consultar_base_de_datos" in tools_of("analista de datos")


def test_six_specialists_exist():
    assert set(SPECIALISTS) == {"ciencia_ingenieria", "investigacion", "datos", "programador", "abogado", "marketing"}
