"""엔진 작업자 — 엔진 환경의 python 으로 실행된다(서버 패키지를 import 하지 않는다).

  <env python> -u voice_worker.py --adapter tts_qwen

stdin 한 줄 = 요청 {"id", "op": load|tts|asr|ping|shutdown, ...}
프로토콜 출력은 원래 stdout(fd 1)의 복제본으로만 쓴다. fd 1 은 stderr 로 돌려서 라이브러리가 찍는 글이
프로토콜을 깨지 않게 한다(서버는 stderr 를 로그 파일에 쌓는다).
응답: {"id", "type": "progress", ...} 여러 번 → {"id", "type": "result", "data"} 또는 {"id", "type": "error", "message", "trace"}
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
import traceback

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
_proto = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
os.dup2(2, 1)
sys.stdout = sys.stderr
ENGINES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ENGINES)


def send(rid, kind, **kw):
    _proto.write(json.dumps({"id": rid, "type": kind, **kw}, ensure_ascii=False, default=str) + "\n")
    _proto.flush()


class Ctx:
    """어댑터가 받는 것: 모델 경로들, 장치, 진행 보고."""

    def __init__(self):
        self.model: dict = {}
        self.engine = ""
        self.rid = None
        self.device = "cpu"

    def progress(self, **kw):
        send(self.rid, "progress", **kw)

    def log(self, line: str):
        print(line, file=sys.stderr, flush=True)
        send(self.rid, "progress", log=line)


def set_seed(seed: int) -> None:
    import random
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed % (2**32))
    except ImportError:
        pass
    if "torch" in sys.modules:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)


def write_wav(path: str, wav, sr: int) -> float:
    import numpy as np
    import soundfile as sf
    w = np.asarray(wav, dtype=np.float32).squeeze()
    if w.ndim == 2:   # (채널, 표본) 이든 (표본, 채널) 이든 모노로
        w = w.mean(0 if w.shape[0] < w.shape[1] else 1)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    sf.write(path, w, int(sr))
    return len(w) / sr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    a = ap.parse_args()
    ctx = Ctx()
    mod = importlib.import_module("adapters." + a.adapter)
    adapter = None
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        req = json.loads(raw)
        rid, op = req.get("id"), req.get("op")
        ctx.rid = rid
        try:
            if op == "shutdown":
                send(rid, "result", data={"bye": True})
                break
            if op == "ping":
                send(rid, "result", data={"pong": True, "loaded": adapter is not None})
                continue
            if op == "load":
                t0 = time.time()
                ctx.model, ctx.engine = req["model"], req.get("engine", "")
                try:
                    import torch
                    ctx.device = "cuda:0" if torch.cuda.is_available() else "cpu"
                    dev_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
                except ImportError:
                    dev_name = os.environ.get("CUDA_VISIBLE_DEVICES") or "CPU"
                    ctx.device = "cuda:0" if os.environ.get("CUDA_VISIBLE_DEVICES") else "cpu"
                adapter = mod.Adapter(ctx)
                adapter.load()
                send(rid, "result", data={"load_s": round(time.time() - t0, 2), "device": dev_name})
                continue
            if adapter is None:
                raise RuntimeError("모델을 먼저 싣는다(load)")
            if op == "tts":
                items, ref, lang, params = req["items"], req["ref"], req["language"], req.get("params") or {}
                out = []
                if hasattr(adapter, "tts_batch") and len(items) > 1:
                    bs = max(1, int(params.get("batch_size", 1)))
                    # 길이가 비슷한 것끼리 묶는다 — 묶음은 가장 긴 문단이 끝날 때까지 돈다
                    order = sorted(range(len(items)), key=lambda k: -len(items[k]["text"]))
                    res = {}
                    for c in range(0, len(order), bs):
                        idx = order[c:c + bs]
                        seed = items[idx[0]]["seed"]
                        set_seed(seed)
                        t0 = time.time()
                        wavs, sr = adapter.tts_batch([items[k]["text"] for k in idx], ref, lang, params)
                        dt = (time.time() - t0) / len(idx)
                        for k, w in zip(idx, wavs):
                            dur = write_wav(items[k]["out"], w, sr)
                            res[k] = {"out": items[k]["out"], "sr": sr, "dur": round(dur, 3), "infer_s": round(dt, 2), "seed_used": seed}
                        ctx.progress(done=len(res), total=len(items), stage=f"{len(res)}/{len(items)}")
                    out = [res[k] for k in range(len(items))]
                else:
                    for k, it in enumerate(items):
                        set_seed(int(it["seed"]))
                        t0 = time.time()
                        w, sr = adapter.tts(it["text"], ref, lang, params)
                        dur = write_wav(it["out"], w, sr)
                        out.append({"out": it["out"], "sr": sr, "dur": round(dur, 3), "infer_s": round(time.time() - t0, 2),
                                    "seed_used": int(it["seed"])})
                        ctx.progress(done=k + 1, total=len(items), stage=f"{k + 1}/{len(items)}")
                send(rid, "result", data={"items": out})
                continue
            if op == "asr":
                r = adapter.asr(req["audio"], req.get("language"), req.get("params") or {})
                send(rid, "result", data=r)
                continue
            raise RuntimeError(f"모르는 요청: {op}")
        except Exception as ex:   # 요청 하나의 실패로 작업자를 죽이지 않는다(상주 모델 유지)
            send(rid, "error", message=f"{type(ex).__name__}: {ex}"[:3000], trace=traceback.format_exc()[-4000:])


if __name__ == "__main__":
    main()
