"""작업 큐 · 카드별 락 · 상주 작업자.

- GPU 작업(tts·asr·ref)은 `acquire()` 로 작업자를 얻는다. 카드마다 락이 하나라 한 카드에서는 한 번에 한 작업만 돈다.
  「메모리가 비어 보인다」만으로 카드를 고르지 않는다 — 다른 프로그램이 막 올라오던 카드에 겹쳐 남의 렌더를
  `CUDA error: device not ready` 로 죽인 전례가 있다. 남이 쓰는 카드(foreign_vram_gb 초과)는 설정에 따라 피한다.
- 대기 순서는 작업 생성 시각(같은 작업이 검증 단계에서 다시 자원을 잡아도 원래 순번을 지킨다).
- 작업자는 모델을 실은 채 상주한다. 유휴 시간(idle_unload_min)·상주 수(max_resident)·자리 비우기로 내린다.
- 취소: 대기 중이면 빼고, 실행 중이면 그 작업자 프로세스 트리를 죽이고 죽었는지 확인해 기록한다.

상태 키·범위·수명: `_workers`(pid → Worker) 는 살아 있는 작업자만, 죽이면 바로 뺀다(상한 max_resident+실행 중).
`_gpu_lock`(uuid → 작업 id) 는 작업이 자원을 놓을 때 지운다. `JOBS`(작업 id → Job) 는 끝난 작업을 최근 300개까지만 둔다.
"""
from __future__ import annotations

import threading
import time
import traceback
from collections import deque

from . import models as M
from . import resources
from .catalog import ENGINES, MODELS
from .config import settings
from .db import new_id, store
from .workers import Cancelled, Worker, WorkerError

LOG_MAX = 400
KEEP_DONE = 300


class Job:
    def __init__(self, kind: str, title: str, params: dict, priority: float | None = None):
        self.id = new_id()
        self.kind, self.title, self.params = kind, title, params
        self.status = "queued"          # queued | waiting | loading | running | done | error | cancelled
        self.stage = "대기"
        self.progress = 0.0
        self.created = time.time()
        self.priority = priority or self.created
        self.started = self.finished = None
        self.result: dict | None = None
        self.error = ""
        self.devices: list = []
        self.log: deque = deque(maxlen=LOG_MAX)
        self.cancel = threading.Event()
        self.worker: Worker | None = None
        self.cancel_note = ""
        self.extra: dict = {}

    def say(self, line: str) -> None:
        self.log.append(time.strftime("%H:%M:%S ") + line)

    def set(self, stage: str | None = None, progress: float | None = None, status: str | None = None) -> None:
        if stage is not None:
            self.stage = stage
        if progress is not None:
            self.progress = max(0.0, min(1.0, progress))
        if status is not None:
            self.status = status

    def view(self, with_log: bool = False) -> dict:
        d = {"id": self.id, "kind": self.kind, "title": self.title, "status": self.status, "stage": self.stage,
             "progress": round(self.progress, 4), "created": self.created, "started": self.started,
             "finished": self.finished, "error": self.error, "devices": self.devices, "result": self.result,
             "cancel_note": self.cancel_note, **self.extra}
        if with_log:
            d["log"] = list(self.log)
        return d


JOBS: dict[str, Job] = {}
_jl = threading.Lock()
_cv = threading.Condition()
_waiting: list[Job] = []
_workers: dict[int, Worker] = {}
_gpu_lock: dict[str, str] = {}     # uuid(또는 "cpu") → 작업 id


