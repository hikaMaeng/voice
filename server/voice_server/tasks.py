"""작업 본체 — 참조 세트 만들기 · TTS 생성 · ASR · 환경 설치 · 모델 받기.

TTS 결과 기록(`generations` 표)은 「그때 쓴 모든 값」을 담는다: 엔진·모델 지문(경로·HF 커밋·파일 해시)·환경 판(freeze 해시)·
서비스 커밋·장치·언어·원문과 실제로 넘긴 글·채운 파라미터 전부·문단별 시드·참고 세트 사본(음성·전사문·구간·f0).
그래서 참고 세트를 지우거나 고쳐도 결과를 불러오면 생성 당시 설정이 그대로 돌아온다.
"""
from __future__ import annotations

import hashlib
import random
import shutil
import subprocess
import time
from pathlib import Path

import soundfile as sf

from . import audio as A
from . import envs
from . import models as M
from . import scheduler as S
from .catalog import ENGINES, MODELS, resolve_params
from .config import DATA, ROOT, settings
from .db import new_id, store
from .textnorm import latin_letters_ko, read_numbers

UPLOADS, REFS, GENS, TRANS = DATA / "uploads", DATA / "refs", DATA / "generations", DATA / "transcripts"
for _d in (UPLOADS, REFS, GENS, TRANS):
    _d.mkdir(parents=True, exist_ok=True)


def service_version() -> dict:
    try:
        sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
                                    capture_output=True, text=True).stdout.strip())
    except OSError:
        sha, dirty = "", False
    from . import __version__
    return {"version": __version__, "git": sha, "dirty": dirty}


SERVICE = service_version()


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _devices(w) -> list[dict]:
    from .resources import gpus
    gs = {g["uuid"]: g for g in gpus()}
    return [{"index": gs[u]["index"], "name": gs[u]["name"], "uuid": u} for u in (w.gpu_uuids if w else []) if u in gs] or [{"name": "CPU"}]


# ───────────────────────── 업로드 ─────────────────────────

def save_upload(name: str, data: bytes) -> dict:
    uid = new_id()
    d = UPLOADS / uid
    d.mkdir(parents=True)
    safe = "".join(c for c in Path(name).name if c not in '<>:"/\\|?*') or "audio"
    src = d / safe
    src.write_bytes(data)
    try:
        info = A.to_wav(src, d / "audio.wav")
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    row = {"id": uid, "name": safe, "file": safe, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), **info}
    return store.put("uploads", row)


def upload_audio(uid: str, sr: int | None = None) -> Path:
    d = UPLOADS / uid
    if not sr:
        return d / "audio.wav"
    p = d / f"audio{sr // 1000}k.wav"
    if not p.exists():
        A.to_wav(d / "audio.wav", p, sr)
    return p


# ───────────────────────── ASR 공통 ─────────────────────────

def _asr_call(job, model_id: str, wav: Path, language: str | None, params: dict, stage: str) -> tuple[dict, object]:
    eng = MODELS[model_id]["engine"]
    w = S.acquire(job, eng, model_id)
    try:
        job.set(stage=stage)
        t0 = time.time()
        r = w.call("asr", {"audio": str(wav), "language": None if language in (None, "", "auto") else language,
                          "params": params}, cancel=job.cancel,
                   on_progress=lambda m: job.set(progress=m.get("pct")) if m.get("pct") is not None else None)
        r["infer_s"] = round(time.time() - t0, 2)
        return r, _devices(w)
    finally:
        S.release(job, w)


def asr_job(job) -> dict:
    p = job.params
    model_id = p["model"]
    eng = MODELS[model_id]["engine"]
    up = store.get("uploads", p["upload_id"])
    if not up:
        raise RuntimeError("업로드 파일이 없다")
    params = resolve_params(eng, p.get("params") or {})
    lang = p.get("language") or params.get("language")
    wav = upload_audio(up["id"], 16000)
    t0 = time.time()
    r, devs = _asr_call(job, model_id, wav, lang, params, f"받아 적는 중 — {MODELS[model_id]['label']}")
    row = {"id": new_id(), "name": p.get("name") or up["name"], "kind": "asr",
           "upload": {"id": up["id"], "name": up["name"], "duration": up.get("duration"), "sha256": up.get("sha256")},
           "engine": eng, "engine_label": ENGINES[eng]["label"], "model": M.fingerprint(model_id),
           "model_label": MODELS[model_id]["label"], "env": envs.key_versions(ENGINES[eng]["env"]), "service": SERVICE,
           "device": devs, "language_requested": lang, "language": r.get("language"), "params": params,
           "segments": r.get("segments", []), "timings": {"infer_s": r.get("infer_s"), "total_s": round(time.time() - t0, 2)}}
    store.put("transcripts", row)
    return {"transcript_id": row["id"], "segments": len(row["segments"]), "language": row["language"]}


