"""시험용 모의 엔진 — GPU·가중치 없이 큐·저장·재현·화면을 시험한다. 실제 음성이 아니다."""
from __future__ import annotations

import numpy as np
import soundfile as sf


class Adapter:
    def __init__(self, ctx):
        self.ctx = ctx

    def load(self):
        self.ctx.progress(stage="모의 모델")

    def tts(self, text, ref, lang, params):
        sr = 24000
        n = max(1, len("".join(c for c in text if c.isalnum())))
        dur = min(30.0, 0.12 * n + 0.3)
        t = np.arange(int(dur * sr)) / sr
        f = float(params.get("pitch_hz", 220.0)) * (1 + 0.05 * np.random.rand())   # 시드에 따라 달라진다
        w = 0.4 * np.sin(2 * np.pi * f * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
        return w.astype(np.float32), sr

    def tts_batch(self, texts, ref, lang, params):
        out = [self.tts(t, ref, lang, params)[0] for t in texts]
        return out, 24000

    def asr(self, audio, language, params):
        y, sr = sf.read(audio, dtype="float32", always_2d=True)
        y = y.mean(1)
        hop = int(0.02 * sr)
        e = np.sqrt((y[:len(y) // hop * hop].reshape(-1, hop) ** 2).mean(1)) if len(y) >= hop else np.zeros(1)
        on = e > 0.1 * (e.max() + 1e-8)
        segs, start = [], None
        for k, v in enumerate(list(on) + [False]):
            if v and start is None:
                start = k
            if not v and start is not None:
                if k - start >= 10:
                    segs.append((start * 0.02, k * 0.02))
                start = None
        words = ["모의", "전사", "문장입니다"]
        out = []
        for i, (a, b) in enumerate(segs or [(0.0, len(y) / sr)]):
            step = (b - a) / len(words)
            out.append({"start": round(a, 2), "end": round(b, 2), "text": f"모의 전사 문장입니다 {i + 1}",
                        "words": [{"start": round(a + j * step, 2), "end": round(a + (j + 1) * step, 2), "word": " " + w, "prob": 1.0}
                                  for j, w in enumerate(words)]})
        return {"language": language or "ko", "segments": out}
