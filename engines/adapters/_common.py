"""어댑터 공용 — 언어 이름 바꾸기, 참고 음성 프롬프트 캐시."""
from __future__ import annotations

NAMES = {"ko": "Korean", "ja": "Japanese", "en": "English", "zh": "Chinese", "de": "German", "fr": "French",
         "es": "Spanish", "it": "Italian", "pt": "Portuguese", "ru": "Russian", "yue": "Cantonese"}


def lang_name(code: str) -> str:
    return NAMES.get(code, code)


import inspect
import os

VENDOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor")


def vendor(*parts: str) -> str:
    return os.path.join(VENDOR, *parts)


def filtered(fn, **kw):
    """엔진 함수가 받는 인자만 넘긴다(판마다 인자 이름이 다르다). 못 넘긴 키는 돌려줘 로그에 남긴다."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return kw, []
    if any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
        return kw, []
    ok = {k: v for k, v in kw.items() if k in sig.parameters}
    return ok, [k for k in kw if k not in ok]


def group_words(words: list[dict], max_gap: float = 0.8, max_dur: float = 12.0) -> list[dict]:
    """단어 시각 → 구간. 문장 끝 부호·긴 쉼·최대 길이에서 끊는다."""
    segs, cur = [], []
    for w in words:
        if cur and (w["start"] - cur[-1]["end"] > max_gap or w["end"] - cur[0]["start"] > max_dur):
            segs.append(cur)
            cur = []
        cur.append(w)
        if w["word"].strip()[-1:] in ".?!。？！":
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    out = []
    for s in segs:
        text = "".join(x["word"] for x in s).strip()
        if text:
            out.append({"start": round(s[0]["start"], 3), "end": round(s[-1]["end"], 3), "text": text, "words": s})
    return out


def cuda_dll_dirs() -> None:
    """Windows: pip 의 nvidia-* 휠(cuBLAS·cuDNN) DLL 을 찾게 한다(CTranslate2 가 PATH 에서 찾는다)."""
    if os.name != "nt":
        return
    import site
    for sp in site.getsitepackages():
        base = os.path.join(sp, "nvidia")
        if not os.path.isdir(base):
            continue
        for sub in os.listdir(base):
            b = os.path.join(base, sub, "bin")
            if os.path.isdir(b):
                os.add_dll_directory(b)
                os.environ["PATH"] = b + os.pathsep + os.environ.get("PATH", "")


def energy_segments(y, sr: int, min_silence_s: float = 0.35, max_len_s: float = 15.0, thr: float = 0.04):
    """시각을 주지 않는 ASR 용 — 소리 크기로 말 구간을 나눈다. [(시작 s, 끝 s), …]. 긴 구간은 가장 조용한 곳에서 자른다."""
    import numpy as np
    hop = max(1, int(0.02 * sr))
    n = len(y) // hop
    if n == 0:
        return []
    e = np.sqrt((y[:n * hop].reshape(n, hop) ** 2).mean(1))
    level = float(np.percentile(e, 95)) + 1e-8
    voiced = e > thr * level
    gap = int(min_silence_s / 0.02)
    spans, start, quiet = [], None, 0
    for k, v in enumerate(voiced):
        if v:
            if start is None:
                start = k
            quiet = 0
        elif start is not None:
            quiet += 1
            if quiet >= gap:
                spans.append([start, k - quiet + 1])
                start, quiet = None, 0
    if start is not None:
        spans.append([start, n])
    out, lim = [], int(max_len_s / 0.02)
    for a, b in spans:
        while b - a > lim:   # 너무 길면 뒤쪽 절반에서 가장 조용한 프레임으로 자른다
            cut = a + lim // 2 + int(np.argmin(e[a + lim // 2: a + lim]))
            out.append((a, cut))
            a = cut
        out.append((a, b))
    pad = 0.1
    return [(max(0.0, a * 0.02 - pad), min(len(y) / sr, b * 0.02 + pad)) for a, b in out if (b - a) * 0.02 >= 0.2]


class PromptCache:
    """참고 음성(경로+전사문) → 엔진의 복제 프롬프트. 같은 세트로 여러 번 만들 때 다시 인코딩하지 않는다.
    키: (경로, 파일 크기·mtime, 전사문). 상한 8개 — 넘으면 가장 오래된 것을 버린다. 작업자 프로세스 수명 동안."""

    def __init__(self, build, limit: int = 8):
        self.build, self.limit, self._d = build, limit, {}

    def get(self, ref: dict):
        import os
        st = os.stat(ref["audio"])
        key = (ref["audio"], st.st_size, st.st_mtime, ref.get("text", ""), ref.get("language", ""))
        if key not in self._d:
            if len(self._d) >= self.limit:
                self._d.pop(next(iter(self._d)))
            self._d[key] = self.build(ref)
        return self._d[key]