# ───────────────────────── 참조 세트 ─────────────────────────

def ref_job(job) -> dict:
    p = job.params
    up = store.get("uploads", p["upload_id"])
    if not up:
        raise RuntimeError("업로드 파일이 없다")
    consent = p.get("consent") or {}
    if not consent.get("agreed") or consent.get("basis") not in ("self", "other_consent", "licensed", "synthetic"):
        raise RuntimeError("목소리 사용 동의(근거)를 고르고 확인해야 참조 세트를 만들 수 있다")
    rid = new_id()
    d = REFS / rid
    d.mkdir(parents=True)
    shutil.copy2(UPLOADS / up["id"] / up["file"], d / ("source" + Path(up["file"]).suffix))
    src = UPLOADS / up["id"] / "audio.wav"
    mono, sr = A.read_mono(src)
    dur = len(mono) / sr
    segs, asr_info, lang = [], None, p.get("language") or ""
    auto = p.get("mode", "auto") == "auto"
    if auto:
        model_id = p.get("asr_model") or settings.get("default_asr_model")
        eng = MODELS[model_id]["engine"]
        params = resolve_params(eng, {**(p.get("asr_params") or {}), "word_timestamps": True})
        r, devs = _asr_call(job, model_id, upload_audio(up["id"], 16000), lang or None, params, "참고 음성 받아 적는 중")
        for s in r.get("segments", []):
            ws = s.get("words") or []
            segs.append({"start": round(ws[0]["start"] if ws else s["start"], 2),
                         "end": round(ws[-1]["end"] if ws else s["end"], 2), "text": s["text"].strip()})
        lang = lang or r.get("language") or ""
        asr_info = {"model": M.fingerprint(model_id), "model_label": MODELS[model_id]["label"], "params": params,
                    "language": r.get("language"), "device": devs}
    job.set(stage="구간 고르는 중")
    start, end = p.get("start"), p.get("end")
    picked = "manual"
    if start is not None and end is not None:
        s0, s1 = float(start), float(end)
        auto_text = " ".join(s["text"] for s in segs if s["end"] > s0 and s["start"] < s1).strip()
    elif segs:
        win = A.pick_window(segs, dur, A.quiet_finder(mono, sr))
        if win:
            s0, s1, auto_text = win
            picked = "auto"
        else:   # 8 s 보다 짧다 — 말소리 전체
            s0, s1 = segs[0]["start"], segs[-1]["end"]
            auto_text = " ".join(s["text"] for s in segs).strip()
            picked = "whole"
    else:
        s0, s1 = A.speech_bounds(mono, sr)
        auto_text = ""
        picked = "whole"
    lo, hi = A.cut_bounds(mono, sr, segs, s0, s1) if segs else (s0, s1)
    clip = A.make_clip(mono, sr, lo, hi)
    sf.write(str(d / "clip.wav"), clip, sr)
    text = (p.get("text") or "").strip() or auto_text
    if not text:
        raise RuntimeError("참고 전사문이 비었다 — 자동 모드를 쓰거나 직접 넣는다")
    if not lang:
        raise RuntimeError("참고 음성 언어를 모른다 — 직접 고른다")
    job.set(stage="f0 재는 중")
    row = {"id": rid, "name": p.get("name") or Path(up["name"]).stem, "rev": 1, "mode": "auto" if auto else "manual",
           "picked": picked, "upload": {"id": up["id"], "name": up["name"], "sha256": up.get("sha256"), "duration": round(dur, 3)},
           "source_file": "source" + Path(up["file"]).suffix, "language": lang, "text": text, "auto_text": auto_text,
           "window": [round(s0, 2), round(s1, 2)], "cut": [round(lo, 3), round(hi, 3)],
           "pad": {"lead_s": A.LEAD_S, "tail_s": A.TAIL_S}, "clip_duration": round(len(clip) / sr, 3), "sr": sr,
           "f0_median": A.median_f0(clip, sr), "clip_sha256": sha_file(d / "clip.wav"), "segments": segs, "asr": asr_info,
           "consent": {"basis": consent["basis"], "note": consent.get("note", ""), "agreed": True,
                       "agreed_at": time.strftime("%Y-%m-%d %H:%M:%S")},
           "service": SERVICE}
    store.put("refs", row)
    return {"ref_id": rid, "text": text, "language": lang, "window": row["window"]}


