"""Chatterbox Multilingual V3. 참고 음성 언어가 대본과 다르면 cfg_weight 0(README 권장 — 참고 억양이 번진다)."""
from __future__ import annotations

from ._common import filtered


class Adapter:
    def __init__(self, ctx):
        self.ctx = ctx

    def load(self):
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        dev = "cuda" if self.ctx.device.startswith("cuda") else "cpu"
        self.model = ChatterboxMultilingualTTS.from_local(self.ctx.model["path"], dev, t3_model="v3")

    def tts(self, text, ref, lang, p):
        cfg = float(p.get("cfg_weight", -1))
        if cfg < 0:
            cfg = 0.0 if ref.get("language") and ref["language"] != lang else 0.5
        kw, dropped = filtered(self.model.generate, text=text, language_id=lang, audio_prompt_path=ref["audio"], cfg_weight=cfg,
                               exaggeration=float(p.get("exaggeration", 0.5)), temperature=float(p.get("temperature", 0.8)),
                               repetition_penalty=float(p.get("repetition_penalty", 2.0)), min_p=float(p.get("min_p", 0.05)),
                               top_p=float(p.get("top_p", 1.0)))
        if dropped:
            self.ctx.log(f"Chatterbox 가 받지 않는 인자: {dropped}")
        w = self.model.generate(**kw)
        return w.squeeze(0).cpu().numpy(), self.model.sr
