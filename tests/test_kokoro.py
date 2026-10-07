import hashlib
import os
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from rem.voice.tts import KokoroTTS, make_tts  # noqa: E402


def test_default_voice_provider_has_no_cloning_and_unknown_files_are_actionable(tmp_path):
    t = make_tts({"tts_provider": "kokoro", "kokoro_model": str(tmp_path / "x.onnx"), "kokoro_voices": str(tmp_path / "v.bin")})
    assert isinstance(t, KokoroTTS) and t.voice == "ef_dora"
    pytest.importorskip("kokoro_onnx")
    with pytest.raises(RuntimeError, match="download_kokoro"):
        t.synthesize("hola")
    assert t.synthesize("   ") is None


def test_download_script_rejects_wrong_hash(tmp_path, monkeypatch):
    import download_kokoro as d
    monkeypatch.setattr(d, "FILES", {"a.bin": hashlib.sha256(b"bueno").hexdigest()})

    def fake(url, dest):
        Path(dest).write_bytes(b"MALICIOSO")
    monkeypatch.setattr(d.urllib.request, "urlretrieve", fake)
    assert d.main(tmp_path) == 1 and not (tmp_path / "a.bin").exists() and not list(tmp_path.glob("*.part"))
    monkeypatch.setattr(d.urllib.request, "urlretrieve", lambda u, p: Path(p).write_bytes(b"bueno"))
    assert d.main(tmp_path) == 0 and (tmp_path / "a.bin").read_bytes() == b"bueno"


def _models():
    d = os.environ.get("REM_KOKORO_DIR")
    if d and (Path(d) / "kokoro-v1.0.int8.onnx").exists():
        return Path(d)
    return None


@pytest.mark.skipif(_models() is None, reason="define REM_KOKORO_DIR con los archivos de Kokoro para la prueba real")
def test_real_spanish_synthesis_on_cpu():
    pytest.importorskip("kokoro_onnx")
    d = _models()
    t = KokoroTTS(str(d / "kokoro-v1.0.int8.onnx"), str(d / "voices-v1.0.bin"))
    wav = t.synthesize("Hola, soy Rem. Estoy lista para ayudarte.")
    with wave.open(str(wav)) as w:
        secs = w.getnframes() / w.getframerate()
        data = w.readframes(w.getnframes())
    assert 1.5 < secs < 8 and any(data)                       # audio plausible y no vacío
    assert t.synthesize("Hola", voice="voz_inexistente")      # voz desconocida -> cae a la configurada
