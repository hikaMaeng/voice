"""Whisper(transformers pipeline). 언어 감지 결과는 파이프라인이 돌려주지 않아 detect_language 로 따로 잰다."""
from __future__ import annotations

from ._common import group_words

ISO = {"ko": "korean", "ja": "japanese", "en": "english", "zh": "chinese", "de": "german", "fr": "french", "es": "spanish",
       "it": "italian", "pt": "portuguese", "ru": "russian", "yue": "cantonese"}


class Adapter:
    def __init__(self, ctx):
        self.ctx = ctx

    def load(self):
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
        cuda = self.ctx.device.startswith("cuda")
        dt = torch.float16 if cuda else torch.float32
        path = self.ctx.model["path"]
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(path, torch_dtype=dt).to(self.ctx.device)
        self.proc = AutoProcessor.from_pretrained(path)
        self.pipe = pipeline("automatic-speech-recognition", model=self.model, tokenizer=self.proc.tokenizer,
                             feature_extractor=self.proc.feature_extractor, torch_dtype=dt, device=self.ctx.device)
        self.torch, self.dt = torch, dt

    def _detect(self, y) -> str:
        feats = self.proc(y[:16000 * 30], sampling_rate=16000, return_tensors="pt").input_features.to(self.ctx.device, self.dt)
        with self.torch.no_grad():
            ids = self.model.detect_language(feats)
        tok = self.proc.tokenizer.convert_ids_to_tokens(ids.tolist())[0]
        return tok.strip("<|>")

    def asr(self, audio, language, p):
        import soundfile as sf
        y, sr = sf.read(audio, dtype="float32", always_2d=True)
        y = y.mean(1)
        if sr != 16000:
            import librosa
            y = librosa.resample(y, orig_sr=sr, target_sr=16000)
        lang = language
        if not lang:
            try:
                lang = self._detect(y)
            except Exception as ex:
                self.ctx.log(f"언어 감지 실패: {ex}")
        gk = {"task": "transcribe"}
        if lang:
            gk["language"] = ISO.get(lang, lang)
        words = bool(p.get("word_timestamps", True))
        r = self.pipe({"raw": y, "sampling_rate": 16000}, return_timestamps="word" if words else True,
                      chunk_length_s=int(p.get("chunk_length_s", 30)), batch_size=int(p.get("batch_size", 8)), generate_kwargs=gk)
        chunks = r.get("chunks") or []
        if words:
            ws = [{"start": float(c["timestamp"][0] or 0), "end": float(c["timestamp"][1] or c["timestamp"][0] or 0),
                   "word": c["text"], "prob": None} for c in chunks]
            segs = group_words(ws)
        else:
            segs = [{"start": float(c["timestamp"][0] or 0), "end": float(c["timestamp"][1] or 0), "text": c["text"].strip()} for c in chunks]
        return {"language": lang or "", "segments": segs}
