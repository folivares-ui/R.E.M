# Modelos gratuitos para los agentes

**Decisión:** R.E.M usa por defecto modelos **gratuitos y locales** (Ollama). El proveedor de pago (Anthropic) sigue en el código solo como opción
(`models.provider: anthropic`), apagado por defecto.

> ⚠️ **Sobre la fiabilidad de esta lista.** Las fuentes oficiales (ollama.com, Hugging Face, OpenRouter) estaban **bloqueadas desde mi entorno**, así que
> la información viene de blogs y buscadores (fuentes secundarias, algunas con estilo SEO) y puede estar desactualizada. Los nombres de modelo y las cifras
> hay que **verificarlos en ollama.com/library** y con `ollama show <modelo>` antes de descargar varios GB. Hoy es 2026-10-07: este mercado cambia rápido.

## Recomendación (local, $0, tus datos no salen del equipo)
Criterios: llamadas a herramientas nativas (los agentes dependen de ellas), español, licencia permisiva y que quepa en hardware doméstico.

| Rol / hardware | Modelo (etiqueta de Ollama) | Por qué (según las fuentes) |
|---|---|---|
| **Por defecto**, ~6-8 GB de VRAM/RAM | `qwen3:8b` | Qwen3: licencia Apache 2.0, 100+ idiomas (incluye español), llamadas a herramientas nativas en todos los tamaños. ~6 GB a Q4 según una fuente. Un blog lo estima en ~85 % de fiabilidad de tool-calling (dato no contrastado). |
| ~8-12 GB | `qwen3:14b` | Mismo modelo, más capaz (~7,7 GB a Q4_K_M según una fuente; verifícalo). Buen candidato para **Rem (líder)** mientras los especialistas usan `qwen3:8b`. |
| ~16 GB | `gpt-oss:20b` | OpenAI, Apache 2.0, razonamiento y llamadas a funciones nativas; "cabe en 16 GB" gracias a MXFP4 (varias fuentes concuerdan). |
| ~19 GB+ | `qwen3:30b-a3b` | MoE: ~3B activos pero hay que cargar los 30B (~19 GB a Q4_K_M según una fuente); suele ir rápido. |
| Alternativa | Gemma 4 (`gemma4:e4b` y otros) | Citada con llamadas a funciones y licencia Apache 2.0 (según blogs; **la etiqueta exacta y la licencia no las pude verificar**). |

Otros mencionados por las fuentes (no probados): `mistral-small3.2:24b`, `llama3.1:8b`, `granite4`, Hermes 4, GLM/Kimi (muy grandes para casa).

**Configuración mínima**
```bash
ollama pull qwen3:8b          # instala Ollama desde su web oficial
```
`config/rem.yaml` ya apunta a `http://127.0.0.1:11434/v1` con `qwen3:8b`. Para un líder más fuerte: `leader: "qwen3:14b"`.

**Avisos honestos**
- Los modelos pequeños son **menos fiables** que los de frontera para orquestar varios agentes y herramientas: pueden elegir mal la herramienta, devolver JSON
  roto (R.E.M lo detecta y se lo devuelve al modelo como error) o alucinar. Las reglas de honestidad del prompt ayudan pero **no lo garantizan**: verifica lo importante.
- **Contexto:** leer PDFs largos exige una ventana de contexto grande en el servidor de modelos; si es corta se pierde texto. Revisa en la documentación vigente de Ollama
  cómo fijarla (no la configuro por ti).
- `qwen3` puede emitir su razonamiento entre `<think>…</think>`: R.E.M lo elimina antes de mostrar/hablar.
- Hardware: no sé qué equipo tienes; **dime tu RAM/VRAM y elijo el tamaño**.

## Búsqueda web sin pago
La búsqueda de servidor de Anthropic no existe con modelos gratuitos. La sustituyen herramientas locales: `buscar_web` (DuckDuckGo vía el paquete `ddgs`,
**scraping no oficial: puede fallar o limitarse**; `pip install -e '.[web]'`), `wikipedia` (API oficial) y `leer_url` (bloquea redes privadas/locales y redirecciones a ellas).
El texto web se trata como dato no confiable. *No pude probar la red real desde este entorno* (solo las protecciones y el parseo).

## Opción en la nube con capa gratuita (con cuidado)
Cualquier servicio con API estilo OpenAI sirve con `provider: openai_compat`:
```yaml
models:
  provider: openai_compat
  base_url: "https://openrouter.ai/api/v1"      # o https://api.groq.com/openai/v1
  api_key_env: OPENROUTER_API_KEY               # export OPENROUTER_API_KEY=...   (no pongas la clave en el YAML)
  leader: "<id de un modelo :free de tu lista>"
```
Límites que citan blogs (cámbialos o verifícalos en el proveedor): OpenRouter `:free` ~20 peticiones/min y 50/día (1.000/día tras comprar ≥ 10 USD en créditos);
Groq ~30 peticiones/min y topes diarios por modelo; Google AI Studio con topes por minuto/día. **Una capa gratuita puede tener topes bajos (un agente que delega gasta
muchas peticiones), cambiar sin aviso y, según el proveedor, usar tus prompts para mejorar sus productos: revisa sus términos y no envíes documentos privados ni datos de cámara.**
Por eso la recomendación principal es local.

## Fuentes consultadas (secundarias)
- [Best Ollama Models 2026 (morphllm)](https://www.morphllm.com/best-ollama-models) · [Best Ollama Model for Tool Calling Agent 2026 (webscraft)](https://webscraft.org/blog/yaku-model-ollama-obrati-dlya-agenta-z-tool-calling-porivnyannya-i-benchmarki?lang=en) · [Best Ollama Models for AI Agents 2026 (localaimaster)](https://localaimaster.com/blog/best-ollama-models-for-agents)
- [Best Open Source LLMs to run locally 2026 (Hugging Face blog)](https://huggingface.co/blog/daya-shankar/open-source-llm-models-to-run-locally)
- [Run Qwen3 locally: GPU requirements (spheron)](https://www.spheron.network/blog/run-qwen3-locally-gpu-requirements-2026/) · [Qwen3 14B (canirun.ai)](https://canirun.ai/model/qwen3-14b/)
- [gpt-oss-20b (Dell/Hugging Face mirror)](https://dell.huggingface.co/models/openai/gpt-oss-20b) · [Gemma 4 locally (jacar.es)](https://jacar.es/en/gemma-4-locally-with-ollama/) · [Gemma 4 Apache 2.0 (noze.it)](https://www.noze.it/en/insights/gemma-new-release/)
- [Free LLM API in 2026 (OpenRouter blog)](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/) · [OpenRouter free tier limits (klymentiev)](https://klymentiev.com/blog/openrouter-free-tier)