def submit(job: Job, fn) -> Job:
    with _jl:
        JOBS[job.id] = job
        done = [j for j in JOBS.values() if j.finished]
        for j in sorted(done, key=lambda x: x.finished)[:-KEEP_DONE] if len(done) > KEEP_DONE else []:
            JOBS.pop(j.id, None)

    def run():
        job.started = time.time()
        job.set(status="running" if job.kind in ("env", "download") else "waiting")
        try:
            job.result = fn(job) or {}
            job.set(stage="완료", progress=1.0, status="done")
        except Cancelled:
            job.set(stage="취소됨", status="cancelled")
        except Exception as ex:   # 작업 하나의 실패가 서버를 죽이지 않는다
            if job.cancel.is_set():
                job.set(stage="취소됨", status="cancelled")
            else:
                job.error = str(ex)[:4000]
                job.say("오류: " + job.error.splitlines()[0][:500] if job.error else "오류")
                job.say(traceback.format_exc()[-3000:])
                job.set(stage="실패", status="error")
        finally:
            job.finished = time.time()
            _persist(job)
    threading.Thread(target=run, daemon=True, name=f"job-{job.id}").start()
    return job


def _persist(job: Job) -> None:
    try:
        store.put("jobs", {"id": job.id, "name": job.title, "created": job.created, **job.view(with_log=True)})
    except Exception:
        pass


