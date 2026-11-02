"""Qwen3-TTS Base — 유일하게 여러 문단을 한 번에(묶음) 생성한다.

토큰을 하나씩 뽑는 생성이라 GPU 가 20~25 % 만 쓰이고 CPU 한 코어가 병목이다. 문단을 묶어 넣으면 같은 토큰 루프
한 바퀴로 여러 문단이 나온다(원격 4080 실측: 묶음 6 이면 48문단 131 s, 문단별의 3~4배).
"""
from __future__ import annotations

from ._common import PromptCache, lang_name

TOKENS_PER_SEC = 12.5


def token_cap(text: str) -> int:
    # 글자당 0.5 s + 4 s. 끝 신호가 안 나오면 8192 토큰(655 s)까지 간다
    return min(8192, int(TOKENS_PER_SEC * (0.5 * len(text) + 4)))


class Adapter:
    def __init__(self, ctx):
        self.ctx = ctx

    def load(self):
        import torch
        from qwen_tts import Qwen3TTSModel
        cuda = self.ctx.device.startswith("cuda")
        self.ctx.progress(stage="Qwen3-TTS 가중치")
        self.model = Qwen3TTSModel.from_pretrained(self.ctx.model["path"], device_map=self.ctx.device,
                                                   torch_dtype=torch.bfloat16 if cuda else torch.float32)
        self.prompts = {m: PromptCache(lambda r, m=m: self.model.create_voice_clone_prompt(
            ref_audio=r["audio"], ref_text=r["text"], x_vector_only_mode=m)) for m in (False, True)}

    def tts_batch(self, texts, ref, lang, p):
        prompt = self.prompts[bool(p.get("x_vector_only"))].get(ref)
        cap = max(token_cap(t) for t in texts)
        wavs, sr = self.model.generate_voice_clone(
            text=list(texts), language=[lang_name(lang)] * len(texts), voice_clone_prompt=prompt, max_new_tokens=cap,
            do_sample=bool(p.get("do_sample", True)), temperature=float(p.get("temperature", 0.9)),
            top_k=int(p.get("top_k", 50)), top_p=float(p.get("top_p", 1.0)),
            repetition_penalty=float(p.get("repetition_penalty", 1.05)),
            subtalker_temperature=float(p.get("subtalker_temperature", 0.9)),
            subtalker_top_k=int(p.get("subtalker_top_k", 50)), subtalker_top_p=float(p.get("subtalker_top_p", 1.0)))
        return wavs, sr

    def tts(self, text, ref, lang, p):
        wavs, sr = self.tts_batch([text], ref, lang, p)
        return wavs[0], sr
