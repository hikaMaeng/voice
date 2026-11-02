"""faster-whisper(CTranslate2). 연산 정밀도(compute_type)는 싣는 시점 값이라 바뀌면 다시 싣는다."""
from __future__ import annotations

from ._common import cuda_dll_dirs


class Adapter:
    def __init__(self, ctx):
        self.ctx = ctx
        self.models = {}

    def _model(self, ct: str):
        cuda = self.ctx.device.startswith("cuda")
        if ct == "auto":
            ct = "float16" if cuda else "int8"
        if ct not in self.models:
            from faster_whisper import WhisperModel
            self.models = {ct: WhisperModel(self.ctx.model["path"], device="cuda" if cuda else "cpu", compute_type=ct)}
        return self.models[ct], ct

    def load(self):
        cuda_dll_dirs()
        self._model("auto")

    def asr(self, audio, language, p):
        import numpy as np
        import soundfile as sf
        model, ct = self._model(p.get("compute_type", "auto"))
        # 파일 경로를 넘기면 PyAV 로 디코딩하는데, 함께 깔린 av 판과 인자가 안 맞아 죽었다(metadata_errors) — 서버가 준 16 kHz wav 를 직접 읽는다
        y, sr = sf.read(audio, dtype="float32", always_2d=True)
        y = y.mean(1)
        if sr != 16000:
            idx = np.linspace(0, len(y) - 1, int(len(y) * 16000 / sr))
            y = np.interp(idx, np.arange(len(y)), y).astype(np.float32)
        segs, info = model.transcribe(
            y, language=language or None, beam_size=int(p.get("beam_size", 5)), vad_filter=bool(p.get("vad_filter", True)),
            word_timestamps=bool(p.get("word_timestamps", True)), temperature=float(p.get("temperature", 0.0)) or [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            condition_on_previous_text=bool(p.get("condition_on_previous_text", True)), initial_prompt=p.get("initial_prompt") or None)
        out = []
        for s in segs:
            out.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip(),
                        "words": [{"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word, "prob": round(w.probability, 3)}
                                  for w in (s.words or [])]})
            if info.duration:
                self.ctx.progress(pct=min(0.99, s.end / info.duration))
        return {"language": info.language, "language_prob": round(info.language_probability, 3),
                "duration": info.duration, "compute_type": ct, "segments": out}
