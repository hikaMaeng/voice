"""이 기계의 자원(GPU·CPU·RAM)을 잰다 — 작업을 어느 카드에 넣을지는 scheduler 가 이 값과 설정으로 정한다.

GPU 는 NVML(nvidia-ml-py)로 읽는다. 번호는 NVML 순서(= PCI 버스 순서 = nvidia-smi 번호)이고,
작업자에는 `CUDA_VISIBLE_DEVICES=<uuid>` 로 넘겨 CUDA 기본 순서(빠른 카드 먼저)와 섞이지 않게 한다.
NVIDIA 가 없거나 드라이버가 없으면 GPU 목록은 비고 CPU 만 남는다(macOS 등).
"""
from __future__ import annotations

import os
import platform
import threading

import psutil

_nvml_ok: bool | None = None
_lock = threading.Lock()


def _nvml():
    global _nvml_ok
    with _lock:
        if _nvml_ok is None:
            try:
                import pynvml
                pynvml.nvmlInit()
                _nvml_ok = True
            except Exception:
                _nvml_ok = False
    if not _nvml_ok:
        return None
    import pynvml
    return pynvml


def gpus() -> list[dict]:
    nv = _nvml()
    if nv is None:
        return []
    out = []
    our = _our_pids()
    for i in range(nv.nvmlDeviceGetCount()):
        h = nv.nvmlDeviceGetHandleByIndex(i)
        mem = nv.nvmlDeviceGetMemoryInfo(h)
        try:
            temp = nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU)
        except Exception:
            temp = None
        try:
            util = nv.nvmlDeviceGetUtilizationRates(h).gpu
        except Exception:
            util = None
        procs, foreign = [], 0
        try:
            plist = list(nv.nvmlDeviceGetComputeRunningProcesses(h)) + list(nv.nvmlDeviceGetGraphicsRunningProcesses(h))
        except Exception:
            plist = []
        for p in plist:
            used = (p.usedGpuMemory or 0) if isinstance(p.usedGpuMemory, int) else 0
            mine = p.pid in our
            procs.append({"pid": p.pid, "used_mb": used // 2**20, "ours": mine})
            if not mine:
                foreign += used
        name = nv.nvmlDeviceGetName(h)
        uuid = nv.nvmlDeviceGetUUID(h)
        out.append({
            "index": i, "name": name.decode() if isinstance(name, bytes) else name,
            "uuid": uuid.decode() if isinstance(uuid, bytes) else uuid,
            "total_gb": round(mem.total / 2**30, 2), "used_gb": round(mem.used / 2**30, 2),
            "free_gb": round(mem.free / 2**30, 2), "temp_c": temp, "util": util,
            "foreign_gb": round(foreign / 2**30, 2), "procs": procs,
            # Windows WDDM 은 프로세스별 사용량을 주지 않는 일이 많다 — 그때는 「우리 것이 아닌 사용량」을 전체에서 추정
            "per_process_known": any(p["used_mb"] for p in procs),
        })
    return out


_registered: set[int] = set()   # 이 서버가 띄운 작업자 PID — workers 가 넣고 뺀다


def register_pid(pid: int, alive: bool) -> None:
    (_registered.add if alive else _registered.discard)(pid)


def _our_pids() -> set[int]:
    s = {os.getpid()} | set(_registered)
    for pid in list(_registered):
        try:
            s |= {c.pid for c in psutil.Process(pid).children(recursive=True)}
        except psutil.Error:
            pass
    return s


def system() -> dict:
    vm = psutil.virtual_memory()
    return {
        "os": f"{platform.system()} {platform.release()}", "machine": platform.machine(),
        "cpu": platform.processor() or platform.machine(), "cpu_count": psutil.cpu_count(logical=True),
        "cpu_physical": psutil.cpu_count(logical=False), "ram_gb": round(vm.total / 2**30, 1),
        "ram_free_gb": round(vm.available / 2**30, 1), "cpu_percent": psutil.cpu_percent(interval=None),
        "gpus": gpus(),
    }
