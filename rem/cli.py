"""CLI: `rem chat | serve | read | faces | live`."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from .app import build_team
from .config import load_config
from .stage import strip_stage_tokens
from .tools.documents import read_document


async def _chat(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    async with build_team(cfg) as (team, gate, hub):
        for k, e in hub.errors.items():
            print(f"[aviso] MCP {k} no disponible: {e}", file=sys.stderr)
        print(f"{cfg.name}: Hola, soy {cfg.name}. (Ctrl+D para salir)")
        while True:
            try:
                text = input("tú> ")
            except EOFError:
                break
            if not text.strip():
                continue
            gate.note_user_message(text)
            res = await team.chat(text)
            print(f"{cfg.name}> {strip_stage_tokens(res.text)}")


async def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    from .bridge.server import PerceptionBuffer, build_app
    from .voice.tts import make_tts

    cfg = load_config(args.config)
    async with build_team(cfg) as (team, _gate, hub):
        for k, e in hub.errors.items():
            logging.warning("MCP %s no disponible: %s", k, e)
        app = build_app(team, make_tts(cfg.voice), PerceptionBuffer())
        server = uvicorn.Server(uvicorn.Config(app, host=cfg.bridge["host"], port=int(cfg.bridge["port"]), log_level="info"))
        await server.serve()


def _read(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    root = cfg.resolve(cfg.documents_root) if cfg.documents_root else None
    res = read_document(args.path, root, args.offset, args.max_chars)
    print(json.dumps(res, ensure_ascii=False, indent=2))


def _faces(args: argparse.Namespace) -> None:
    from .perception.faces import FaceRegistry

    cfg = load_config(args.config)
    reg = FaceRegistry(cfg.resolve(cfg.data_dir) / "faces")
    if args.action == "list":
        print("\n".join(reg.people()) or "(nadie inscrito)")
    elif args.action == "forget":
        print("Borrado." if reg.forget(args.name) else "No existía.")
    elif args.action == "enroll":
        if not args.consent:
            sys.exit("Falta --consent: la persona debe aceptar explícitamente que se guarde su vector facial.")
        import cv2  # type: ignore[import-not-found]

        from .perception.faces import FaceEmbedder

        cap = cv2.VideoCapture(int(cfg.perception.get("camera_index", 0)))
        ok, frame = cap.read()
        cap.release()
        if not ok:
            sys.exit("No se pudo leer la cámara.")
        embs = FaceEmbedder().embeddings(frame)
        if len(embs) != 1:
            sys.exit(f"Se esperaba exactamente 1 rostro y se detectaron {len(embs)}.")
        reg.enroll(args.name, embs[0], consent=True)
        print(f"Inscrito: {args.name}")


def _voice(args: argparse.Namespace) -> None:
    """Prueba de voces predefinidas (sin clonación): genera muestras para que elijas la que más te guste."""
    from .voice.tts import KokoroTTS

    cfg = load_config(args.config)
    v = cfg.voice
    tts = KokoroTTS(str(cfg.resolve(v.get("kokoro_model", "models/kokoro-v1.0.int8.onnx"))),
                    str(cfg.resolve(v.get("kokoro_voices", "models/voices-v1.0.bin"))),
                    lang=v.get("kokoro_lang", "es"))
    if args.action == "list":
        print("\n".join(sorted(x for x in tts._engine().get_voices() if x[:2] in ("ef", "em"))))
        return
    import shutil

    out = cfg.resolve(cfg.data_dir) / "voice_demo"
    out.mkdir(parents=True, exist_ok=True)
    text = args.text or "Hola, soy Rem. Estoy lista para ayudarte con lo que necesites."
    for voice in ("ef_dora", "em_alex", "em_santa"):
        for speed in (0.9, 1.0, 1.1):
            tts.speed = speed
            wav = tts.synthesize(text, voice)
            if wav:
                shutil.move(str(wav), out / f"{voice}_x{speed}.wav")
    print(f"Muestras en {out}  (escúchalas y elige: voice.kokoro_voice y voice.kokoro_speed en config/rem.yaml)")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="rem")
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("chat", help="Conversar por terminal")
    sub.add_parser("serve", help="Servir el puente OpenAI-compatible para AIRI")
    r = sub.add_parser("read", help="Probar la lectura de un documento")
    r.add_argument("path")
    r.add_argument("--offset", type=int, default=0)
    r.add_argument("--max-chars", type=int, default=60000)
    f = sub.add_parser("faces", help="Gestionar rostros inscritos (con consentimiento)")
    f.add_argument("action", choices=["list", "enroll", "forget"])
    f.add_argument("name", nargs="?")
    f.add_argument("--consent", action="store_true")
    v = sub.add_parser("voice", help="Probar las voces predefinidas (list | demo)")
    v.add_argument("action", choices=["list", "demo"])
    v.add_argument("--text", default="")
    sub.add_parser("live", help="Micrófono + cámara + llamada por nombre (requiere extras)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if args.cmd == "chat":
        asyncio.run(_chat(args))
    elif args.cmd == "serve":
        asyncio.run(_serve(args))
    elif args.cmd == "read":
        _read(args)
    elif args.cmd == "faces":
        _faces(args)
    elif args.cmd == "voice":
        _voice(args)
    elif args.cmd == "live":
        from .live import run_live

        asyncio.run(run_live(args.config))


if __name__ == "__main__":
    main()
