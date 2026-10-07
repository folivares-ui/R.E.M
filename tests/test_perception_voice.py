import pytest

from rem.perception.faces import FaceRegistry
from rem.perception.gestures import Debouncer, gesture_to_intent
from rem.perception.wake import detect_wake
from rem.tools.confirm import ConfirmGate
from rem.voice.tts import CommandTTS, NoTTS, make_tts
from rem.stage import strip_stage_tokens

NAMES = ["rem", "rem-chan"]


@pytest.mark.parametrize("t", ["Rem, lee este PDF", "oye REM", "Hola rem-chan ¿puedes ayudarme?", "rem."])
def test_wake_positive(t):
    assert detect_wake(t, NAMES)[0]


@pytest.mark.parametrize("t", ["hoy hace calor", "el remedio está en la mesa", "ram vino ayer", "regla de tres"])
def test_wake_negative(t):
    assert not detect_wake(t, NAMES)[0]


def test_gesture_map_and_debounce():
    assert gesture_to_intent("Thumb_Up")[0] == "aprobado" and gesture_to_intent("None") is None
    d = Debouncer(frames_required=3, cooldown_frames=5)
    out = [d.update("Open_Palm") for _ in range(4)]
    assert out == [None, None, "Open_Palm", None]       # dispara una vez
    assert d.update(None) is None


def test_face_registry_requires_consent_and_matches(tmp_path):
    reg = FaceRegistry(tmp_path / "faces")
    with pytest.raises(PermissionError):
        reg.enroll("Ana", [1, 0, 0], consent=False)
    assert reg.people() == []
    reg.enroll("Ana", [1, 0, 0], consent=True); reg.enroll("Luis", [0, 1, 0], consent=True)
    assert reg.identify([0.9, 0.1, 0])[0] == "Ana"
    assert reg.identify([0, 0, 1])[0] is None       # desconocido: nunca se asigna a alguien
    assert reg.forget("Ana") and reg.people() == ["Luis"]


async def test_confirm_gate_requires_human_yes():
    g = ConfirmGate()
    args = {"to": "bot", "text": "haz X"}
    assert await g("maus__send", args) is False            # primera vez: pendiente
    assert await g("maus__send", args) is False            # el modelo no se autoaprueba
    g.note_user_message("sí, adelante")
    assert await g("maus__send", {"to": "otro"}) is False  # otra acción no queda aprobada
    g.note_user_message("sí")
    assert await g("maus__send", args) is False            # la aprobación solo cubre lo que estaba pendiente


async def test_confirm_gate_flow():
    g = ConfirmGate(); args = {"a": 1}
    assert await g("t", args) is False
    g.note_user_message("Sí, hazlo")
    assert await g("t", args) is True
    assert await g("t", args) is False                      # un solo uso


async def test_confirm_gate_rejects_negation():
    g = ConfirmGate(); args = {"a": 1}
    await g("t", args); g.note_user_message("sí pero espera")
    assert await g("t", args) is False


def test_tts_providers(tmp_path):
    assert isinstance(make_tts({}), NoTTS)
    with pytest.raises(ValueError):
        CommandTTS("cat")                                    # falta {out}
    wav = CommandTTS("sh -c 'cat > {out}'").synthesize("hola")
    assert wav and wav.read_bytes() == b"hola"
    with pytest.raises(ValueError):
        make_tts({"tts_provider": "inventado"})


def test_strip_stage_tokens():
    s = 'Hola <|ACT {"emotion":{"name":"happy","intensity":1}}|>mundo<|DELAY:1|>'
    assert strip_stage_tokens(s) == "Hola mundo"


def test_http_tts_posts_json_with_bearer_key(monkeypatch):
    import json, threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from rem.voice.tts import HttpTTS
    seen = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["auth"] = self.headers.get("Authorization")
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200); self.send_header("Content-Type", "audio/wav"); self.end_headers(); self.wfile.write(b"RIFFfake")
        def log_message(self, *a): pass

    srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("MI_CLAVE", "abc")
    try:
        t = make_tts({"tts_provider": "http", "tts_url": f"http://127.0.0.1:{srv.server_port}/v1/audio/speech",
                      "tts_api_key_env": "MI_CLAVE", "tts_model": "m", "tts_voice": "v"})
        assert isinstance(t, HttpTTS)
        out = t.synthesize("hola")
    finally:
        srv.shutdown()
    assert out.read_bytes() == b"RIFFfake" and seen["auth"] == "Bearer abc"
    assert seen["body"] == {"input": "hola", "response_format": "wav", "model": "m", "voice": "v"}
    with pytest.raises(ValueError):
        HttpTTS("ftp://x")
