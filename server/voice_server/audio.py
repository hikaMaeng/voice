"""음성 파일 처리 — 변환, 참고 구간 고르기·자르기, 결과 검사, 이어 붙이기.

참고 구간 규칙(WanAvatar 나레이션 스킬 narrate.py 에서 옮김, 실측 근거는 docs/reference-audio.md):
- 문장 경계에서만 자른다. 끝 쪽은 말이 끝나 조용해진 뒤 소리가 다시 커지는 지점 앞에서 자른다.
- 복제는 참고에 「이어서」 말한다 — 참고 끝에 걸린 소리가 출력 첫머리로 번진다(97 Hz 저음 → 첫머리 저음 8/40).
  그래서 끝에 0.4 s 무음을 붙인다.
- 파일 끝을 「쉼」으로 치지 않는다(다음 소리 도중에 잘려 있을 수 있다).
- Whisper 단어 시각은 늘어진다 → 쉼은 소리 크기로 잰다.
"""
from __future__ import annotations

import difflib
import re
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

REF_MIN, REF_MAX = 8.0, 15.0
LEAD_S, TAIL_S = 0.1, 0.4


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def to_wav(src: Path, dst: Path, sr: int | None = None, mono: bool = True) -> dict:
    """아무 형식(영상 포함) → PCM wav. sr 없으면 원래 표본율(최대 48 kHz)."""
    cmd = [ffmpeg(), "-v", "error", "-y", "-i", str(src), "-vn"]
    if mono:
        cmd += ["-ac", "1"]
    if sr:
        cmd += ["-ar", str(sr)]
    cmd += ["-c:a", "pcm_s16le", str(dst)]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg 변환 실패: " + r.stderr.decode("utf-8", "replace")[-400:])
    info = sf.info(str(dst))
    if not sr and info.samplerate > 48000:
        return to_wav(src, dst, 48000, mono)
    return {"sr": info.samplerate, "duration": round(info.duration, 3), "channels": info.channels}


def read_mono(p: Path) -> tuple[np.ndarray, int]:
    y, sr = sf.read(str(p), dtype="float32", always_2d=True)
    return y.mean(1), sr


