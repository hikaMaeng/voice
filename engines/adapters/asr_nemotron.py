"""NVIDIA Nemotron 3.5 ASR Streaming 0.6B — transformers(AutoModelForRNNT) 경로(NeMo 없이 Windows 에서 돈다).

모델 카드에 단어·구간 시각 출력이 없다 → 소리 크기로 말 구간을 나누고 구간마다 인식해 타임라인을 만든다.
언어는 locale(ko-KR) 또는 맨 코드(ko) 또는 auto. auto 면 출력 끝에 <ko-KR> 같은 언어 표지가 붙는다.
"""
from __future__ import annotations

import re

from ._common import energy_segments

TAG = re.compile(r"<([a-z]{2,3})-[A-Za-z]{2,4}>")
# 맨 코드를 받는 언어도 있지만 ja·zh 는 locale 만 받는다(실측: `language='ja'` → ValueError) — 전부 locale 로 넘긴다
LOCALE = {"ko": "ko-KR", "ja": "ja-JP", "en": "en-US", "zh": "zh-CN", "de": "de-DE", "fr": "fr-FR", "es": "es-ES",
          "it": "it-IT", "pt": "pt-BR", "ru": "ru-RU"}


class Adapter:
    def __init__(self, ctx):
        self.ctx = ctx

    def load(self):
        import torch
        from transformers import AutoModelForRNNT, AutoProcessor
        self.torch = torch
        path = self.ctx.model["path"]
        self.proc = AutoProcessor.from_pretrained(path)
        self.model = AutoModelForRNNT.from_pretrained(path, torch_dtype=torch.float32).to(self.ctx.device).eval()
        self.sr = self.proc.feature_extractor.sampling_rate

    def asr(self, audio, language, p):
        import numpy as np
        import soundfile as sf
        y, sr = sf.read(audio, dtype="float32", always_2d=True)
        y = y.mean(1)
        if sr != self.sr:
            import librosa
            y = librosa.resample(y, orig_sr=sr, target_sr=self.sr)
            sr = self.sr
        spans = energy_segments(y, sr, float(p.get("min_silence_s", 0.35)), float(p.get("segment_max_s", 15.0)))
        lang_arg = LOCALE.get(language, language) if language else "auto"
        segs, langs = [], []
        for k, (a, b) in enumerate(spans):
            piece = y[int(a * sr): int(b * sr)]
            inputs = self.proc(piece, sampling_rate=sr, language=lang_arg)
            inputs = inputs.to(self.model.device, dtype=self.model.dtype)
            with self.torch.no_grad():
                out = self.model.generate(**inputs, return_dict_in_generate=True)
            raw = self.proc.decode(out.sequences, skip_special_tokens=False)   # 언어 표지(<ko-KR>)를 읽으려고
            raw = raw[0] if isinstance(raw, list) else raw
            langs += [m.group(1) for m in TAG.finditer(raw)]
            text = self.proc.decode(out.sequences, skip_special_tokens=True)
            text = TAG.sub("", text[0] if isinstance(text, list) else text).strip()
            if text:
                segs.append({"start": round(a, 3), "end": round(b, 3), "text": text})
            self.ctx.progress(pct=(k + 1) / max(1, len(spans)))
        lang = language or (max(set(langs), key=langs.count) if langs else "")
        return {"language": lang, "segments": segs, "segmentation": "energy"}
