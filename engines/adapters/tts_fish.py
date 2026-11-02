"""Fish Audio S2-Pro — fish-speech(고정 커밋)의 ModelManager. 작업 디렉터리를 바꾸므로 경로는 모두 절대 경로로 받는다."""
from __future__ import annotations

import os
import sys

from ._common import vendor


class Adapter:
    def __init__(self, ctx):
        self.ctx = ctx

    def load(self):
        code = vendor("fish", "fish-speech")
        sys.path.insert(0, code)
        os.chdir(code)   # 설정 파일을 상대 경로로 읽는다
        from tools.server.model_manager import ModelManager
        dev = "cuda" if self.ctx.device.startswith("cuda") else "cpu"
        self.mm = ModelManager(mode="tts", device=dev, half=False, compile=False, llama_checkpoint_path=self.ctx.model["path"],
                               decoder_checkpoint_path=None, decoder_config_name="modded_dac_vq")
        self._ref = (None, None)

    def tts(self, text, ref, lang, p):
        from fish_speech.utils.schema import ServeReferenceAudio, ServeTTSRequest
        if self._ref[0] != ref["audio"]:
            self._ref = (ref["audio"], open(ref["audio"], "rb").read())
        fields = getattr(ServeTTSRequest, "model_fields", {})
        kw = {k: v for k, v in dict(temperature=float(p.get("temperature", 0.8)), top_p=float(p.get("top_p", 0.8)),
                                     repetition_penalty=float(p.get("repetition_penalty", 1.1)),
                                     max_new_tokens=int(p.get("max_new_tokens", 1024)),
                                     chunk_length=int(p.get("chunk_length", 200))).items() if k in fields}
        req = ServeTTSRequest(text=text, references=[ServeReferenceAudio(audio=self._ref[1], text=ref["text"])], format="wav", **kw)
        for r in self.mm.tts_inference_engine.inference(req):
            if r.code == "error":
                raise r.error
            if r.code == "final":
                return r.audio[1], r.audio[0]
        raise RuntimeError("최종 음성이 없다")