def recut_ref(rid: str, start: float, end: float, text: str | None) -> dict:
    ref = store.get("refs", rid)
    if not ref:
        raise KeyError(rid)
    mono, sr = A.read_mono(UPLOADS / ref["upload"]["id"] / "audio.wav")
    segs = ref.get("segments") or []
    lo, hi = A.cut_bounds(mono, sr, segs, start, end) if segs else (start, end)
    clip = A.make_clip(mono, sr, lo, hi)
    d = REFS / rid
    sf.write(str(d / "clip.wav"), clip, sr)
    auto_text = " ".join(s["text"] for s in segs if s["end"] > start and s["start"] < end).strip()
    ref.update({"window": [round(start, 2), round(end, 2)], "cut": [round(lo, 3), round(hi, 3)], "picked": "manual",
                "auto_text": auto_text or ref.get("auto_text", ""),
                # 사람이 고친 전사문은 지킨다(새 글을 직접 주면 그것) — 구간이 바뀌었으니 화면이 확인을 권한다
                "text": (text or "").strip() or (ref["text"] if ref.get("text_edited") else auto_text or ref["text"]),
                "clip_duration": round(len(clip) / sr, 3), "f0_median": A.median_f0(clip, sr),
                "clip_sha256": sha_file(d / "clip.wav"), "rev": int(ref.get("rev", 1)) + 1})
    return store.put("refs", ref)


# ───────────────────────── TTS ─────────────────────────

def _ref_for(p: dict, gdir: Path) -> dict:
    """참고 세트를 결과 폴더에 복사해 둔다(나중에 세트를 지우거나 고쳐도 재현되게)."""
    (gdir / "ref").mkdir(parents=True, exist_ok=True)
    if p.get("ref_id"):
        ref = store.get("refs", p["ref_id"])
        if not ref:
            raise RuntimeError("참조 세트가 없다")
        shutil.copy2(REFS / ref["id"] / "clip.wav", gdir / "ref" / "clip.wav")
        snap = {k: ref.get(k) for k in ("id", "name", "rev", "language", "text", "window", "cut", "pad", "f0_median",
                                         "clip_sha256", "clip_duration", "mode", "picked", "consent", "upload")}
    elif p.get("ref_from_generation"):
        g = store.get("generations", p["ref_from_generation"])
        if not g:
            raise RuntimeError("원본 결과가 없다")
        shutil.copy2(GENS / g["id"] / "ref" / "clip.wav", gdir / "ref" / "clip.wav")
        snap = dict(g["ref"])
        snap["from_generation"] = g["id"]
    else:
        raise RuntimeError("참조 세트를 고른다")
    if p.get("ref_text"):   # 폼에서 전사문을 이번 생성에만 고쳐 쓸 때
        snap["text"] = p["ref_text"].strip()
    max_s = ENGINES[MODELS[p["model"]]["engine"]].get("max_ref_s")
    if max_s and (snap.get("clip_duration") or 0) > max_s:
        _fit_ref(snap, store.get("refs", snap.get("id") or "") if p.get("ref_id") else None, gdir, max_s, p.get("job"))
    (gdir / "ref" / "text.txt").write_text(snap["text"], encoding="utf-8")
    return snap


def _fit_ref(snap: dict, ref: dict | None, gdir: Path, max_s: float, job=None) -> None:
    """참고 길이에 상한이 있는 엔진(X-Voice: 12 s 를 넘으면 오디오만 자르고 전사문은 그대로 둬 소리와 글이 어긋난다)용 —
    세트의 문장 구간 안에서 상한에 맞는 가장 긴 연속 구간을 골라 다시 자르고, 그 구간의 전사문을 쓴다."""
    segs = (ref or {}).get("segments") or []
    if not segs:
        raise RuntimeError(f"이 엔진은 참고가 {max_s:.0f} s 이하여야 한다(지금 {snap.get('clip_duration')} s). "
                           "자동 모드 세트를 쓰거나 짧게 다시 자른 세트를 쓴다")
    lo0, hi0 = ref["cut"]
    inside = [x for x in segs if x["start"] >= lo0 - 0.05 and x["end"] <= hi0 + 0.05]
    budget = max_s - A.LEAD_S - A.TAIL_S - 0.3
    best = None
    for i in range(len(inside)):
        for k in range(i, len(inside)):
            span = inside[k]["end"] - inside[i]["start"]
            if span > budget:
                break
            if best is None or span > best[1] - best[0]:
                best = (inside[i]["start"], inside[k]["end"], i, k)
    if best is None:
        raise RuntimeError(f"참고 안에 {max_s:.0f} s 이하 문장 구간이 없다 — 짧은 세트를 쓴다")
    s0, s1, i, k = best
    mono, sr = A.read_mono(UPLOADS / ref["upload"]["id"] / "audio.wav")
    lo, hi = A.cut_bounds(mono, sr, segs, s0, s1)
    clip = A.make_clip(mono, sr, lo, hi)
    sf.write(str(gdir / "ref" / "clip.wav"), clip, sr)
    text = " ".join(x["text"] for x in inside[i:k + 1]).strip()
    snap["engine_fit"] = {"max_s": max_s, "from_text": snap["text"], "from_cut": [lo0, hi0], "cut": [round(lo, 3), round(hi, 3)],
                          "text_source": "ASR 구간(사람이 고친 전사문은 구간별로 나눌 수 없다)" if ref.get("text_edited") else "ASR 구간"}
    snap.update({"text": text, "clip_duration": round(len(clip) / sr, 3), "clip_sha256": sha_file(gdir / "ref" / "clip.wav")})
    if job is not None:
        job.say(f"참고를 {snap['clip_duration']} s 로 다시 잘랐다(엔진 상한 {max_s} s): {text[:60]}")


