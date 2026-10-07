import json

import pytest
from starlette.testclient import TestClient

from conftest import FakeBackend, resp, text_block
from rem.agents.team import Team
from rem.bridge.server import PerceptionBuffer, build_app, messages_to_history
from rem.config import Config


def make(tmp_path, answer="Hola <|ACT {\"emotion\":{\"name\":\"happy\",\"intensity\":1}}|>mundo", clock=None):
    be = FakeBackend(lambda kw: resp([text_block(answer)], "end_turn"))
    team = Team(Config(workspace=tmp_path / "ws", base_dir=tmp_path), be)
    buf = PerceptionBuffer(clock=clock) if clock else PerceptionBuffer()
    return TestClient(build_app(team, perception=buf)), be, buf


def test_messages_to_history_ignores_airi_system_and_merges():
    hist, last = messages_to_history([
        {"role": "system", "content": "otro personaje"},
        {"role": "user", "content": "a"}, {"role": "user", "content": [{"type": "text", "text": "b"}]},
        {"role": "assistant", "content": "r"}, {"role": "user", "content": "¿y ahora?"},
    ])
    assert hist == [{"role": "user", "content": "a\nb"}, {"role": "assistant", "content": "r"}] and last == "¿y ahora?"
    with pytest.raises(ValueError):
        messages_to_history([{"role": "assistant", "content": "x"}])


def test_chat_non_stream_and_system_prompt_has_stage_addendum(tmp_path):
    c, be, _ = make(tmp_path)
    r = c.post("/v1/chat/completions", json={"model": "rem", "messages": [{"role": "user", "content": "hola"}]})
    j = r.json()
    assert r.status_code == 200 and j["choices"][0]["message"]["content"].startswith("Hola")
    assert "<|ACT" in be.calls[0]["system"] and "Eres Rem" in be.calls[0]["system"]


def test_chat_stream_sse_format(tmp_path):
    c, _, _ = make(tmp_path, answer="Buenas")
    r = c.post("/v1/chat/completions", json={"stream": True, "messages": [{"role": "user", "content": "hola"}]})
    lines = [l for l in r.text.split("\n\n") if l]
    assert lines[-1] == "data: [DONE]"
    chunks = [json.loads(l[6:]) for l in lines[:-1]]
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    assert "".join(ch["choices"][0]["delta"].get("content", "") for ch in chunks) == "Buenas"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"


def test_perception_events_reach_next_turn_and_expire(tmp_path):
    t = [0.0]
    c, be, _ = make(tmp_path, clock=lambda: t[0])
    c.post("/events", json={"kind": "persona", "data": {"name": "Ana"}})
    c.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]})
    assert "Ana" in be.calls[-1]["system"]
    t[0] = 1000.0                                            # pasado el TTL
    c.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]})
    assert "Ana" not in be.calls[-1]["system"]


def test_bad_request_and_auth(tmp_path, monkeypatch):
    c, _, _ = make(tmp_path)
    assert c.post("/v1/chat/completions", json={"messages": []}).status_code == 400
    assert c.get("/v1/models").json()["data"][0]["id"] == "rem"
    monkeypatch.setenv("REM_BRIDGE_TOKEN", "s3")
    c2, _, _ = make(tmp_path)
    assert c2.get("/v1/models").status_code == 401
    assert c2.get("/v1/models", headers={"Authorization": "Bearer s3"}).status_code == 200


def test_speech_501_without_tts(tmp_path):
    c, _, _ = make(tmp_path)
    assert c.post("/v1/audio/speech", json={"input": "hola"}).status_code == 501