def cancel(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job:
        raise KeyError(job_id)
    if job.finished:
        return job.view()
    job.cancel.set()
    with _cv:
        _cv.notify_all()
    w = job.worker
    if w is not None:   # 실행 중 — 생성 도중에는 멈출 길이 없으니 프로세스를 죽인다
        ok = w.kill()
        _drop(w)
        job.cancel_note = f"작업자 PID {w.pid} 트리 종료 " + ("확인" if ok else "실패 — 남은 프로세스 있음")
        job.say(job.cancel_note)
    job.set(stage="취소 중")
    return job.view()


def _drop(w: Worker) -> None:
    _workers.pop(w.pid, None)
    for u in w.gpu_uuids or ["cpu"]:
        if _gpu_lock.get(u) and w.busy:
            _gpu_lock.pop(u, None)
    w.busy = False


# ───────────────────────── 자원 고르기 ─────────────────────────

def _allowed(g: dict) -> bool:
    allowed = settings.get("allowed_gpus")
    return allowed is None or g["uuid"] in allowed


def _worker_vram(w: Worker, uuid: str) -> float:
    """작업자가 그 카드에서 쓰는 VRAM — 싣기 전후로 잰 실제 증가량, 없으면 카탈로그 추정.
    Windows(WDDM)는 프로세스별 사용량을 주지 않아, 추정만 쓰면 우리 작업자가 더 쓴 몫을 「다른 프로그램」으로 잘못 센다
    (실측: Drama 추정 15 GB 인데 카드를 거의 채워 「다른 프로그램 사용 3.0 GB」로 막혔다)."""
    if uuid in w.vram_actual:
        return w.vram_actual[uuid]
    return float(MODELS[w.model_key].get("vram_gb") or 0) / max(1, len(w.gpu_uuids))


def _our_vram(uuid: str) -> float:
    return sum(_worker_vram(w, uuid) for w in _workers.values() if uuid in w.gpu_uuids and w.alive())


def device_view() -> list[dict]:
    """설정 화면용 — 카드마다 허용 여부와 「지금 쓸 수 있나」의 이유."""
    out = []
    for g in resources.gpus():
        ours = _our_vram(g["uuid"])
        foreign = max(g["foreign_gb"], g["used_gb"] - ours - 0.6) if not g["per_process_known"] else g["foreign_gb"]
        why = []
        if not _allowed(g):
            why.append("설정에서 제외")
        if settings.get("gpu_mode") == "cpu":
            why.append("CPU 모드")
        if g["temp_c"] is not None and g["temp_c"] >= settings.get("temp_limit_c"):
            why.append(f"온도 {g['temp_c']}°C")
        if settings.get("avoid_foreign_gpu") and foreign > settings.get("foreign_vram_gb"):
            why.append(f"다른 프로그램 사용 {foreign:.1f} GB")
        if g["uuid"] in _gpu_lock:
            why.append("작업 중")
        out.append({**g, "allowed": _allowed(g), "ours_gb": round(ours, 2), "foreign_est_gb": round(foreign, 2),
                    "blocked": why})
    return out


def _pick(n: int, need_gb: float, job: Job) -> list[dict] | None:
    if settings.get("gpu_mode") == "cpu":
        return None
    reserve = float(settings.get("vram_reserve_gb"))
    cands = []
    for g in device_view():
        hard = [w for w in g["blocked"] if not w.startswith("작업 중")]
        if hard or g["uuid"] in _gpu_lock:
            continue
        reclaim = sum(_worker_vram(w, g["uuid"]) for w in _workers.values() if g["uuid"] in w.gpu_uuids and not w.busy)
        per = need_gb / n
        room = g["free_gb"] + reclaim - reserve
        # 카드보다 큰 모델(Fish 19.7 GB > 16 GB)은 카드가 거의 비었을 때만 넣는다 — 드라이버가 공유 메모리로 넘긴다
        oversize = per > g["total_gb"] - reserve and g["free_gb"] + reclaim >= g["total_gb"] * 0.9
        if room >= per or oversize:
            cands.append((g, reclaim))
    if len(cands) < n:
        return None
    cands.sort(key=lambda c: -(c[0]["free_gb"] + c[1]))   # 여유가 큰 카드부터
    return [c[0] for c in cands[:n]]


def acquire(job: Job, engine: str, model_id: str, extra_env: dict | None = None) -> Worker:
    """작업자 하나를 잡는다(필요하면 띄우고 모델을 싣는다). 반드시 release() 로 놓는다."""
    e, m = ENGINES[engine], MODELS[model_id]
    n = int(m.get("gpus", 1))
    need = float(m.get("vram_gb") or 0)
    gpu_allowed = need > 0 or not e.get("cpu_ok")   # VRAM 0 인 모의 엔진은 GPU 를 잡지 않는다
    if gpu_allowed and not e.get("cpu_ok"):
        usable = 0 if settings.get("gpu_mode") == "cpu" else len([g for g in resources.gpus() if _allowed(g)])
        if usable < n:   # 기다려도 안 된다 — 바로 알린다(설정에서 카드를 더 허용하거나 다른 모델)
            raise RuntimeError(f"「{m['label']}」은 GPU {n}장이 필요한데 설정에서 쓸 수 있는 카드는 {usable}장이다")
    with _cv:
        _waiting.append(job)
        _waiting.sort(key=lambda j: j.priority)
    try:
        job.set(stage="자원 대기", status="waiting")
        while True:
            if job.cancel.is_set():
                raise Cancelled()
            with _cv:
                first = _waiting and _waiting[0] is job
                if first:
                    w = _try_acquire(job, engine, model_id, n, need, gpu_allowed, e, extra_env)
                    if w is not None:
                        _waiting.remove(job)
                        _cv.notify_all()
                        break
                _cv.wait(timeout=1.5)
    except BaseException:
        with _cv:
            if job in _waiting:
                _waiting.remove(job)
            _cv.notify_all()
        raise
    job.worker = w
    job.devices = w.gpu_indices or ["cpu"]
    if not w.loaded:
        _load(job, w, model_id, engine, extra_env)
        w = job.worker   # 재시도로 새 작업자가 됐을 수 있다
    # 생성 중에 늘어난 메모리(캐시 할당자가 놓지 않는다)도 그 작업자 몫으로 더하려고 시작 시점 사용량을 적어 둔다
    w.used_at_start = {g["uuid"]: g["used_gb"] for g in resources.gpus() if g["uuid"] in w.gpu_uuids}
    job.set(status="running")
    return w


def _try_acquire(job, engine, model_id, n, need, gpu_allowed, e, extra_env) -> Worker | None:
    # 1) 이미 실은 작업자
    for w in list(_workers.values()):
        if not w.alive():
            _drop(w)
            continue
        if w.engine == engine and w.model_key == model_id and not w.busy:
            keys = w.gpu_uuids or ["cpu"]
            usable = all(k not in _gpu_lock for k in keys)
            if w.gpu_uuids and not all(_allowed({"uuid": u}) for u in w.gpu_uuids):
                w.shutdown()   # 설정에서 뺀 카드에 남은 작업자
                _drop(w)
                continue
            if usable:
                for k in keys:
                    _gpu_lock[k] = job.id
                w.busy = True
                return w
    # 2) 새로 띄울 카드
    devs = _pick(n, need, job) if gpu_allowed else None
    if devs is None:
        # CPU 로 돌릴 수 있는 엔진은 「쓸 GPU 가 아예 없을 때」만 CPU 로 — 카드가 잠깐 바쁜 것은 기다린다
        no_gpu = settings.get("gpu_mode") == "cpu" or not any(_allowed(g) for g in resources.gpus())
        if not gpu_allowed or e.get("cpu_ok") and settings.get("allow_cpu") and no_gpu:
            if "cpu" in _gpu_lock:
                return None
            devs = []
        else:
            job.set(stage="자원 대기 — " + _why_wait(n, need))
            return None
    uuids = [d["uuid"] for d in devs]
    for u in uuids:   # 자리 비우기 — 그 카드의 유휴 작업자 중 오래된 것부터
        for w in sorted([w for w in _workers.values() if u in w.gpu_uuids and not w.busy], key=lambda w: w.last_used):
            g = next((x for x in resources.gpus() if x["uuid"] == u), None)
            if g and g["free_gb"] - float(settings.get("vram_reserve_gb")) >= need / max(1, n):
                break
            job.say(f"자리 비우기: {w.engine}/{w.model_key} (PID {w.pid}) 내림")
            w.shutdown()
            _drop(w)
    while len([w for w in _workers.values() if not w.busy]) >= int(settings.get("max_resident")):
        old = min((w for w in _workers.values() if not w.busy), key=lambda w: w.last_used)
        job.say(f"상주 수 초과: {old.engine}/{old.model_key} 내림")
        old.shutdown()
        _drop(old)
    if devs:   # Vulkan 처럼 CUDA_VISIBLE_DEVICES 가 안 먹는 백엔드가 카드를 이름으로 맞출 수 있게
        extra_env = {**(extra_env or {}), "VOICE_GPU_NAME": devs[0]["name"], "VOICE_GPU_INDEX": str(devs[0]["index"])}
    try:
        w = Worker(engine, e["env"], e["adapter"], model_id, uuids, [d["index"] for d in devs], extra_env)
    except WorkerError as ex:
        raise RuntimeError(str(ex)) from ex
    _workers[w.pid] = w
    for k in uuids or ["cpu"]:
        _gpu_lock[k] = job.id
    w.busy = True
    job.say(f"작업자 시작 PID {w.pid} · {e['env']} · " + (", ".join(f"GPU{d['index']} {d['name']}" for d in devs) or "CPU"))
    return w


def _why_wait(n, need) -> str:
    gs = device_view()
    if not gs:
        return "GPU 없음(이 엔진은 CPU 로 못 돈다)"
    state = "; ".join(f"GPU{g['index']}: " + (", ".join(g["blocked"]) or f"여유 {g['free_gb']:.1f} GB") for g in gs)
    return f"카드 {n}장·{need:.1f} GB 필요 · {state}"


def model_payload(model_id: str) -> dict:
    m = MODELS[model_id]
    return {"id": model_id, "path": str(M.location(model_id)), "repo": m.get("repo"), "file": m.get("file"),
            "sub": m.get("sub"), "aux": {r: str(M.location(r)) for r in m.get("requires", [])}}


def _load(job: Job, w: Worker, model_id: str, engine: str, extra_env) -> None:
    for attempt in (1, 2):
        for mid in [model_id] + MODELS[model_id].get("requires", []):
            chk = M.check_with_retry(mid)
            if not chk["ok"]:
                raise RuntimeError(f"모델 「{MODELS[mid]['label']}」 확인 실패 — {chk.get('error')} ({chk['path']}). "
                                   "모델 관리에서 받거나 위치를 지정한다")
        job.set(stage=f"모델 싣는 중 — {MODELS[model_id]['label']}", status="loading")
        t0 = time.time()
        before = {g["uuid"]: g["used_gb"] for g in resources.gpus() if g["uuid"] in w.gpu_uuids}

        def prog(msg):
            job.set(stage="모델 싣는 중 — " + (msg.get("stage") or ""))
            if msg.get("log"):
                job.say(msg["log"])
        try:
            r = w.call("load", {"model": model_payload(model_id), "engine": engine}, on_progress=prog, cancel=job.cancel)
            w.loaded = True
            after = {g["uuid"]: g["used_gb"] for g in resources.gpus() if g["uuid"] in w.gpu_uuids}
            # 같은 카드에서 다른 작업자가 동시에 싣지 않는다(카드 락) — 증가량은 이 작업자 몫
            w.vram_actual = {u: round(max(0.0, after[u] - before.get(u, after[u])), 2) for u in after}
            if w.vram_actual:
                job.say("실제 VRAM 증가 " + ", ".join(f"{v:.1f} GB" for v in w.vram_actual.values()))
            job.say(f"모델 실음 {time.time() - t0:.1f}s · {r.get('device', '')}")
            return
        except Cancelled:
            raise
        except WorkerError as ex:
            job.say(f"싣기 실패({attempt}/2): {str(ex)[:600]}")
            if attempt == 2:
                w.kill()
                _drop(w)
                raise RuntimeError(f"모델을 싣지 못했다: {str(ex)[:1500]}") from ex
            # 한 번 다시 — 같은 카드에서 새 프로세스로
            w.kill()
            uuids, idx = w.gpu_uuids, w.gpu_indices
            _workers.pop(w.pid, None)
            time.sleep(5)
            nw = Worker(engine, ENGINES[engine]["env"], ENGINES[engine]["adapter"], model_id, uuids, idx, extra_env)
            nw.busy = True
            _workers[nw.pid] = nw
            job.worker = nw
            w = nw


def release(job: Job, w: Worker | None = None) -> None:
    w = w or job.worker
    if w is not None:
        if w.alive() and getattr(w, "used_at_start", None):
            now = {g["uuid"]: g["used_gb"] for g in resources.gpus() if g["uuid"] in w.used_at_start}
            for u, v in now.items():   # 카드 락으로 이 작업만 그 카드를 썼다 — 늘어난 몫은 이 작업자 것
                grow = v - w.used_at_start[u]
                if grow > 0.2:
                    w.vram_actual[u] = round(w.vram_actual.get(u, 0.0) + grow, 2)
            w.used_at_start = {}
        w.busy = False
        w.last_used = time.time()
        if not w.alive():
            _workers.pop(w.pid, None)
    for k, v in list(_gpu_lock.items()):
        if v == job.id:
            _gpu_lock.pop(k, None)
    job.worker = None
    with _cv:
        _cv.notify_all()


def workers_view() -> list[dict]:
    return [w.info() for w in _workers.values()]


def stop_worker(pid: int) -> bool:
    w = _workers.get(pid)
    if not w:
        raise KeyError(pid)
    if w.busy:
        raise RuntimeError("작업 중인 작업자다 — 그 작업을 취소한다")
    ok = w.shutdown()
    _drop(w)
    return ok


def shutdown_all() -> None:
    for w in list(_workers.values()):
        w.kill()
        _drop(w)


def _janitor() -> None:
    while True:
        time.sleep(30)
        limit = float(settings.get("idle_unload_min")) * 60
        for w in list(_workers.values()):
            if not w.alive():
                _drop(w)
            elif not w.busy and limit > 0 and time.time() - w.last_used > limit:
                w.shutdown()
                _drop(w)


threading.Thread(target=_janitor, daemon=True, name="janitor").start()
