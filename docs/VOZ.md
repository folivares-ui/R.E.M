# Voz de Rem

## Decisión
**Sin clonación de voces.** R.E.M. usa una voz **sintética predefinida** (Kokoro-82M). No procesé la grabación que adjuntaste al inicio ni ninguna
muestra de una persona real, y el código ya no incluye registro/clonación de voces.

## Voz elegida: Kokoro-82M (local, CPU)
- Modelo de síntesis pequeño que corre **en CPU**, sin GPU (tu equipo: 16 GB de RAM y 128 MB de VRAM).
- Voces en español incluidas en su paquete de voces (comprobado en el paquete `kokoro-js` y con el modelo real): `ef_dora` (femenina), `em_alex` y `em_santa` (masculinas).
  **Por defecto: `ef_dora`** (voz femenina; es la opción más cercana a Rem en género/registro, pero **no puedo escuchar el audio ni afirmar que "se parezca" a Rem**:
  genera muestras y decide tú).
- Licencia: el paquete `kokoro-js` declara **Apache-2.0** (verificado en su `package.json`) y fuentes secundarias indican lo mismo para el modelo Kokoro-82M.
  **No pude abrir su ficha oficial** (Hugging Face bloqueado desde mi entorno): léela antes de cualquier uso fuera de este prototipo privado, incluidos los datos con que se entrenó.
- El "parecido" a Rem se logra con la **personalidad y el estilo de habla** (persona + frases cortas), no imitando a nadie.

### Puesta en marcha
```bash
pip install -e '.[tts-kokoro]'
python scripts/download_kokoro.py     # ~92 MB + ~28 MB en ./models, con verificación SHA-256
rem voice list                        # voces en español
rem voice demo                        # genera data/voice_demo/*.wav (3 voces x 3 velocidades) para que las escuches
```
Luego ajusta `voice.kokoro_voice` y `voice.kokoro_speed` en `config/rem.yaml`.

**Medido en este entorno (4 núcleos, 15 GB de RAM; no es tu máquina):** carga ~0,7 s; una frase de ~3,5 s de audio tardó ~3,3 s en sintetizarse (≈ tiempo real
en CPU, incluyendo el primer uso). En tu equipo puede variar.

## Conectarla a AIRI
AIRI tiene un proveedor de voz "OpenAI-compatible" (existe en su código). R.E.M. sirve `POST /v1/audio/speech` (`rem serve`) y acepta el campo `voice`:
base URL `http://127.0.0.1:8765/v1/`, voz `ef_dora`. (Los nombres exactos de los campos de la interfaz de AIRI no los he probado; verifícalos en tu versión.)
> El Kokoro integrado de AIRI (`kokoro-local`) **no sirve para español**: el paquete que usa solo registra voces en inglés (las voces en español están como archivos pero no en su lista).

## Subtítulos
Funcionan con o sin voz: `/subtitles` (overlay transparente para OBS o ventana), `/subtitles/stream` (SSE) y `/subtitles/last`. Los tiempos son una **estimación**
(~16 caracteres/s); con Kokoro se puede medir la duración real del WAV si necesitas sincronía exacta (pendiente).

## Otros proveedores (opcionales)
- `tts_provider: none` — sin audio (solo subtítulos).
- `tts_provider: command` — tu propio comando: lee texto por stdin y escribe un WAV en `{out}`.
- `tts_provider: http` — una API de voz tuya (URL + nombre de la variable de entorno con la clave). Formato: `POST` JSON `{model, input, voice, response_format}`.
  Probado solo con un servidor local de prueba. Revisa los términos del proveedor sobre qué datos recibe.
