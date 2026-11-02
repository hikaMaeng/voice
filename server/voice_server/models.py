"""모델 위치·확인·다운로드·지문.

위치: 설정 `model_paths[id]`(사용자가 지정한 「이미 받은 폴더」) → 없으면 `<model_root>/<owner>/<repo>`.
확인: 로드 전에 폴더와 필수 파일(`need` 패턴)을 서버가 직접 본다. HF 오프라인에서 없는 경로를 넘기면
transformers 가 그 경로를 저장소 이름으로 읽어 엉뚱한 오류(`Repo id must use alphanumeric chars`)로 죽기 때문이다.
다운로드: `snapshot_download(local_dir=…)` 로 평범한 폴더에(HF 캐시의 blob·심볼릭 링크 구조는 옮기기·위치 지정이 꼬인다).
지문: 작은 파일(설정·토크나이저)은 sha256, 큰 가중치는 이름·크기 — 결과 기록에 남겨 「같은 모델이었나」를 가린다.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import time
from pathlib import Path

from .catalog import MODELS
from .config import settings


def location(mid: str) -> Path:
    m = MODELS[mid]
    custom = (settings.get("model_paths") or {}).get(mid)
    if custom:
        return Path(custom)
    if m.get("builtin"):
        return Path("")
    owner, repo = m["repo"].split("/", 1)
    return Path(settings.get("model_root")) / owner / repo


def check(mid: str) -> dict:
    m = MODELS[mid]
    if m.get("builtin"):
        return {"ok": True, "path": "(내장)", "missing": [], "size_gb": 0}
    p = location(mid)
    res = {"ok": False, "path": str(p), "missing": [], "size_gb": 0.0, "custom": mid in (settings.get("model_paths") or {})}
    names, total = [], 0
    try:
        if not p.is_dir():
            res["error"] = "폴더가 없다"
            _check_cache[mid] = (time.time(), res)
            return res
        # os.scandir 는 목록과 함께 크기를 돌려준다(SMB 에서 파일마다 stat 하지 않는다)
        stack = [(p, "")]
        while stack:
            d, rel = stack.pop()
            with os.scandir(d) as it:
                for ent in it:
                    if ent.name == ".cache":
                        continue
                    r = rel + ent.name
                    if ent.is_dir(follow_symlinks=False):
                        stack.append((ent.path, r + "/"))
                    else:
                        names.append(r)
                        try:
                            total += ent.stat().st_size
                        except OSError:
                            pass
    except OSError as ex:   # 네트워크 드라이브가 잠깐 안 보일 때
        res["error"] = f"폴더를 읽을 수 없다: {ex}"
        return res
    for pat in m.get("need", []):
        if not any(fnmatch.fnmatch(n, pat) for n in names):
            res["missing"].append(pat)
    res["size_gb"] = round(total / 2**30, 2)
    res["ok"] = not res["missing"]
    if res["missing"]:
        res["error"] = "필수 파일 없음: " + ", ".join(res["missing"])
    _check_cache[mid] = (time.time(), res)
    return res


# 모델 확인 캐시: 모델 id → (잰 시각, 결과). 카탈로그 화면이 NAS 를 매번 훑지 않게(실측 13~31 s).
# 수명 CHECK_TTL 초. 받기·위치 지정이 끝나면 그 모델 것을 지운다(invalidate). 크기 상한 = 카탈로그 모델 수.
CHECK_TTL = 300
_check_cache: dict[str, tuple[float, dict]] = {}


def check_cached(mid: str) -> dict:
    hit = _check_cache.get(mid)
    if hit and time.time() - hit[0] < CHECK_TTL:
        return hit[1]
    return check(mid)


def invalidate(mid: str | None = None) -> None:
    if mid is None:
        _check_cache.clear()
    else:
        _check_cache.pop(mid, None)


def check_with_retry(mid: str, wait: float = 15.0) -> dict:
    """유휴로 풀린 네트워크 드라이브는 새 프로세스의 첫 접근에서 안 보인 일이 있다(1분 안 2건, 16 s 뒤 재시도는 7연속 성공) — 한 번 더 본다."""
    r = check(mid)
    if not r["ok"] and r.get("error", "").startswith(("폴더가 없다", "폴더를 읽을 수 없다")):
        time.sleep(wait)
        r = check(mid)
        r["retried"] = True
    return r


def revision(mid: str) -> str:
    """snapshot_download(local_dir) 가 남기는 `.cache/huggingface/download/*.metadata` 첫 줄 = 커밋 해시."""
    p = location(mid) / ".cache" / "huggingface" / "download"
    try:
        for f in p.rglob("*.metadata"):
            line = f.read_text(encoding="utf-8").splitlines()[0].strip()
            if len(line) == 40:
                return line
    except (OSError, IndexError):
        pass
    return ""


_fp_cache: dict[tuple[str, str], tuple[float, dict]] = {}   # (모델 id, 경로) → (폴더 mtime, 지문). 서버 수명 동안, 모델 수만큼만


def fingerprint(mid: str) -> dict:
    m = MODELS[mid]
    if m.get("builtin"):
        return {"id": mid, "builtin": True}
    p = location(mid)
    try:
        mt = p.stat().st_mtime
    except OSError:
        return {"id": mid, "path": str(p), "error": "없음"}
    hit = _fp_cache.get((mid, str(p)))
    if hit and hit[0] == mt:
        return hit[1]
    h = hashlib.sha256()
    files = []
    for f in sorted(x for x in p.rglob("*") if x.is_file() and ".cache" not in x.parts):
        rel = str(f.relative_to(p)).replace("\\", "/")
        size = f.stat().st_size
        if size < 4 * 2**20:
            h.update(rel.encode() + f.read_bytes())
        else:
            h.update(f"{rel}:{size}".encode())
        files.append(rel)
    fp = {"id": mid, "repo": m["repo"], "path": str(p), "revision": revision(mid), "sha": h.hexdigest()[:16], "files": len(files)}
    _fp_cache[(mid, str(p))] = (mt, fp)
    return fp


def download(mid: str, log, cancel=None) -> dict:
    from huggingface_hub import HfApi, snapshot_download
    m = MODELS[mid]
    dst = location(mid)
    dst.mkdir(parents=True, exist_ok=True)
    os.environ["HF_XET_CHUNK_CACHE_SIZE_BYTES"] = "0"   # xet 청크 캐시가 로컬 디스크에 쌓이지 않게
    os.environ.pop("HF_HUB_OFFLINE", None)
    endpoint = settings.get("hf_endpoint") or None
    total = 0
    try:
        info = HfApi(endpoint=endpoint).model_info(m["repo"], files_metadata=True)
        allow = m.get("allow")
        total = sum((s.size or 0) for s in info.siblings
                    if not allow or any(fnmatch.fnmatch(s.rfilename, a) for a in allow))
        log(f"{m['repo']} @ {info.sha[:10]} · {total / 2**30:.2f} GB → {dst}", total=total)
    except Exception as ex:
        log(f"목록 조회 실패(계속 받는다): {ex}")
    import threading
    done = threading.Event()

    def watch():
        while not done.wait(2.0):
            try:
                cur = sum(f.stat().st_size for f in dst.rglob("*") if f.is_file())
            except OSError:
                continue
            log(None, done_bytes=cur, total=total)
            if cancel is not None and cancel.is_set():
                return
    t = threading.Thread(target=watch, daemon=True)
    t.start()
    try:
        snapshot_download(repo_id=m["repo"], local_dir=str(dst), allow_patterns=m.get("allow"), endpoint=endpoint)
    finally:
        done.set()
    invalidate(mid)
    r = check(mid)
    if not r["ok"]:
        raise RuntimeError(f"받았지만 확인 실패: {r.get('error')}")
    _fp_cache.pop((mid, str(dst)), None)
    return r


def set_path(mid: str, path: str | None) -> dict:
    paths = dict(settings.get("model_paths") or {})
    if path:
        paths[mid] = path
    else:
        paths.pop(mid, None)
    settings.update({"model_paths": paths})
    invalidate(mid)
    return check(mid)


def summary(mid: str) -> dict:
    m = dict(MODELS[mid])
    m["check"] = check(mid)
    return json.loads(json.dumps(m, ensure_ascii=False, default=str))
