"""OmniVoice (k2-fsa) — 가장 빠른 엔진(RTF 0.40)."""
from __future__ import annotations

from ._common import PromptCache, filtered


class Adapter:
    def __init__(self, ctx):
        self.ctx = ctx

    def load(self):
        import torch
        from omnivoice import OmniVoice
        cuda = self.ctx.device.startswith("cuda")
        self.model = OmniVoice.from_pretrained(self.ctx.model["path"], device_map=self.ctx.device,
                                               dtype=torch.float16 if cuda else torch.float32)
        self.prompts = PromptCache(lambda r: self.model.create_voice_clone_prompt(ref_audio=r["audio"], ref_text=r["text"]))

    def tts(self, text, ref, lang, p):
        kw, dropped = filtered(self.model.generate, text=text, voice_clone_prompt=self.prompts.get(ref),
                               num_step=int(p.get("num_step", 32)), guidance_scale=float(p.get("guidance_scale", 2.0)),
                               speed=float(p.get("speed", 1.0)))
        if dropped:
            self.ctx.log(f"OmniVoice 가 받지 않는 인자: {dropped}")
        out = self.model.generate(**kw)
        return out[0], 24000
