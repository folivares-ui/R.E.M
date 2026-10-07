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
