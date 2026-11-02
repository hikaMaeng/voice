"""Higgs Audio v3 TTS 4B — multimodalart 의 transformers 포팅판(transformers >= 5.5)."""
from __future__ import annotations


class Adapter:
    def __init__(self, ctx):
        self.ctx = ctx

    def load(self):
        import soundfile as sf
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch, self.sf = torch, sf
        m = self.ctx.model
        self.tok = AutoTokenizer.from_pretrained(m["path"])
        self.ctx.progress(stage="Higgs 가중치")
        self.model = AutoModelForCausalLM.from_pretrained(m["path"], trust_remote_code=True, dtype=torch.bfloat16).to(self.ctx.device).eval()
        self.model.config.audio_tokenizer_id = next(iter(m["aux"].values()))   # 코덱도 로컬 폴더에서
        self._codes = {}

    def tts(self, text, ref, lang, p):
        key = (ref["audio"], ref.get("text"))
        if key not in self._codes:
            rw, rsr = self.sf.read(ref["audio"], dtype="float32", always_2d=True)
            self._codes = {key: self.model._encode_reference(self.torch.from_numpy(rw.mean(1)), rsr).cpu()}
        with self.torch.no_grad():   # 모델 카드(bosonai) 예시 값이 기본
            w = self.model.generate_speech(text, self.tok, reference_codes=self._codes[key], reference_text=ref["text"],
                                           temperature=float(p.get("temperature", 0.8)), top_k=int(p.get("top_k", 50)),
                                           max_new_tokens=int(25 * (0.5 * len(text) + 8)))
        return w.numpy() if hasattr(w, "numpy") else w, self.model.config.sample_rate
