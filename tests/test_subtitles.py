import asyncio

from starlette.testclient import TestClient

from conftest import FakeBackend, resp, text_block
from rem.agents.team import Team
from rem.bridge.server import build_app
from rem.bridge.subtitles import SubtitleHub, split_cues
from rem.config import Config


def test_split_cues_sentences_and_long_lines():
    cues = split_cues("Hola. ¿Cómo estás? " + "palabra " * 30)
    assert [c.text for c in cues[:2]] == ["Hola.", "¿Cómo estás?"]
    assert all(len(c.text) <= 84 for c in cues) and len(cues) >= 4
    assert " ".join(c.text for c in cues).split() == ("Hola. ¿Cómo estás? " + "palabra " * 30).split()  # nada se pierde
    assert cues[1].start == cues[0].duration and all(c.duration >= 1.2 for c in cues)
    assert split_cues("   ") == []


async def test_hub_broadcasts_and_slow_viewer_never_blocks():
    hub = SubtitleHub(); q = hub.subscribe()
    for i in range(20):
        hub.publish(f"Frase {i}.")            # el visor no consume: no debe bloquear ni crecer sin límite
    assert q.qsize() <= 8
    assert (await asyncio.wait_for(q.get(), 1))[0]["text"].startswith("Frase")
    hub.unsubscribe(q)


def test_chat_publishes_clean_subtitles_and_overlay_served(tmp_path):
    be = FakeBackend(lambda kw: resp([text_block('<|ACT {"emotion":{"name":"happy","intensity":1}}|>Hola, soy Rem.')], "end_turn"))
    c = TestClient(build_app(Team(Config(workspace=tmp_path / "w", base_dir=tmp_path), be)))
    c.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]})
    last = c.get("/subtitles/last").json()
    assert [x["text"] for x in last] == ["Hola, soy Rem."]          # sin etiquetas <|ACT|>
    html = c.get("/subtitles")
    assert html.status_code == 200 and "EventSource('/subtitles/stream')" in html.text
