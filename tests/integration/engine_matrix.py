"""엔진 실측 — 떠 있는 서버의 API 로 TTS·ASR 모델을 같은 조건으로 돌리고 결과를 JSON 으로 남긴다.

  uv run python tests/integration/engine_matrix.py --base http://127.0.0.1:8770 --ref <참조 세트 id> --upload <ASR 용 업로드 id>
      [--tts qwen3-tts-1.7b-base,… | -] [--asr fw-large-v3,… | -] [--out tests/reports/engine-matrix]   (- = 건너뜀, 생략 = 전부)

기록하는 것: 작업 상태·오류, 장치, 생성 기록의 timings·문단별 검사(match·lead_low_s·basic·attempts)·출력 길이,
ASR 은 구간 수·언어·첫 글·infer_s. 숫자는 서버가 남긴 기록에서 그대로 옮긴다(이 스크립트가 계산하지 않는다).
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

TEXT = ("이해되는 에이아이, 1편. 엘엘엠의 어텐션이란?\n\n"
        "똑같이 밥이 들어가는데, 하나는 걱정이고 하나는 핀잔이죠.")


def req(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=60) as f:
        return json.loads(f.read())


def wait(base, jid, limit=3600):
    t0 = time.time()
    while time.time() - t0 < limit:
        j = req(base, "GET", f"/api/jobs/{jid}")
        if j["status"] in ("done", "error", "cancelled"):
            return j
        time.sleep(3)
    return req(base, "POST", f"/api/jobs/{jid}/cancel")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    ap.add_argument("--ref", required=True)
    ap.add_argument("--upload", required=True)
    ap.add_argument("--tts", default="")
    ap.add_argument("--asr", default="")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--out", default="tests/reports/engine-matrix")
    a = ap.parse_args()
    cat = req(a.base, "GET", "/api/catalog")
    sysinfo = req(a.base, "GET", "/api/system")
    out = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "base": a.base, "ref": a.ref, "upload": a.upload, "seed": a.seed,
           "verify": a.verify, "text": TEXT, "settings": req(a.base, "GET", "/api/settings"),
           "gpus": [{k: g[k] for k in ("index", "name", "uuid", "allowed", "blocked")} for g in sysinfo["gpus"]],
           "service": sysinfo["service"], "tts": [], "asr": []}
    # "-" = 그 종류는 건너뛴다
    tts = [] if a.tts == "-" else [m for m in a.tts.split(",") if m] or [k for k, m in cat["models"].items() if m["kind"] == "tts" and not m.get("builtin")]
    asr = [] if a.asr == "-" else [m for m in a.asr.split(",") if m] or [k for k, m in cat["models"].items() if m["kind"] == "asr" and not m.get("builtin")]
    for mid in tts:
        t0 = time.time()
        j = req(a.base, "POST", "/api/tts", {"model": mid, "text": TEXT, "language": "ko", "ref_id": a.ref,
                                             "name": f"matrix {mid}", "params": {"seed": a.seed, "verify": a.verify}})
        j = wait(a.base, j["id"])
        row = {"model": mid, "status": j["status"], "error": j["error"][:600], "devices": j["devices"], "wall_s": round(time.time() - t0, 1),
               "log_tail": j.get("log", [])[-4:] if j["status"] != "done" else []}
        if j["status"] == "done":
            g = req(a.base, "GET", f"/api/generations/{j['result']['generation_id']}")
            row.update({"generation_id": g["id"], "result_status": g["status"], "duration": g["output"]["duration"],
                        "timings": g["timings"], "env": g["env"], "device": g["device"],
                        "parts": [{"i": p["i"], "dur": p.get("dur"), "attempts": p["attempts"], **p["checks"]} for p in g["parts"]]})
        if row["status"] != "done":
            row["log_tail"] = req(a.base, "GET", f"/api/jobs/{j['id']}").get("log", [])[-6:]
        out["tts"].append(row)
        print(json.dumps({k: row.get(k) for k in ("model", "status", "duration", "timings", "error")}, ensure_ascii=False), flush=True)
    for mid in asr:
        t0 = time.time()
        j = wait(a.base, req(a.base, "POST", "/api/asr", {"model": mid, "upload_id": a.upload, "name": f"matrix {mid}"})["id"])
        row = {"model": mid, "status": j["status"], "error": j["error"][:600], "devices": j["devices"], "wall_s": round(time.time() - t0, 1)}
        if j["status"] == "done":
            t = req(a.base, "GET", f"/api/transcripts/{j['result']['transcript_id']}")
            row.update({"transcript_id": t["id"], "language": t["language"], "segments": len(t["segments"]), "timings": t["timings"],
                        "words": sum(len(s.get("words") or []) for s in t["segments"]), "env": t["env"],
                        "first": [(s["start"], s["end"], s["text"]) for s in t["segments"][:3]]})
        else:
            row["log_tail"] = req(a.base, "GET", f"/api/jobs/{j['id']}").get("log", [])[-6:]
        out["asr"].append(row)
        print(json.dumps({k: row.get(k) for k in ("model", "status", "segments", "language", "timings", "error")}, ensure_ascii=False), flush=True)
    out["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    d = Path(a.out)
    d.mkdir(parents=True, exist_ok=True)
    p = d / (time.strftime("%Y%m%d_%H%M%S") + ".json")
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("→", p)


if __name__ == "__main__":
    main()
