"""SenseVoice Small(FunASR). FSMN VAD 로 구간을 먼저 나누고 구간마다 인식한다 — 시각은 구간 단위."""
from __future__ import annotations

import re


class Adapter:
    def __init__(self, ctx):
        self.ctx = ctx

    def load(self):
        from funasr import AutoModel
        dev = "cuda:0" if self.ctx.device.startswith("cuda") else "cpu"
        vad = next(iter(self.ctx.model["aux"].values()))
        self.vad = AutoModel(model=vad, device=dev, disable_update=True, max_single_segment_time=30000)
        self.model = AutoModel(model=self.ctx.model["path"], device=dev, disable_update=True)

    def asr(self, audio, language, p):
        import soundfile as sf
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
        y, sr = sf.read(audio, dtype="float32", always_2d=True)
        y = y.mean(1)
        spans = self.vad.generate(input=audio)[0]["value"]   # [[시작 ms, 끝 ms], …]
        # 짧은 구간을 merge_length_s 까지 합친다
        merged, lim = [], float(p.get("merge_length_s", 15)) * 1000
        for a, b in spans:
            if merged and b - merged[-1][0] <= lim and a - merged[-1][1] < 800:
                merged[-1][1] = b
            else:
                merged.append([a, b])
        segs, langs = [], []
        for k, (a, b) in enumerate(merged):
            piece = y[int(a * sr / 1000): int(b * sr / 1000)]
            r = self.model.generate(input=piece, cache={}, language=language or "auto", use_itn=bool(p.get("use_itn", True)),
                                    fs=sr)[0]
            raw = r["text"]
            m = re.match(r"<\|(\w+)\|>", raw)
            if m:
                langs.append(m.group(1))
            segs.append({"start": round(a / 1000, 3), "end": round(b / 1000, 3), "text": rich_transcription_postprocess(raw).strip()})
            self.ctx.progress(pct=(k + 1) / max(1, len(merged)))
        lang = max(set(langs), key=langs.count) if langs else (language or "")
        return {"language": lang, "segments": [s for s in segs if s["text"]]}
