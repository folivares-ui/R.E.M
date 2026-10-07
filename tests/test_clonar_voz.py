"""Adaptador de Clonar-voz: (1) contra un servidor falso con su API; (2) contra su app.py REAL si está disponible
(REM_CLONAR_VOZ_DIR o vendor/Clonar-voz), con un `llama-tts` falso: prueba el contrato HTTP, no la calidad de la voz."""
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from rem.voice.tts import ClonarVozTTS, make_tts

FAKE_LLAMA = Path(__file__).parent / "fixtures" / "fake_llama_tts.py"


def _wav(path: Path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\x00\x00" * 1600)


def test_rejects_non_local_url():
    with pytest.raises(ValueError):
        ClonarVozTTS("http://ejemplo.com:8080")


def test_against_fake_api_server():
    seen = {}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_POST(self):
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(b'{"id":"t1"}')
        def do_GET(self):
            if self.path == "/api/tarea/t1/eventos":
                self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                self.wfile.write(b'data: {"tipo":"bloque"}\n\ndata: {"tipo":"fin","archivo":"a.wav"}\n\n')
            elif self.path == "/api/salidas/a.wav":
                self.send_response(200); self.end_headers(); self.wfile.write(b"RIFFxx")
            else:
                self.send_response(404); self.end_headers()

    srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        t = make_tts({"tts_provider": "clonar_voz", "clonar_voz_url": f"http://127.0.0.1:{srv.server_port}", "clonar_voz_voice_id": "v9"})
        out = t.synthesize("Hola")
    finally:
        srv.shutdown()
    assert out.read_bytes() == b"RIFFxx"
    assert seen["body"] == {"texto": "Hola", "idioma": "es", "dispositivo": "auto", "voz": "v9"}


def _real_dir():
    for c in (os.environ.get("REM_CLONAR_VOZ_DIR"), Path(__file__).parent.parent / "vendor" / "Clonar-voz"):
        if c and (Path(c) / "app.py").exists():
            return Path(c)
    return None


@pytest.mark.skipif(_real_dir() is None or not shutil.which("python3"), reason="Clonar-voz no disponible")
def test_against_real_clonar_voz_app(tmp_path):
    pytest.importorskip("fastapi"); pytest.importorskip("multipart")
    work = tmp_path / "cv"
    shutil.copytree(_real_dir(), work, ignore=shutil.ignore_patterns(".git", "docs"))
    (work / "modelo").mkdir(exist_ok=True)
    (work / "modelo" / "m.gguf").write_bytes(b"x"); (work / "modelo" / "mmproj-m.gguf").write_bytes(b"x")
    fake = work / "llama-tts"
    fake.write_text(f"#!/bin/sh\nexec {sys.executable} {FAKE_LLAMA} \"$@\"\n"); fake.chmod(0o755)
    (work / "config.json").write_text(json.dumps({"binario": str(fake)}))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    env = {**os.environ, "PUERTO": str(port)}
    proc = subprocess.Popen([sys.executable, "app.py"], cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        t = ClonarVozTTS(f"http://127.0.0.1:{port}")
        for _ in range(60):
            try:
                st = t.status(); break
            except Exception:
                time.sleep(0.25)
        else:
            pytest.fail("app.py no arrancó: " + proc.stdout.read(2000).decode())
        assert st["binario_ok"] and st["soporta_qwen3tts"] and st["modelo_ok"] and st["mmproj_ok"]
        ref = tmp_path / "ref.wav"; _wav(ref)
        v = t.register_voice(ref, "Mi voz de prueba", "hola")           # API real: multipart
        assert any(x["id"] == v["id"] for x in t.voices())
        t.voice_id = v["id"]
        out = t.synthesize("Hola, esto es una prueba de integración.")
        with wave.open(str(out)) as w:
            assert w.getnframes() > 0
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_register_requires_permission_statement(tmp_path, monkeypatch):
    from rem.cli import main
    monkeypatch.chdir(tmp_path)
    ref = tmp_path / "m.wav"; _wav(ref)
    for perm in ([], ["--permission", "ok"]):
        with pytest.raises(SystemExit) as e:
            main(["voice", "register", "--file", str(ref), "--name", "X", *perm])
        assert "permiso" in str(e.value).lower() or "permission" in str(e.value).lower()
