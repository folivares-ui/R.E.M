# R.E.M

Prototipo privado de avatar de IA multiagente. **Sin fines de lucro; no es una distribución pública.**
Personalidad inspirada en Rem (Re:Zero) — ver `rem/persona.py` (escrita desde mi conocimiento general del personaje, sin citar diálogos; ajústala).

## Arquitectura

```
 ┌──────────── AIRI (cuerpo) ────────────┐        ┌────────────── R.E.M (cerebro, Python) ──────────────┐
 │ Avatar Live2D/VRM, voz, micrófono,    │  HTTP  │  Puente OpenAI-compatible  /v1/chat/completions     │
 │ animaciones por <|ACT {...}|>         │◄──────►│            │                                        │
 └───────────────────────────────────────┘        │      Rem (líder, claude-opus-5-5)                   │
                                                  │   delega en paralelo con `delegar` ─┐               │
   Cámara/mic (rem live) ── POST /events ───────► │  ciencia_ingenieria · investigacion │ (claude-      │
                                                  │  datos · programador · abogado ·    │  sonnet-5-5)  │
                                                  │  marketing                          ┘               │
                                                  │   Herramientas: leer_documento, consultar_base_de_  │
                                                  │   datos, workspace_*, web_search (servidor) y MCP:  │
                                                  │   • God's Eye View (gev__*)  • OpenMausBot (maus__*)│
                                                  └──────────────────────────────────────────────────────┘
```

- **AIRI** (MIT) aporta el avatar, la voz y la animación. AIRI define un proveedor `openai-compatible`;
  R.E.M se registra como tal (`http://127.0.0.1:8765/v1/`, modelo `rem`).
- **God's Eye View** (MIT) y **OpenMausBot** (Apache-2.0; su carpeta `enterprise/` tiene otra licencia, no se usa) se consumen
  **por sus servidores MCP** (stdio). No se copia su código: `scripts/bootstrap.sh` los descarga a `vendor/` (git-ignorado) en versiones fijadas.
- Las herramientas con efectos externos (p. ej. enviar trabajo a un bot de OpenMausBot) **piden confirmación humana**:
  la llamada se bloquea, Rem te pregunta, y solo tras tu "sí" se permite esa misma llamada, una vez (`rem/tools/confirm.py`).

## Los seis especialistas (`rem/agents/specialists.py`)
| id | Rol | Herramientas propias |
|---|---|---|
| `ciencia_ingenieria` | Ciencia e ingeniería | documentos, workspace |
| `investigacion` | Investigación especializada | documentos, búsqueda web |
| `datos` | Analista de datos | documentos, SQL de solo lectura, workspace |
| `programador` | Programación | documentos, workspace (lectura/escritura confinada), búsqueda web |
| `abogado` | Orientación jurídica (informativa) | documentos, búsqueda web |
| `marketing` | Audiencia y marca | documentos, búsqueda web |

Todos comparten reglas de honestidad (no inventar datos/fuentes/APIs, marcar incertidumbre, preguntar si falta información).

## Formatos de documentos
PDF, Word (`.docx`, `.doc` vía LibreOffice), Excel (`.xlsx`, `.xls` vía LibreOffice, `.csv`), PowerPoint (`.pptx`, `.ppt` vía LibreOffice),
Microsoft Project (`.mpp` vía MPXJ + Java), SQLite, Markdown/texto/código. Otras bases (PostgreSQL, MySQL, DuckDB...) con `consultar_base_de_datos`
(SQLAlchemy; usa credenciales de solo lectura). La salida nunca se trunca en silencio (`has_more`/`next_offset`).
**`.doe`**: no reconozco ese formato; el lector pide aclarar (¿`.doc`/`.docx`?).

## Puesta en marcha
```bash
bash scripts/bootstrap.sh                      # descarga AIRI, God's Eye View y OpenMausBot en vendor/
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'                        # núcleo; extras: vision, faces, voice, project, dbs
export ANTHROPIC_API_KEY=...                   # o `ant auth login`
rem chat                                       # probar por terminal
rem serve                                      # puente para AIRI
```
Activa los MCP en `config/rem.yaml` (`enabled: true`) tras arrancar God's Eye View (`npm run dev` en `vendor/gods-eye-view`)
y OpenMausBot. Percepción y voz: `docs/PERCEPCION.md`, `docs/VOZ.md`.

## Qué está verificado y qué no (honestidad)
| Pieza | Estado |
|---|---|
| Bucle de agente, delegación en paralelo, manejo de errores/`pause_turn`/rechazos | ✅ pruebas automáticas con un LLM simulado |
| Lectores PDF/DOCX/XLSX/PPTX/CSV/SQLite/`.mpp`(MSPDI)/`.doc`(LibreOffice), confinamiento de rutas, SQL de solo lectura | ✅ pruebas automáticas |
| Puente MCP | ✅ contra un servidor MCP de prueba **y contra el servidor real de God's Eye View** (se listan sus 30 herramientas; no se llamó a ninguna con datos en vivo) |
| Puente OpenAI-compatible (stream y no stream), eventos de percepción, auth opcional | ✅ pruebas automáticas |
| Llamada real a la API de Claude | ❌ **no probada** (sin clave en este entorno). Los parámetros siguen la documentación del SDK (`thinking: adaptive`, `output_config.effort`, `fallbacks` beta, `web_search_20260209`); verifica con una primera consulta real |
| Conexión AIRI ↔ R.E.M en la interfaz de AIRI | ❌ no probada (no se levantó AIRI). Los nombres exactos de campos de su UI deben comprobarse |
| OpenMausBot MCP | ❌ no ejecutado (requiere su app/harness y emparejamiento; ver su `docs/mcp-server.md`) |
| Cámara, rostros, gestos, micrófono, STT, TTS | ❌ escritos, **no ejecutados** (sin hardware). La lógica pura sí tiene tests |
| Subtítulos (overlay + SSE) y TTS por API HTTP configurable | ✅ probados con servidor real/local de prueba; ❌ ningún proveedor de voz real probado |
| Clonar-voz como motor de voz (`tts_provider: clonar_voz`) | ✅ contrato HTTP contra su `app.py` real con `llama-tts` falso; ❌ modelo Qwen3-TTS real no probado |
| Voz de Rem | ⛔ no clonada (ver `docs/VOZ.md`) |

## Pruebas
```bash
pytest -q        # 53 pruebas
```