def tts_job(job) -> dict:
    p = job.params
    model_id = p["model"]
    eng = MODELS[model_id]["engine"]
    e = ENGINES[eng]
    params = resolve_params(eng, p.get("params") or {})
    seed = params["seed"] if params["seed"] >= 0 else random.randint(0, 2**31 - 1)
    params["seed"] = seed
    language = p.get("language") or "ko"
    gid = new_id()
    gdir = GENS / gid
    (gdir / "parts").mkdir(parents=True)
    ref = _ref_for({**p, "job": job}, gdir)
    text = p["text"]
    used = read_numbers(text) if params.get("normalize_numbers") and language == "ko" else text
    pieces = A.split_text(used, params["split"])
    if not pieces:
        raise RuntimeError("대본이 비었다")
    eng_params = {k: params[k] for k in (q["key"] for q in e["params"])}
    orig = A.split_text(text, params["split"])
    orig = orig if len(orig) == len(pieces) else pieces
    parts = [{"i": i, "text": t, "text_orig": orig[i], "seed": seed + i, "file": f"parts/p{i:03d}.wav", "attempts": 0, "checks": {}}
             for i, t in enumerate(pieces)]
    t_start = time.time()
    timings = {"wait_load_s": 0.0, "gen_s": 0.0, "verify_s": 0.0}   # wait_load_s = 자원 대기 + 모델 싣기(상주면 0 에 가깝다)
    todo = list(parts)
    devs = []
    for attempt in range(params["retries"] + 1):
        if not todo:
            break
        t_acq = time.time()
        w = S.acquire(job, eng, model_id)
        timings["wait_load_s"] += time.time() - t_acq
        devs = _devices(w)
        try:
            job.set(stage=f"생성 중 ({len(todo)}개)" + (f" — 다시 뽑기 {attempt}" if attempt else ""))
            for pt in todo:
                pt["seed"] = seed + pt["i"] + 7919 * attempt
                pt["attempts"] += 1
            t0 = time.time()
            done_before = len(parts) - len(todo)

            def prog(m, n0=done_before):
                if m.get("done") is not None:
                    job.set(progress=0.9 * (n0 + m["done"]) / len(parts))
                if m.get("log"):
                    job.say(m["log"])
            r = w.call("tts", {"ref": {"audio": str(gdir / "ref" / "clip.wav"), "text": ref["text"], "language": ref["language"]},
                               "language": language, "params": eng_params,
                               "items": [{"text": pt["text"], "out": str(gdir / pt["file"]), "seed": pt["seed"]} for pt in todo]},
                       on_progress=prog, cancel=job.cancel)
            timings["gen_s"] += time.time() - t0
            for pt, it in zip(todo, r.get("items", [])):
                pt.update({"infer_s": it.get("infer_s"), "sr": it.get("sr"), "dur": it.get("dur")})
                if it.get("seed_used") is not None:
                    pt["seed_used"] = it["seed_used"]
        finally:
            S.release(job, w)
        # 검사
        bad = []
        outliers = A.rate_outliers(parts)
        for pt in todo:
            if job.cancel.is_set():
                raise S.Cancelled()
            why = A.check_wav(gdir / pt["file"], pt["text"]) or outliers.get(pt["i"], "")
            pt["checks"]["basic"] = why or "ok"
            if not why and params["lead_low_check"] and ref.get("f0_median"):
                ll = A.lead_low(gdir / pt["file"], ref["f0_median"])
                pt["checks"]["lead_low_s"] = ll
                if ll >= 0.15:
                    why = f"첫머리 저음 {ll:.2f}s"
            if why:
                bad.append(pt)
                job.say(f"문단 {pt['i'] + 1} 불량: {why}")
        if params["verify"]:
            vm = settings.get("default_asr_model")
            check_list = [pt for pt in todo if pt not in bad]
            if check_list:
                t0 = time.time()
                veng = MODELS[vm]["engine"]
                vw = S.acquire(job, veng, vm)
                try:
                    vparams = resolve_params(veng, {"word_timestamps": False})
                    for k, pt in enumerate(check_list):
                        job.set(stage=f"받아쓰기 검증 {k + 1}/{len(check_list)}")
                        rr = vw.call("asr", {"audio": str(gdir / pt["file"]), "language": language, "params": vparams}, cancel=job.cancel)
                        heard = " ".join(s["text"] for s in rr.get("segments", []))
                        # ASR 은 숫자·영문을 아라비아 숫자·로마자로 적는다(「에이아이, 일편」→「AI 1편」 실측 0.61 오판).
                        # 넘긴 글 · 원문 · 숫자를 푼 받아쓰기 중 가장 잘 맞는 짝을 쓴다
                        rate = max(A.match_rate(pt["text"], heard), A.match_rate(pt["text_orig"], heard),
                                   A.match_rate(pt["text"], latin_letters_ko(read_numbers(heard))))
                        segs = rr.get("segments") or []
                        tail = A.tail_noise(gdir / pt["file"], segs[-1]["end"]) if segs else 0.0
                        pt["checks"].update({"match": rate, "heard": heard, "verify_model": vm, "tail_noise_s": tail})
                        if rate < params["verify_min"]:
                            bad.append(pt)
                            job.say(f"문단 {pt['i'] + 1} 일치율 {rate:.3f} < {params['verify_min']}")
                        elif tail >= 1.0:
                            bad.append(pt)
                            job.say(f"문단 {pt['i'] + 1} 말이 끝난 뒤 큰 소리 {tail:.1f}s")
                finally:
                    S.release(job, vw)
                timings["verify_s"] += time.time() - t0
        todo = bad if attempt < params["retries"] else []
        for pt in bad:
            pt["checks"]["failed"] = attempt >= params["retries"]
    if job.cancel.is_set():
        raise S.Cancelled()
    job.set(stage="이어 붙이는 중", progress=0.95)
    out = A.assemble([gdir / pt["file"] for pt in parts], gdir / "output.wav", params["pause_s"])
    row = {"id": gid, "name": p.get("name") or used[:40], "kind": "tts", "status": "ok" if not any(pt["checks"].get("failed") for pt in parts) else "warn",
           "engine": eng, "engine_label": e["label"], "model": M.fingerprint(model_id), "model_label": MODELS[model_id]["label"],
           "license": MODELS[model_id]["license"], "commercial": MODELS[model_id]["commercial"],
           "aux_models": [M.fingerprint(a) for a in MODELS[model_id].get("requires", [])],
           "env": envs.key_versions(e["env"]), "service": SERVICE, "device": devs,
           "language": language, "text": text, "text_used": used, "params": params, "seed": seed, "ref": ref,
           "parts": parts, "output": {"file": "output.wav", **out, "sha256": sha_file(gdir / "output.wav")},
           "timings": {k: round(v, 2) for k, v in timings.items()} | {"total_s": round(time.time() - t_start, 2)}}
    store.put("generations", row)
    return {"generation_id": gid, "duration": out["duration"], "status": row["status"]}


# ───────────────────────── 설치·다운로드 ─────────────────────────

def env_job(job) -> dict:
    env = job.params["env"]

    def log(line):
        job.say(line[:2000])
        if line.startswith("$ "):
            job.set(stage=line[2:120])
    return envs.install(env, log, job.cancel)


def download_job(job) -> dict:
    ids = [job.params["model"]] + [r for r in MODELS[job.params["model"]].get("requires", []) if not M.check(r)["ok"]]
    out = {}
    for k, mid in enumerate(ids):
        job.set(stage=f"받는 중 {MODELS[mid]['label']} ({k + 1}/{len(ids)})")

        def log(line, done_bytes=None, total=None, k=k):
            if line:
                job.say(line)
            if done_bytes is not None and total:
                job.set(progress=(k + min(1.0, done_bytes / total)) / len(ids))
                job.extra["bytes"] = [done_bytes, total]
        out[mid] = M.download(mid, log, job.cancel)
    return out
