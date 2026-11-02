"""HTTP API + 정적 웹 — 계약은 docs/api.md."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import envs
from . import models as M
from . import resources
from . import scheduler as S
from . import tasks as T
from .catalog import ENGINES, LANGS, MODELS, visible
from .config import DATA, WEB_DIST, settings
from .db import store
from .subtitles import render

app = FastAPI(title="voice", version=T.SERVICE["version"])


def _404(what="없다"):
    raise HTTPException(404, what)


@app.exception_handler(KeyError)
async def _key(_, ex):
    return JSONResponse({"detail": f"없다: {ex}"}, status_code=404)


@app.exception_handler(RuntimeError)
async def _rt(_, ex):
    return JSONResponse({"detail": str(ex)}, status_code=400)


# ───────────────────────── 상태·설정 ─────────────────────────

@app.get("/api/health")
def health():
    return {"ok": True, "service": T.SERVICE, "data_dir": str(DATA)}


@app.get("/api/system")
def system():
    s = resources.system()
    s["gpus"] = S.device_view()
    return {**s, "workers": S.workers_view(), "service": T.SERVICE, "data_dir": str(DATA)}


@app.get("/api/settings")
def get_settings():
    return settings.all()


@app.put("/api/settings")
def put_settings(patch: dict):
    try:
        out = settings.update(patch)
        if {"model_root", "model_paths"} & set(patch):
            M.invalidate()
        return out
    except KeyError as ex:
        raise HTTPException(400, str(ex))


@app.post("/api/settings/reset")
def reset_settings():
    return settings.reset()


# ───────────────────────── 카탈로그·모델·환경 ─────────────────────────

@app.get("/api/catalog")
def catalog():
    eng, mods = visible(bool(settings.get("show_test_engines")))
    env_names = sorted({e["env"] for e in eng.values()})
    return {"languages": LANGS, "engines": eng,
            "models": {k: {**v, "check": M.check_cached(k), "location": str(M.location(k))} for k, v in mods.items()},
            "envs": {n: envs.status(n) for n in env_names},
            "defaults": {"tts_model": settings.get("default_tts_model"), "asr_model": settings.get("default_asr_model")}}


@app.get("/api/models/{mid}")
def model(mid: str):
    if mid not in MODELS:
        _404()
    return {**M.summary(mid), "location": str(M.location(mid)), "fingerprint": M.fingerprint(mid) if M.check(mid)["ok"] else None}


class PathBody(BaseModel):
    path: str | None = None


@app.put("/api/models/{mid}/path")
def model_path(mid: str, body: PathBody):
    if mid not in MODELS:
        _404()
    return M.set_path(mid, (body.path or "").strip() or None)


@app.post("/api/models/{mid}/download")
def model_download(mid: str):
    if mid not in MODELS or MODELS[mid].get("builtin"):
        _404()
    return S.submit(S.Job("download", f"받기 {MODELS[mid]['label']}", {"model": mid}), T.download_job).view()


@app.post("/api/envs/{env}/install")
def env_install(env: str):
    if not envs.manifest(env):
        _404("설치 정의 없음")
    for j in S.JOBS.values():
        if j.kind == "env" and j.params.get("env") == env and not j.finished:
            raise HTTPException(409, "이미 설치 중")
    return S.submit(S.Job("env", f"환경 설치 {env}", {"env": env}), T.env_job).view()


@app.get("/api/envs")
def env_list():
    names = sorted({e["env"] for e in ENGINES.values()})
    return {n: envs.status(n) for n in names}


# ───────────────────────── 작업·작업자 ─────────────────────────

@app.get("/api/jobs")
def jobs():
    live = {j.id: j.view() for j in S.JOBS.values()}
    for row in store.list("jobs", 200):   # 서버 재시작 전 작업(끝난 것만 기록돼 있다)
        if row["id"] not in live:
            live[row["id"]] = {k: v for k, v in row.items() if k != "log"} | {"persisted": True}
    return sorted(live.values(), key=lambda j: -j["created"])


@app.get("/api/jobs/{jid}")
def job(jid: str):
    j = S.JOBS.get(jid)
    if j:
        return j.view(with_log=True)
    row = store.get("jobs", jid)
    return row or _404()


@app.post("/api/jobs/{jid}/cancel")
def job_cancel(jid: str):
    return S.cancel(jid)


@app.get("/api/workers")
def workers():
    return S.workers_view()


@app.post("/api/workers/{pid}/stop")
def worker_stop(pid: int):
    return {"stopped": S.stop_worker(pid)}


class Preload(BaseModel):
    model: str


@app.post("/api/workers/preload")
def preload(body: Preload):
    mid = body.model
    if mid not in MODELS:
        _404()

    def fn(job):
        w = S.acquire(job, MODELS[mid]["engine"], mid)
        S.release(job, w)
        return {"pid": w.pid}
    return S.submit(S.Job("load", f"미리 싣기 {MODELS[mid]['label']}", {"model": mid}), fn).view()


# ───────────────────────── 업로드 ─────────────────────────

@app.post("/api/uploads")
async def upload(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "빈 파일")
    return T.save_upload(file.filename or "audio", data)


@app.get("/api/uploads")
def uploads():
    return store.list("uploads")


@app.get("/api/uploads/{uid}/audio")
def upload_file(uid: str):
    p = T.UPLOADS / uid / "audio.wav"
    return FileResponse(p, media_type="audio/wav") if p.exists() else _404()


@app.delete("/api/uploads/{uid}")
def upload_delete(uid: str):
    store.delete("uploads", uid)
    shutil.rmtree(T.UPLOADS / uid, ignore_errors=True)
    return {"deleted": uid}


# ───────────────────────── 참조 세트 ─────────────────────────

class RefCreate(BaseModel):
    upload_id: str
    name: str = ""
    mode: str = "auto"              # auto | manual
    language: str = ""              # 비우면(auto) ASR 이 감지
    text: str = ""                  # 비우면(auto) ASR 결과
    start: float | None = None
    end: float | None = None
    asr_model: str = ""
    asr_params: dict = {}
    consent: dict = {}


@app.post("/api/refs")
def ref_create(body: RefCreate):
    if body.mode == "manual" and (not body.text.strip() or not body.language):
        raise HTTPException(400, "수동 모드는 언어와 전사문을 넣어야 한다")
    if body.asr_model and body.asr_model not in MODELS:
        _404("ASR 모델")
    return S.submit(S.Job("ref", f"참조 세트 {body.name or body.upload_id}", body.model_dump()), T.ref_job).view()


@app.get("/api/refs")
def refs():
    return store.list("refs")


@app.get("/api/refs/{rid}")
def ref(rid: str):
    return store.get("refs", rid) or _404()


class RefPatch(BaseModel):
    name: str | None = None
    text: str | None = None
    language: str | None = None


@app.patch("/api/refs/{rid}")
def ref_patch(rid: str, body: RefPatch):
    r = store.get("refs", rid) or _404()
    for k, v in body.model_dump(exclude_none=True).items():
        r[k] = v.strip() if isinstance(v, str) else v
    if body.text is not None:
        r["text_edited"] = True   # 다시 자르기가 사람이 고친 전사문을 덮지 않게
    r["rev"] = int(r.get("rev", 1)) + 1
    return store.put("refs", r)


class Recut(BaseModel):
    start: float
    end: float
    text: str | None = None


@app.post("/api/refs/{rid}/recut")
def ref_recut(rid: str, body: Recut):
    if body.end - body.start < 1.0:
        raise HTTPException(400, "구간이 1초보다 짧다")
    return T.recut_ref(rid, body.start, body.end, body.text)


@app.get("/api/refs/{rid}/audio")
def ref_audio(rid: str, which: str = "clip"):
    r = store.get("refs", rid) or _404()
    p = T.REFS / rid / ("clip.wav" if which == "clip" else r["source_file"])
    if which != "clip":
        p = T.UPLOADS / r["upload"]["id"] / "audio.wav"
    return FileResponse(p, media_type="audio/wav") if p.exists() else _404()


@app.delete("/api/refs/{rid}")
def ref_delete(rid: str):
    store.delete("refs", rid)
    shutil.rmtree(T.REFS / rid, ignore_errors=True)
    return {"deleted": rid}


# ───────────────────────── TTS ─────────────────────────

class TTSBody(BaseModel):
    model: str
    text: str
    language: str = "ko"
    ref_id: str = ""
    ref_from_generation: str = ""
    ref_text: str = ""
    params: dict = {}
    name: str = ""


@app.post("/api/tts")
def tts(body: TTSBody):
    if body.model not in MODELS or MODELS[body.model]["kind"] != "tts":
        _404("TTS 모델")
    if not body.text.strip():
        raise HTTPException(400, "대본이 비었다")
    return S.submit(S.Job("tts", f"TTS {MODELS[body.model]['label']} — {body.text.strip()[:24]}", body.model_dump()), T.tts_job).view()


class PreviewBody(BaseModel):
    text: str
    language: str = "ko"
    split: str = "paragraph"
    normalize_numbers: bool = True


@app.post("/api/text/preview")
def text_preview(body: PreviewBody):
    """생성 전에 엔진에 넘길 글(숫자 풀기)과 문단 나누기를 본다 — tts_job 과 같은 함수."""
    from . import audio as A
    from .textnorm import read_numbers
    used = read_numbers(body.text) if body.normalize_numbers and body.language == "ko" else body.text
    parts = A.split_text(used, body.split)
    return {"text_used": used, "parts": parts, "count": len(parts)}


@app.get("/api/generations")
def generations():
    return store.list("generations")


@app.get("/api/generations/{gid}")
def generation(gid: str):
    return store.get("generations", gid) or _404()


@app.get("/api/generations/{gid}/audio")
def generation_audio(gid: str, part: int | None = None, which: str = "output"):
    g = store.get("generations", gid) or _404()
    d = T.GENS / gid
    if which == "ref":
        p = d / "ref" / "clip.wav"
    elif part is not None:
        p = d / g["parts"][part]["file"]
    else:
        p = d / "output.wav"
    return FileResponse(p, media_type="audio/wav", filename=f"{gid}.wav") if p.exists() else _404()


class NameBody(BaseModel):
    name: str


@app.patch("/api/generations/{gid}")
def generation_rename(gid: str, body: NameBody):
    g = store.get("generations", gid) or _404()
    g["name"] = body.name.strip()
    return store.put("generations", g)


@app.delete("/api/generations/{gid}")
def generation_delete(gid: str):
    store.delete("generations", gid)
    shutil.rmtree(T.GENS / gid, ignore_errors=True)
    return {"deleted": gid}


# ───────────────────────── ASR ─────────────────────────

class ASRBody(BaseModel):
    model: str
    upload_id: str
    language: str = "auto"
    params: dict = {}
    name: str = ""


@app.post("/api/asr")
def asr(body: ASRBody):
    if body.model not in MODELS or MODELS[body.model]["kind"] != "asr":
        _404("ASR 모델")
    return S.submit(S.Job("asr", f"ASR {MODELS[body.model]['label']}", body.model_dump()), T.asr_job).view()


@app.get("/api/transcripts")
def transcripts():
    return [{k: v for k, v in t.items() if k != "segments"} | {"segment_count": len(t.get("segments", []))}
            for t in store.list("transcripts")]


@app.get("/api/transcripts/{tid}")
def transcript(tid: str):
    return store.get("transcripts", tid) or _404()


class SegPatch(BaseModel):
    segments: list[dict] | None = None
    name: str | None = None


@app.patch("/api/transcripts/{tid}")
def transcript_patch(tid: str, body: SegPatch):
    t = store.get("transcripts", tid) or _404()
    if body.segments is not None:
        for s in body.segments:
            if not {"start", "end", "text"} <= set(s):
                raise HTTPException(400, "구간에는 start·end·text 가 있어야 한다")
        old = {(round(s["start"], 3), round(s["end"], 3)): s for s in t.get("segments", [])}
        for s in body.segments:
            prev = old.get((round(s["start"], 3), round(s["end"], 3)))
            if s.get("words") and (not prev or prev.get("text", "").strip() != s["text"].strip()):
                s.pop("words")   # 글을 고친 구간의 단어 시각은 더 이상 맞지 않는다
        t["segments"] = body.segments
        t["edited"] = True
    if body.name is not None:
        t["name"] = body.name.strip()
    return store.put("transcripts", t)


@app.get("/api/transcripts/{tid}/export")
def transcript_export(tid: str, fmt: str = "srt", max_chars: int = 0):
    t = store.get("transcripts", tid) or _404()
    meta = {k: t.get(k) for k in ("id", "name", "engine", "model", "params", "language", "upload")}
    try:
        body, mime = render(t["segments"], fmt, max_chars, meta)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    fname = f"{Path(t.get('name') or tid).stem}.{fmt}"
    from urllib.parse import quote
    return Response(body.encode("utf-8"), media_type=mime + "; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"})


@app.delete("/api/transcripts/{tid}")
def transcript_delete(tid: str):
    store.delete("transcripts", tid)
    return {"deleted": tid}


@app.on_event("startup")
def _warm():
    # 모델 확인을 미리 해 둔다 — 첫 카탈로그 요청이 NAS 를 다 훑느라 늦지 않게
    import threading
    threading.Thread(target=lambda: [M.check(k) for k in MODELS], daemon=True, name="warm-check").start()


@app.on_event("shutdown")
def _bye():
    S.shutdown_all()


# ───────────────────────── 정적 웹 ─────────────────────────
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = WEB_DIST / path
        if path and f.is_file() and WEB_DIST in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(WEB_DIST / "index.html")
