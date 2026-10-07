#!/usr/bin/env python3
"""Sustituto de `llama-tts` para probar la integración sin modelo: escribe un WAV con un tono."""
import math, struct, sys, wave

a = sys.argv[1:]
if "--help" in a:
    print("usage: llama-tts [options]\n  -mm, --mmproj FILE\n"); sys.exit(0)
if "--version" in a:
    print("version: 10500 (fake)"); sys.exit(0)
if "--list-devices" in a:
    sys.exit(0)
out = a[a.index("-o") + 1]
text = a[a.index("-p") + 1]
n = 16000 * max(1, len(text) // 20)
with wave.open(out, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 16000))) for i in range(n)))
print("fake llama-tts ok")
