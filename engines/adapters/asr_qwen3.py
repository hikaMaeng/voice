"""Qwen3-ASR(qwen-asr 패키지). 시각은 보조 모델 Qwen3-ForcedAligner-0.6B 로 맞춘다(11개 언어, 한국어 포함)."""
from __future__ import annotations

from ._common import group_words, lang_name

CODES = {"Korean": "ko", "Japanese": "ja", "English": "en", "Chinese": "zh", "German": "de", "French": "fr", "Spanish": "es",
         "Italian": "it", "Portuguese": "pt", "Russian": "ru", "Cantonese": "yue"}


class Adapter:
    def __init__(self, ctx):
        self.ctx = ctx

    def load(self):
        import torch
        from qwen_asr import Qwen3ASRModel
        cuda = self.ctx.device.startswith("cuda")
        dt = torch.bfloat16 if cuda else torch.float32
        aligner = next(iter(self.ctx.model["aux"].values()), None)
        kw = dict(dtype=dt, device_map=self.ctx.device, max_inference_batch_size=8, max_new_tokens=1024)
        if aligner:
            kw.update(forced_aligner=aligner, forced_aligner_kwargs=dict(dtype=dt, device_map=self.ctx.device))
        self.model = Qwen3ASRModel.from_pretrained(self.ctx.model["path"], **kw)

    def asr(self, audio, language, p):
        ts = bool(p.get("timestamps", True))
        res = self.model.transcribe(audio=audio, language=lang_name(language) if language else None, return_time_stamps=ts)
        r = res[0]
        lang = CODES.get(getattr(r, "language", "") or "", getattr(r, "language", "") or "")
        stamps = getattr(r, "time_stamps", None) or []
        if ts and stamps:
            items = stamps.items if hasattr(stamps, "items") and not isinstance(stamps, dict) else stamps
            ws = []
            for it in items:
                g = it if isinstance(it, dict) else it.__dict__
                ws.append({"start": float(g.get("start_time", g.get("start", 0))), "end": float(g.get("end_time", g.get("end", 0))),
                           "word": g.get("text", ""), "prob": None})
            # 동아시아 글자는 단어 사이 띄어쓰기가 없다 — 원문에서 띄어쓰기를 되살린다
            text = r.text
            pos = 0
            for w in ws:
                k = text.find(w["word"], pos)
                if k > pos and text[pos:k].strip() == "":
                    w["word"] = text[pos:k] + w["word"]
                if k >= 0:
                    pos = k + len(w["word"].lstrip())
            return {"language": lang, "segments": group_words(ws)}
        return {"language": lang, "segments": [{"start": 0.0, "end": 0.0, "text": r.text.strip()}]}
