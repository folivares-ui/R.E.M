# Cámara, rostros, gestos y llamada por nombre

> **Estado: sin verificar en hardware.** Este entorno no tiene cámara, micrófono ni GPU. La lógica pura
> (coincidencia de nombre, mapa de gestos, antirrebote, registro de rostros con consentimiento,
> puerta de confirmación) está probada con tests; los módulos que tocan hardware están escritos pero
> **no se han ejecutado**.

## Instalación
```bash
pip install -e '.[vision,faces,voice]'
```
- Gestos: MediaPipe Gesture Recognizer. Descarga el archivo `gesture_recognizer.task` desde la
  documentación oficial de MediaPipe (no incluyo una URL porque no pude verificarla) y apunta
  `perception.gesture_model` en `config/rem.yaml` a ese archivo.
- Rostros: InsightFace (`buffalo_l`). **Revisa la licencia de los modelos preentrenados**
  (no estoy seguro de que permita más que uso de investigación/no comercial).
- Voz a texto: faster-whisper (el modelo se descarga la primera vez). Sin GPU usa el modelo `base` (configurado) por velocidad; `small` es más preciso pero más lento (no medido).

## Privacidad (diseño)
- Solo se reconoce a personas **inscritas con consentimiento**:
  `rem faces enroll "Ana" --consent`. Se guarda un vector, no fotos, en `data/faces/` (git-ignorado).
- `rem faces forget "Ana"` borra a la persona. Rostros no inscritos = "desconocido", sin intentar identificarlos.
- El micrófono solo desencadena una respuesta si oye el nombre ("Rem..."); lo demás se descarta sin guardarse.
- La cámara y el micrófono dejan un aviso en el log al activarse.
- Si hay terceros en el encuadre, avísales. Según tu país, el reconocimiento facial puede estar regulado.

## Uso
`rem live` une micrófono + cámara + nombre. Los eventos de cámara también pueden enviarse al puente
HTTP (`POST /events`) para que AIRI/Rem los tengan en cuenta en el siguiente turno.
