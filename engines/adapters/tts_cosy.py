"""Fun-CosyVoice3 — 결정적(같은 입력이면 md5 까지 같은 출력). 코드는 engines/vendor/cosy/CosyVoice(고정 커밋)."""
from __future__ import annotations

import os
import sys

from ._common import filtered, vendor


class Adapter:
    def __init__(self, ctx):
        self.ctx = ctx

    def load(self):
        code = vendor("cosy", "CosyVoice")
        sys.path[:0] = [code, os.path.join(code, "third_party", "Matcha-TTS")]
        from cosyvoice.cli.cosyvoice import AutoModel
        self.model = AutoModel(model_dir=self.ctx.model["path"])

    def tts(self, text, ref, lang, p):
        import torch
        ptext = "You are a helpful assistant.<|endofprompt|>" + ref["text"]
        kw, dropped = filtered(self.model.inference_zero_shot, tts_text=text, prompt_text=ptext, prompt_wav=ref["audio"],
                               prompt_speech_16k=ref["audio"], stream=False, speed=float(p.get("speed", 1.0)),
                               text_frontend=bool(p.get("text_frontend", True)))
        segs = [o["tts_speech"] for o in self.model.inference_zero_shot(**kw)]
        return torch.cat(segs, dim=1).squeeze(0).cpu().numpy(), self.model.sample_rate
