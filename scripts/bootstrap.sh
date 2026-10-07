#!/usr/bin/env bash
# Descarga (sin copiar al repositorio) las tres bases en vendor/ en las versiones con las que se probó R.E.M.
# Licencias: AIRI (MIT), God's Eye View (MIT), OpenMausBot (Apache-2.0, salvo la carpeta enterprise/).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p vendor

fetch() { # nombre url sha
  local dir="vendor/$1"
  if [ ! -d "$dir/.git" ]; then git clone "$2" "$dir"; fi
  git -C "$dir" fetch --depth=1 origin "$3" 2>/dev/null || git -C "$dir" fetch origin
  git -C "$dir" checkout --quiet "$3"
  echo "✔ $1 @ $3"
}

GIT_LFS_SKIP_SMUDGE=1 fetch airi             https://github.com/moeru-ai/airi                     60d73ccd52ccf29e1528a98eb4428606f4051577
GIT_LFS_SKIP_SMUDGE=1 fetch gods-eye-view    https://github.com/bilawalsidhu/gods-eye-view        e685449a52550775a5279cef1b9090ef24d507a2
GIT_LFS_SKIP_SMUDGE=1 fetch OpenMausBot      https://github.com/milind-soni/OpenMausBot           37b059690d88ad27ef8faed327d3e0e373ca0a36

cat <<'MSG'

Siguientes pasos (ver README.md):
  (cd vendor/gods-eye-view && npm install && npm run dev)     # globo 3D + datos; requiere Node >= 24.14 según su package.json
  (cd vendor/OpenMausBot  && pnpm install && pnpm dev)         # app de bots (revisa su README)
  (cd vendor/airi         && pnpm install && pnpm dev)         # avatar (revisa su README/AGENTS.md)
  python -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
  rem serve                                                    # cerebro R.E.M en http://127.0.0.1:8765/v1
MSG
