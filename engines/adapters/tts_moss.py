"""MOSS-TTS v1.5 — Local-Transformer 4B(카드 1장) / 8B(카드 2장, 디코더 층 분할)."""
from __future__ import annotations

from ._common import lang_name


class Adapter:
    def __init__(self, ctx):
        self.ctx = ctx

    def load(self):
        import soundfile as sf
        import torch
        from transformers import AutoConfig, AutoModel, AutoProcessor
        self.torch, self.sf = torch, sf
        m = self.ctx.model
        path, codec = m["path"], next(iter(m["aux"].values()))
        self.big = m["id"] == "moss-tts-v1.5-8b"
        torch.backends.cuda.enable_cudnn_sdp(False)
        # 코덱은 저장소 이름으로 불러 HF 캐시를 찾는다 — 경로를 준다(codec_path kwarg)
        self.ctx.progress(stage="MOSS 프로세서·코덱")
        self.proc = AutoProcessor.from_pretrained(path, trust_remote_code=True, codec_path=codec)
        self.ctx.progress(stage="MOSS 가중치")
        if self.big:
            # 8B: 디코더 층만 두 카드에 나누고 임베딩·헤드·norm 은 cuda:0 에. 그것들이 갈리면 장치가 섞인다(auto 분할 10/10 실패)
            self.proc.audio_tokenizer = self.proc.audio_tokenizer.to("cpu")
            nl = AutoConfig.from_pretrained(path, trust_remote_code=True).language_config.num_hidden_layers
            self.split = None
            dmap = {"language_model.embed_tokens": 0, "emb_ext": 0, "language_model.norm": 0,
                    "language_model.rotary_emb": 0, "lm_heads": 0,
                    **{f"language_model.layers.{i}": (0 if i < 10 else 1) for i in range(nl)}}
            self.model = AutoModel.from_pretrained(path, trust_remote_code=True, attn_implementation="sdpa",
                                                   torch_dtype=torch.bfloat16, device_map=dmap).eval()
        else:
            self.proc.audio_tokenizer = self.proc.audio_tokenizer.to(self.ctx.device)
            self.model = AutoModel.from_pretrained(path, trust_remote_code=True, attn_implementation="sdpa",
                                                   torch_dtype=torch.bfloat16).to(self.ctx.device).eval()
        self._codes = {}

    def _ref_codes(self, ref):
        key = (ref["audio"], ref.get("text"))
        if key not in self._codes:
            # 경로로 넘기면 torchaudio → torchcodec 이 FFmpeg DLL 을 못 찾아 Windows 에서 죽는다 — 미리 코드로 바꾼다
            rw, rsr = self.sf.read(ref["audio"], dtype="float32", always_2d=True)
            self._codes = {key: self.proc.encode_audios_from_wav(self.torch.from_numpy(rw.T.copy()), rsr)[0]}
        return self._codes[key]

    def tts(self, text, ref, lang, p):
        torch = self.torch
        codes = self._ref_codes(ref)
        b = self.proc([[self.proc.build_user_message(text=text, reference=[codes], language=lang_name(lang))]], mode="generation")
        gen_kw = {} if self.big else dict(do_sample=True, audio_temperature=float(p.get("audio_temperature", 1.7)),
                                          audio_top_p=float(p.get("audio_top_p", 0.8)), audio_top_k=int(p.get("audio_top_k", 25)),
                                          audio_repetition_penalty=float(p.get("audio_repetition_penalty", 1.0)))
        dev = "cuda:0" if self.ctx.device.startswith("cuda") else "cpu"
        with torch.no_grad():
            out = self.model.generate(input_ids=b["input_ids"].to(dev), attention_mask=b["attention_mask"].to(dev),
                                      max_new_tokens=int(p.get("max_new_tokens", 4096)), **gen_kw)
        msg = [x for x in self.proc.decode(out) if x is not None][0]
        w = msg.audio_codes_list[0].float().cpu().numpy()
        return (w.T if w.ndim == 2 else w), self.proc.model_config.sampling_rate
