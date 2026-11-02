"""전사 결과 → SRT · VTT · TXT · JSON.

`max_chars` > 0 이면 긴 구간을 단어 시각으로 나눈다(단어 시각이 없는 엔진은 글자 비율로 시각을 나눈다).
"""
from __future__ import annotations

import json


def _ts(t: float, sep: str) -> str:
    t = max(0.0, t)
    h, r = divmod(int(round(t * 1000)), 3600_000)
    m, r = divmod(r, 60_000)
    s, ms = divmod(r, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def cues(segments: list[dict], max_chars: int = 0) -> list[dict]:
    out = []
    for s in segments:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        if not max_chars or len(text) <= max_chars:
            out.append({"start": s["start"], "end": s["end"], "text": text})
            continue
        words = s.get("words") or []
        if words:
            cur, st = [], None
            for w in words:
                wt = w["word"]
                if cur and len("".join(x["word"] for x in cur + [w]).strip()) > max_chars:
                    out.append({"start": st, "end": cur[-1]["end"], "text": "".join(x["word"] for x in cur).strip()})
                    cur, st = [], None
                if st is None:
                    st = w["start"]
                cur.append({"word": wt, "end": w["end"]})
            if cur:
                out.append({"start": st, "end": cur[-1]["end"], "text": "".join(x["word"] for x in cur).strip()})
        else:
            n = (len(text) + max_chars - 1) // max_chars
            step = (s["end"] - s["start"]) / n
            for k in range(n):
                out.append({"start": s["start"] + k * step, "end": s["start"] + (k + 1) * step,
                            "text": text[k * max_chars:(k + 1) * max_chars].strip()})
    return out


def render(segments: list[dict], fmt: str, max_chars: int = 0, meta: dict | None = None) -> tuple[str, str]:
    cs = cues(segments, max_chars)
    if fmt == "srt":
        body = "\n".join(f"{i}\n{_ts(c['start'], ',')} --> {_ts(c['end'], ',')}\n{c['text']}\n" for i, c in enumerate(cs, 1))
        return body, "application/x-subrip"
    if fmt == "vtt":
        body = "WEBVTT\n\n" + "\n".join(f"{_ts(c['start'], '.')} --> {_ts(c['end'], '.')}\n{c['text']}\n" for c in cs)
        return body, "text/vtt"
    if fmt == "txt":
        return "\n".join(c["text"] for c in cs) + "\n", "text/plain"
    if fmt == "json":
        return json.dumps({**(meta or {}), "segments": segments}, ensure_ascii=False, indent=1), "application/json"
    raise ValueError(f"모르는 형식: {fmt}")
