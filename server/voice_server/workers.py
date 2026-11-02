"""엔진 작업자 프로세스 — 엔진마다 자기 uv 환경의 python 으로 `engines/runtime/voice_worker.py` 를 띄운다.

규약(JSON Lines): 서버 → 작업자 stdin 한 줄에 요청 하나, 작업자 → 서버는 프로토콜 전용 파이프(stdout)로
`{"id", "type": "progress"|"result"|"error"|"log", ...}`. 라이브러리가 찍는 글은 작업자가 stderr 로 돌려
로그 파일(`<data>/logs/worker-<engine>-<pid>.log`)에 쌓인다.

수명: 모델을 실은 채 상주한다. scheduler 가 내리거나(유휴·자리 비우기) 취소하면 **프로세스 트리째** 죽이고
죽었는지 확인한다(자식이 남아 GPU 를 잡고 있던 전례). 정리는 PID 로만 한다.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from . import resources
from .config import DATA, ENGINES_DIR, ROOT
from .envs import env_python

LOGS = DATA / "logs"
LOGS.mkdir(parents=True, exist_ok=True)


class WorkerError(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


class Worker:
    def __init__(self, engine: str, env: str, adapter: str, model_key: str, gpu_uuids: list[str],
                 gpu_indices: list[int], extra_env: dict | None = None):
        self.engine, self.env, self.adapter, self.model_key = engine, env, adapter, model_key
        self.gpu_uuids, self.gpu_indices = gpu_uuids, gpu_indices
        self.busy = False
        self.loaded = False
        self.last_used = time.time()
        self.vram_actual: dict[str, float] = {}   # uuid → 싣기 전후 + 작업 전후로 잰 VRAM 증가(GB). 작업자 수명 동안
        self.used_at_start: dict[str, float] = {}
        self._seq = 0
        self._waiters: dict[str, queue.Queue] = {}
        self._wlock = threading.Lock()
        py = env_python(env)
        if not py or not Path(py).exists():
            raise WorkerError(f"엔진 환경 「{env}」이 설치되지 않았다 — 모델 관리 화면에서 환경을 설치한다")
        env_vars = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
                    "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
                    "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True", "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
                    "TOKENIZERS_PARALLELISM": "false", **(extra_env or {})}
        # 장치는 uuid 로 고정한다. 빈 문자열이면 CUDA 장치를 아예 안 보인다(CPU 작업)
        env_vars["CUDA_VISIBLE_DEVICES"] = ",".join(gpu_uuids)
        self.log_path = LOGS / f"worker-{engine}-{time.strftime('%Y%m%d-%H%M%S')}.log"
        self._log = open(self.log_path, "a", encoding="utf-8", errors="replace")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        self.proc = subprocess.Popen(
            [py, "-u", str(ENGINES_DIR / "runtime" / "voice_worker.py"), "--adapter", adapter],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._log, cwd=str(ROOT), env=env_vars,
            creationflags=flags, start_new_session=sys.platform != "win32")
        resources.register_pid(self.proc.pid, True)
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    @property
    def pid(self) -> int:
        return self.proc.pid

    def alive(self) -> bool:
        return self.proc.poll() is None

    def _read(self) -> None:
        for raw in self.proc.stdout:
            try:
                msg = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            q = self._waiters.get(msg.get("id"))
            if q:
                q.put(msg)
        for q in list(self._waiters.values()):   # 프로세스가 죽었다 — 기다리던 쪽을 깨운다
            q.put({"type": "error", "message": f"작업자가 종료됐다(코드 {self.proc.poll()}) — 로그 {self.log_path.name}"})

    def call(self, op: str, payload: dict, on_progress=None, cancel: threading.Event | None = None,
             timeout: float | None = None) -> dict:
        with self._wlock:
            self._seq += 1
            rid = f"r{self._seq}"
            q: queue.Queue = queue.Queue()
            self._waiters[rid] = q
            line = json.dumps({"id": rid, "op": op, **payload}, ensure_ascii=False) + "\n"
            try:
                self.proc.stdin.write(line.encode("utf-8"))
                self.proc.stdin.flush()
            except OSError as ex:
                self._waiters.pop(rid, None)
                raise WorkerError(f"작업자에 보낼 수 없다: {ex}") from ex
        t0 = time.time()
        try:
            while True:
                if cancel is not None and cancel.is_set():
                    raise Cancelled("취소됨")
                if timeout and time.time() - t0 > timeout:
                    raise WorkerError(f"{op} 시간 초과({timeout:.0f}s)")
                try:
                    msg = q.get(timeout=0.25)
                except queue.Empty:
                    if not self.alive() and q.empty():
                        raise WorkerError(f"작업자가 종료됐다(코드 {self.proc.poll()}) — 로그 {self.log_path.name}")
                    continue
                kind = msg.get("type")
                if kind == "progress":
                    if on_progress:
                        on_progress(msg)
                elif kind == "result":
                    return msg.get("data") or {}
                elif kind == "error":
                    raise WorkerError(msg.get("message", "작업자 오류") + (("\n" + msg["trace"]) if msg.get("trace") else ""))
        finally:
            self._waiters.pop(rid, None)
            self.last_used = time.time()

    def kill(self, wait: float = 10.0) -> bool:
        """프로세스 트리째 죽이고, 다 죽었는지 확인해 돌려준다."""
        try:
            root = psutil.Process(self.proc.pid)
            tree = root.children(recursive=True) + [root]
        except psutil.NoSuchProcess:
            tree = []
        for p in tree:
            try:
                p.kill()
            except psutil.Error:
                pass
        gone, alive = psutil.wait_procs(tree, timeout=wait)
        if alive and sys.platform == "win32":   # 마지막 수단 — PID 로만
            for p in alive:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
            gone, alive = psutil.wait_procs(alive, timeout=wait)
        resources.register_pid(self.proc.pid, False)
        try:
            self._log.close()
        except Exception:
            pass
        return not alive

    def shutdown(self) -> bool:
        if self.alive():
            try:
                self.proc.stdin.write(b'{"id":"bye","op":"shutdown"}\n')
                self.proc.stdin.flush()
                self.proc.wait(timeout=8)
            except Exception:
                pass
        return self.kill(wait=5)

    def info(self) -> dict:
        return {"engine": self.engine, "model": self.model_key, "pid": self.pid, "alive": self.alive(),
                "busy": self.busy, "loaded": self.loaded, "gpus": self.gpu_indices, "vram_gb": self.vram_actual,
                "idle_s": round(time.time() - self.last_used), "log": self.log_path.name}
