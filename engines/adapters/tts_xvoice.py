"""X-Voice Stage1 — CLI 모듈을 인자째 import 해 모델을 한 번만 싣고, 문단마다 main() 을 부른다.
eSpeak NG 는 설치하지 않고 MSI 를 풀어 DLL 만 쓴다(engines/vendor/xvoice/espeak)."""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from ._common import vendor


class Adapter:
    def __init__(self, ctx):
        self.ctx = ctx

    def load(self):
        m = self.ctx.model
        esp = vendor("xvoice", "espeak", "eSpeak NG")
        if os.name == "nt":
            os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = os.path.join(esp, "libespeak-ng.dll")
            os.environ["ESPEAK_DATA_PATH"] = os.path.join(esp, "espeak-ng-data")
        import x_voice.infer.utils_infer as xu
        voc = next(iter(m["aux"].values()))
        _lv = xu.load_vocoder
        xu.load_vocoder = lambda **k: _lv(**{**k, "is_local": True, "local_path": voc})
        self.model_dir = os.path.join(m["path"], m.get("sub") or "XVoice_Base_Stage1")
        self.tmpd = tempfile.mkdtemp(prefix="xv_")
        self.xc = None
        self._key = None

    def _module(self, ref, lang, p):
        """참고·언어·옵션이 바뀌면 CLI 인자를 다시 읽힌다(모듈을 다시 import — 가중치는 utils_infer 쪽 캐시)."""
        key = (ref["audio"], ref["text"], ref.get("language"), lang, p.get("nfe_step"), p.get("cfg_strength"), p.get("speed"))
        if key == self._key:
            return self.xc
        sys.argv = ["x", "-m", "XVoice_Base_Stage1", "-p", os.path.join(self.model_dir, "model_600000.safetensors"),
                    "-v", os.path.join(self.model_dir, "vocab.txt"), "-r", ref["audio"], "-s", ref["text"], "-t", "x",
                    "--ref_lang", ref.get("language") or lang, "--gen_lang", lang, "-o", self.tmpd, "-w", "cur.wav",
                    "--device", "cuda" if self.ctx.device.startswith("cuda") else "cpu",
                    "--nfe_step", str(int(p.get("nfe_step", 32))), "--cfg_strength", str(float(p.get("cfg_strength", 2.0))),
                    "--speed", str(float(p.get("speed", 1.0)))]
        name = "x_voice.infer.infer_cli_stage1"
        self.xc = importlib.reload(sys.modules[name]) if name in sys.modules else importlib.import_module(name)
        self._key = key
        return self.xc

    def tts(self, text, ref, lang, p):
        import soundfile as sf
        xc = self._module(ref, lang, p)
        xc.gen_text = text
        xc.wave_path = Path(self.tmpd) / "cur.wav"
        if xc.wave_path.exists():
            xc.wave_path.unlink()
        xc.main()
        w, sr = sf.read(str(xc.wave_path), dtype="float32")
        return w, sr
