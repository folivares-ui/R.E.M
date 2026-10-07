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
    """Gestiona las voces de Clonar-voz. Registrar una voz exige constancia de permiso."""
    import time
    from pathlib import Path

    from .voice.tts import ClonarVozTTS

    cfg = load_config(args.config)
    tts = ClonarVozTTS(cfg.voice.get("clonar_voz_url", "http://127.0.0.1:8080"))
    if args.action == "status":
        st = tts.status()
        print(json.dumps({k: st.get(k) for k in ("binario_ok", "version", "soporta_qwen3tts", "modelo_ok", "mmproj_ok", "ffmpeg")}, indent=2))
    elif args.action == "list":
        for v in tts.voices():
            print(f"{v['id']}\t{v.get('nombre')}\t{v.get('duracion')}s")
    elif args.action == "register":
        if not (args.file and args.name):
            sys.exit("Uso: rem voice register --file muestra.wav --name NOMBRE --permission 'quién da el permiso'")
        if not args.permission or len(args.permission.strip()) < 8:
            sys.exit("Falta --permission: indica con claridad que la voz es TUYA o que la persona dio permiso explícito "
                     "(p. ej. 'mi propia voz' o 'María Pérez, autorización por escrito 2026-10-07'). "
                     "No registro voces de terceros sin permiso.")
        v = tts.register_voice(Path(args.file), args.name, args.transcript or "")
        log = cfg.resolve(cfg.data_dir) / "voice_consent.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"voice_id": v["id"], "name": args.name, "permission": args.permission.strip(),
                                "file": Path(args.file).name, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, ensure_ascii=False) + "\n")
        print(f"Voz registrada: id={v['id']}. Ponla en config/rem.yaml -> voice.clonar_voz_voice_id")


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
    v = sub.add_parser("voice", help="Voces de Clonar-voz (con constancia de permiso)")
    v.add_argument("action", choices=["status", "list", "register"])
    v.add_argument("--file")
    v.add_argument("--name")
    v.add_argument("--transcript", default="")
    v.add_argument("--permission", default="")
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