def norm_text(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", s, flags=re.UNICODE).lower()


def match_rate(expected: str, heard: str) -> float:
    """글자 단위 일치율(문장부호·띄어쓰기 무시). 거친 자다 — 고유명사·숫자는 ASR 쪽이 틀리기도 한다."""
    a, b = norm_text(expected), norm_text(heard)
    if not a:
        return 1.0 if not b else 0.0
    return round(difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 4)


def quiet_finder(mono: np.ndarray, sr: int):
    """t 근처(±0.6 s)에서 가장 긴 무음 길이(초)를 돌려주는 함수."""
    hop = int(0.01 * sr)
    e = np.sqrt((mono[:len(mono) // hop * hop].reshape(-1, hop) ** 2).mean(1))
    level = float(np.median(e[e > 0.01])) if (e > 0.01).any() else 0.05
    silent = e < 0.03 * level

    def quiet(t: float) -> float:
        a, b = max(0, int((t - 0.6) * 100)), min(len(silent), int((t + 0.6) * 100))
        best = run = 0
        for k in range(a, b):
            run = run + 1 if silent[k] else 0
            best = max(best, run)
        return best / 100
    return quiet


def pick_window(segs: list[dict], file_dur: float, quiet=None) -> tuple[float, float, str]:
    """문장 경계에서 8~15 s 창. 말이 빽빽하고(쉼 비율 낮음) 1 s 넘는 쉼이 없는 창이 이긴다."""
    best = None
    for i in range(len(segs)):
        j = i
        while j < len(segs) and segs[j]["end"] - segs[i]["start"] <= REF_MAX:
            j += 1
        for k in range(j - 1, i - 1, -1):
            a, b = segs[i]["start"], segs[k]["end"]
            if b - a < REF_MIN:
                break
            speech = sum(s["end"] - s["start"] for s in segs[i:k + 1])
            gaps = [segs[t + 1]["start"] - segs[t]["end"] for t in range(i, k)]
            if quiet:
                pre = quiet(a)
                post = quiet(b) if b < file_dur - 0.6 else 0.0
            else:
                pre = a - segs[i - 1]["end"] if i > 0 else a
                post = segs[k + 1]["start"] - b if k + 1 < len(segs) else file_dur - b - 0.3
            score = (speech / (b - a) - (0.3 if gaps and max(gaps) > 1.0 else 0) + 0.01 * (b - a)
                     + 0.1 * (pre >= 0.3) + 0.2 * (post >= 0.3))
            if best is None or score > best[0]:
                best = (score, a, b, " ".join(s["text"].strip() for s in segs[i:k + 1]).strip())
    if best is None:
        return None
    return best[1], best[2], best[3]


def cut_bounds(mono: np.ndarray, sr: int, segs: list[dict], s0: float, s1: float) -> tuple[float, float]:
    """말 앞뒤 여유를 주되 이웃 소리는 넣지 않는다. 끝은 조용해진 뒤 다시 커지는 지점 앞에서."""
    dur = len(mono) / sr
    prev_end = max([s["end"] for s in segs if s["end"] <= s0 + 0.01] or [0.0])
    next_start = min([s["start"] for s in segs if s["start"] >= s1 - 0.01] or [dur])
    lo = max(0.0, s0 - 0.05, prev_end + 0.02 if prev_end > 0 else 0.0)
    hi = min(s1 + 0.25, next_start - 0.05, dur)
    hop = int(0.01 * sr)
    seg = mono[int(s1 * sr): int(hi * sr)]
    if len(seg) > hop:
        e = np.sqrt(np.convolve(seg ** 2, np.ones(hop) / hop, mode="valid")[::hop])
        speech = float(np.sqrt((mono[int(s0 * sr): int(s1 * sr)] ** 2).mean())) + 1e-8
        quiet = np.where(e < 0.05 * speech)[0]
        if len(quiet):
            again = np.where(e[quiet[0]:] > 0.15 * speech)[0]
            if len(again):
                hi = min(hi, s1 + (quiet[0] + again[0]) * 0.01 - 0.02)
    return lo, max(hi, s1)


def make_clip(mono: np.ndarray, sr: int, lo: float, hi: float) -> np.ndarray:
    clip = mono[int(lo * sr): int(hi * sr)].copy()
    clip = clip / (np.abs(clip).max() + 1e-8) * 0.9
    fade = min(int(0.03 * sr), len(clip) // 4)
    if fade:
        clip[:fade] *= np.linspace(0, 1, fade)
        clip[-fade:] *= np.linspace(1, 0, fade)
    return np.concatenate([np.zeros(int(LEAD_S * sr), np.float32), clip, np.zeros(int(TAIL_S * sr), np.float32)])


def speech_bounds(mono: np.ndarray, sr: int) -> tuple[float, float]:
    """수동 모드에서 구간을 안 줬을 때 — 앞뒤 무음만 걷어 낸다."""
    hop = int(0.01 * sr)
    e = np.sqrt((mono[:len(mono) // hop * hop].reshape(-1, hop) ** 2).mean(1))
    if not len(e):
        return 0.0, len(mono) / sr
    on = np.where(e > 0.05 * (e.max() + 1e-8))[0]
    if not len(on):
        return 0.0, len(mono) / sr
    return max(0.0, on[0] * 0.01 - 0.05), min(len(mono) / sr, (on[-1] + 1) * 0.01 + 0.1)


def median_f0(y: np.ndarray, sr: int) -> float:
    import librosa
    y16 = librosa.resample(y, orig_sr=sr, target_sr=16000)
    f0, vf, _ = librosa.pyin(y16, fmin=60, fmax=600, sr=16000, frame_length=1024)
    v = f0[vf & np.isfinite(f0)]
    return round(float(np.median(v)), 1) if len(v) else 0.0


def lead_low(path: Path, ref_f0: float) -> float:
    """첫 유성음이 참고 f0 의 0.6배 미만으로 시작하는 길이(초) — 참고 끝 소리가 번진 흔적. 받아쓰기는 이것을 못 잡는다."""
    import librosa
    if ref_f0 <= 0:
        return 0.0
    y, sr = librosa.load(str(path), sr=16000, duration=2.0)
    f0, vf, _ = librosa.pyin(y, fmin=50, fmax=600, sr=sr, frame_length=1024)
    n = 0
    for f, v in zip(f0, vf):
        if not v or not np.isfinite(f):
            continue
        if f < 0.6 * ref_f0:
            n += 1
        else:
            break
    return round(n * 256 / sr, 3)


def check_wav(p: Path, text: str) -> str:
    """기본 검사 — 문제 없으면 빈 문자열."""
    if not p.exists() or p.stat().st_size < 1000:
        return "파일 없음"
    w, sr = sf.read(str(p), dtype="float32")
    if not np.isfinite(w).all():
        return "NaN/Inf"
    if np.abs(w).max() < 0.02:
        return "무음"
    dur, n = len(w) / sr, max(1, len(norm_text(text)))
    if not 0.04 <= dur / n <= 0.6:
        return f"길이 이상 {dur:.1f}s/{n}자"
    return ""


def trim_edges(w: np.ndarray, sr: int, thr: float = 0.01) -> np.ndarray:
    idx = np.where(np.abs(w) > thr)[0]
    if not len(idx):
        return w
    a = max(0, idx[0] - int(0.02 * sr))
    b = min(len(w), idx[-1] + int(0.08 * sr))
    return w[a:b]


def assemble(parts: list[Path], out: Path, pause_s: float) -> dict:
    ws, sr0 = [], None
    for p in parts:
        w, sr = sf.read(str(p), dtype="float32", always_2d=True)
        w = w.mean(1)
        if sr0 is None:
            sr0 = sr
        elif sr != sr0:
            import librosa
            w = librosa.resample(w, orig_sr=sr, target_sr=sr0)
        ws.append(trim_edges(w, sr0))
    gap = np.zeros(int(pause_s * (sr0 or 24000)), np.float32)
    seq = []
    for i, w in enumerate(ws):
        if i:
            seq.append(gap)
        seq.append(w)
    y = np.concatenate(seq) if seq else np.zeros(1, np.float32)
    peak = float(np.abs(y).max())
    if peak > 0.99:
        y = y / peak * 0.98
    sf.write(str(out), y, sr0 or 24000)
    return {"sr": sr0, "duration": round(len(y) / (sr0 or 24000), 3)}


def split_text(text: str, mode: str) -> list[str]:
    t = text.replace("\r\n", "\n").strip()
    if mode == "none":
        return [" ".join(l.strip() for l in t.splitlines() if l.strip())] if t else []
    if mode == "line":
        return [l.strip() for l in t.splitlines() if l.strip()]
    return [" ".join(l.strip() for l in p.splitlines() if l.strip()) for p in re.split(r"\n\s*\n", t) if p.strip()]
