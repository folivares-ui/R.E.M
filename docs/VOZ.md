# Voz de Rem

## Lo que NO hice y por qué
Me adjuntaste una grabación cuyo nombre de archivo la atribuye a una actriz de doblaje real
(Alondra Hidalgo). **No procesé ese audio ni clono su voz.** Clonar la voz de una persona real sin
su consentimiento es suplantación de identidad vocal, aunque el proyecto sea privado y sin fines de
lucro; y no puedo verificar ni los derechos del audio ni el permiso de la persona. No es una cuestión
de derechos de autor del personaje: es de la voz de una persona.
(No pude confirmar que la grabación sea realmente de esa persona; me baso solo en el nombre del archivo.)

## Qué sí queda listo
- AIRI ya trae su propia síntesis de voz (selección de proveedor en sus ajustes). Es la ruta más simple.
- `rem/voice/tts.py` define un proveedor `command`: tú configuras un comando que lee texto por stdin y
  escribe un WAV en `{out}` (y opcionalmente usa `{ref}` como audio de referencia).
  Ejemplo de configuración (`config/rem.yaml`):

  ```yaml
  voice:
    tts_provider: command
    tts_command: "mi-tts --ref {ref} --out {out}"   # TU comando; no incluyo uno
    reference_wav: assets/voice_reference/mi_voz.wav  # solo una voz propia o con permiso por escrito
  ```
- `assets/voice_reference/` y `assets/*.mp3` están en `.gitignore`.

## Alternativas para una voz "tipo Rem" sin clonar a nadie
1. Una voz propia o de alguien que firme su consentimiento para esa finalidad.
2. Una voz sintética genérica, o diseñada por parámetros (tono/edad/ritmo) en un TTS que lo permita.
3. Un/a actor/actriz de voz que te autorice a grabar un conjunto de referencia para este prototipo.
Si eliges (1) o (3), dime qué motor TTS usarás y lo integro y pruebo contigo.

## Subtítulos y API de voz enchufable
**Subtítulos** (funcionan con o sin voz): al responder, R.E.M. los publica en
- `http://127.0.0.1:8765/subtitles` — overlay con fondo transparente (Browser Source de OBS o ventana propia),
- `/subtitles/stream` — Server-Sent Events con cada cue `{text, start, duration}`,
- `/subtitles/last` — el último conjunto, para depurar.
Las etiquetas de emoción `<|ACT ...|>` se quitan antes. La duración de cada cue es una **estimación** (~16 caracteres/s);
no está sincronizada con el audio real de ningún proveedor (si lo necesitas, hay que medir la duración del WAV devuelto).

**API de voz propia** (`voice.tts_provider: http`): tú pones URL, modelo, voz y el *nombre* de la variable de entorno con la clave.
```yaml
voice:
  tts_provider: http
  tts_url: "https://TU-PROVEEDOR/v1/audio/speech"
  tts_api_key_env: REM_TTS_API_KEY     # export REM_TTS_API_KEY=...  (no pongas la clave en el YAML)
  tts_model: "..."
  tts_voice: "..."
```
Envía `POST` JSON `{model, input, voice, response_format}` y espera audio en la respuesta (la convención de los endpoints
"OpenAI-compatible" de voz). **No he probado ningún proveedor real**; solo un servidor local de prueba. Si tu proveedor usa otro
formato, usa `tts_provider: command` con un script tuyo. Revisa los términos del proveedor sobre voces y datos que envías.

## Clonar-voz (servidor local) como motor de voz
Integrado el proyecto <https://github.com/jceronch1/Clonar-voz> (MIT, commit fijado en `scripts/bootstrap.sh`):
síntesis y clonación 100 % local con Qwen3-TTS (GGUF) + llama.cpp y una API HTTP.

```bash
bash scripts/bootstrap.sh                 # lo deja en vendor/Clonar-voz
cd vendor/Clonar-voz && ./iniciar.sh      # pide llama.cpp (>= b10500 según su README), ffmpeg y descarga ~1,5 GB de pesos
# en otra terminal, desde R.E.M:
rem voice status
rem voice register --file mi_voz.wav --name "Mi voz" --permission "mi propia voz"
rem voice list                            # copia el id a config/rem.yaml -> voice.clonar_voz_voice_id
```
```yaml
voice:
  tts_provider: clonar_voz
  clonar_voz_url: http://127.0.0.1:8080   # solo local: su API no tiene autenticación
  clonar_voz_voice_id: "<id>"
```
**Permiso obligatorio:** `rem voice register` se niega sin `--permission` (quién da el permiso: tu propia voz, o una persona con
autorización escrita) y deja constancia en `data/voice_consent.jsonl`. El propio README de Clonar-voz advierte que clonar una voz
sin permiso es ilegal en muchos países. **Sigo sin procesar la grabación de la actriz de doblaje**: esta herramienta no cambia eso; sirve
para una voz propia o con consentimiento. Es una constancia declarativa, no una verificación: la responsabilidad es tuya.

**Verificado:** el adaptador contra el `app.py` REAL de Clonar-voz con un `llama-tts` falso (registro de voz multipart, generación, SSE,
descarga del WAV) y contra un servidor de prueba. **No verificado:** la calidad ni el funcionamiento del modelo Qwen3-TTS real, llama.cpp,
GPU/CPU, ni el parecido de la voz (no se descargaron los ~1,5 GB de pesos). Los pesos tienen su propia licencia
(<https://huggingface.co/ggml-org/Qwen3-TTS-12Hz-1.7B-Base-GGUF>); no la he revisado. Las afirmaciones sobre versiones de llama.cpp y
rendimiento son de su README, no mías.
