"""Subtítulos: trocea cada respuesta de Rem en "cues" y los difunde a los visores suscritos.

- `GET /subtitles`         página-overlay transparente (úsala como Browser Source de OBS o en una ventana).
- `GET /subtitles/stream`  Server-Sent Events con cada cue (`{"text", "start", "duration"}`).
- `GET /subtitles/last`    el último conjunto de cues (útil para depurar).
Los subtítulos funcionan con o sin voz: si no hay TTS, el texto sigue apareciendo.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass

_SENT = re.compile(r"(?<=[.!?…])\s+")


@dataclass
class Cue:
    text: str
    start: float      # segundos desde el inicio de la respuesta
    duration: float


def split_cues(text: str, max_chars: int = 84, chars_per_s: float = 16.0, min_s: float = 1.2) -> list[Cue]:
    """Parte por frases y, si una frase es larga, por palabras sin cortar ninguna. Duración estimada (~16 car/s)."""
    pieces: list[str] = []
    for sent in _SENT.split(text.strip()):
        sent = sent.strip()
        while len(sent) > max_chars:
            cut = sent.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            pieces.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        if sent:
            pieces.append(sent)
    cues, t = [], 0.0
    for p in pieces:
        d = max(min_s, len(p) / chars_per_s)
        cues.append(Cue(p, round(t, 2), round(d, 2)))
        t += d
    return cues


class SubtitleHub:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()
        self.last: list[Cue] = []

    def publish(self, text: str) -> list[Cue]:
        self.last = split_cues(text)
        payload = [asdict(c) for c in self.last]
        for q in list(self._subs):
            if q.full():  # visor lento: descarta lo más antiguo, nunca bloquea a Rem
                q.get_nowait()
            q.put_nowait(payload)
        return self.last

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=8)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    async def sse(self, is_disconnected):
        q = self.subscribe()
        try:
            yield ": conectado\n\n"
            while not await is_disconnected():
                try:
                    cues = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"data: {json.dumps(cues, ensure_ascii=False)}\n\n"
        finally:
            self.unsubscribe(q)


OVERLAY_HTML = """<!doctype html><html lang="es"><meta charset="utf-8"><title>Subtítulos de Rem</title>
<style>html,body{margin:0;height:100%;background:transparent;overflow:hidden}
#s{position:fixed;left:6%;right:6%;bottom:6%;text-align:center;font:600 clamp(20px,3.2vw,40px)/1.3 system-ui,sans-serif;
color:#fff;text-shadow:0 0 4px #000,0 0 8px #000,2px 2px 2px #000;transition:opacity .25s;opacity:0}</style>
<div id="s" aria-live="polite"></div>
<script>
const el=document.getElementById('s');let timers=[];
function show(cues){timers.forEach(clearTimeout);timers=[];
 cues.forEach(c=>{timers.push(setTimeout(()=>{el.textContent=c.text;el.style.opacity=1},c.start*1000));
  timers.push(setTimeout(()=>{if(el.textContent===c.text)el.style.opacity=0},(c.start+c.duration+0.8)*1000));});}
const es=new EventSource('/subtitles/stream');es.onmessage=e=>show(JSON.parse(e.data));
</script></html>"""
