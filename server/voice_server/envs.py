"""엔진별 uv 환경 — 설치·상태·고정 버전.

엔진끼리 transformers·torch 요구 버전이 충돌한다(다른 버전에서는 조용히 망가진다 — Step-Audio 가 transformers 5.x 에서
EOS 를 못 내 8192 토큰까지 폭주한 전례). 그래서 엔진마다 `envs/<env>/` 에 따로 만든다.

설치 정의: `engines/envs/<env>/env.json`
  python        uv 가 받을 Python 버전
  torch_backend uv `--torch-backend` 값(cu128 등). NVIDIA 가 없는 기계에서는 cpu 로 바꾼다
  repos         [{url, commit, dir, recursive}] — engines/vendor/<env>/<dir> 에 받아 그 커밋으로 맞춘다
  assets        [{os, url, dest, kind: zip|msi, check}] — 실행 파일(speech.cpp)·DLL(eSpeak)
  steps         [{os?, pip: [...] | lock: 파일 | req: 파일, no_deps?, editable?: repo dir, pypi?: [이름]}] 차례대로
  check         설치 확인용 파이썬 한 줄
상태 파일: `envs/<env>/voice-env.json` (installed·freeze_sha·python·torch) — 설치가 끝날 때만 쓴다.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from .config import DATA, ENGINES_DIR, ENVS_DIR, VENDOR_DIR

MANIFESTS = ENGINES_DIR / "envs"


def manifest(env: str) -> dict:
    p = MANIFESTS / env / "env.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def env_dir(env: str) -> Path:
    return ENVS_DIR / env


def env_python(env: str) -> str | None:
    if env == "server":
        return sys.executable
    d = env_dir(env)
    p = d / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    return str(p) if p.exists() else None


def status(env: str) -> dict:
    if env == "server":
        return {"env": env, "installed": True, "python": sys.version.split()[0], "builtin": True}
    st = {"env": env, "installed": False, "has_manifest": bool(manifest(env))}
    f = env_dir(env) / "voice-env.json"
    if f.exists() and env_python(env):
        try:
            st.update(json.loads(f.read_text(encoding="utf-8")))
            st["installed"] = True
        except ValueError:
            pass
    return st


def _os_ok(rule: str | None) -> bool:
    if not rule:
        return True
    neg = rule.startswith("!")
    hit = sys.platform.startswith(rule.lstrip("!"))
    return hit != neg


def has_nvidia() -> bool:
    from .resources import gpus
    return bool(gpus())


def uv_bin() -> str:
    u = shutil.which("uv")
    if not u:
        raise RuntimeError("uv 가 PATH 에 없다 — https://docs.astral.sh/uv/ 로 설치한다")
    return u


def _strip_lock(src: Path, dst: Path, pypi: list[str] = ()) -> list[str]:
    """원격 노드에서 받은 freeze 를 설치용으로 다듬는다: 로컬 판 표기(+cu128)·편집 설치 줄은 뺀다.
    `pypi` 에 든 패키지는 따로 돌려준다 — torch 색인에는 Windows 휠이 없어 PyPI 일반 판을 받아야 하는 것(torchcodec)."""
    out, aside = [], []
    for line in src.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("-e ") or s.startswith("Using "):
            continue
        if "==" in s and "+" in s.split("==", 1)[1]:
            name, ver = s.split("==", 1)
            s = f"{name}=={ver.split('+', 1)[0]}"
        (aside if s.split("==")[0].strip().lower() in pypi else out).append(s)
    dst.write_text("\n".join(out) + "\n", encoding="utf-8")
    return aside


def install(env: str, log, cancel=None) -> dict:
    """환경 하나를 설치한다. log(str) 로 진행을 알린다. 실패하면 예외."""
    m = manifest(env)
    if not m:
        raise RuntimeError(f"설치 정의가 없다: engines/envs/{env}/env.json")
    uv = uv_bin()
    d = env_dir(env)
    d.parent.mkdir(parents=True, exist_ok=True)
    vend = VENDOR_DIR / env
    # uv 캐시와 환경 폴더가 다른 드라이브면 하드링크가 안 된다 — 처음부터 복사(경고 없이)
    renv = {**os.environ, "PYTHONUTF8": "1", "UV_NO_PROGRESS": "1", "VIRTUAL_ENV": str(d), "UV_LINK_MODE": "copy",
            "GIT_TERMINAL_PROMPT": "0"}
    backend = m.get("torch_backend", "auto")
    if backend.startswith("cu") and not has_nvidia():
        backend = "cpu"

    def run(cmd: list[str], cwd: Path | None = None) -> None:
        if cancel is not None and cancel.is_set():
            raise RuntimeError("취소됨")
        log("$ " + " ".join(cmd))
        p = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, env=renv, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        for raw in p.stdout:
            log(raw.decode("utf-8", "replace").rstrip())
            if cancel is not None and cancel.is_set():
                p.kill()
        if p.wait() != 0:
            raise RuntimeError(f"명령 실패(코드 {p.returncode}): {' '.join(cmd[:4])} …")

    py = env_python(env)
    if not py:
        run([uv, "venv", "--python", m.get("python", "3.12"), "--seed", str(d)])
        py = env_python(env)
    for r in m.get("repos", []):
        if not _os_ok(r.get("os")):
            continue
        rd = vend / r["dir"]
        if not (rd / ".git").exists():
            vend.mkdir(parents=True, exist_ok=True)
            run(["git", "clone"] + (["--recursive"] if r.get("recursive") else []) + [r["url"], str(rd)])
        if r.get("commit"):
            run(["git", "-C", str(rd), "fetch", "--quiet", "origin"])
            run(["git", "-C", str(rd), "checkout", "--quiet", r["commit"]])
            if r.get("recursive"):
                run(["git", "-C", str(rd), "submodule", "update", "--init", "--recursive"])
    for a in m.get("assets", []):
        if not _os_ok(a.get("os")):
            continue
        dest = vend / a["dest"]
        if (dest / a["check"]).exists():
            continue
        dest.mkdir(parents=True, exist_ok=True)
        # 받은 파일은 풀 폴더 밖에 둔다 — msiexec /a 는 대상 폴더 안의 MSI 를 풀다가 1603 으로 실패한다
        tmp = vend / (f"_dl_{dest.name}" + Path(a["url"]).suffix)
        log(f"받는 중 {a['url']}")
        urllib.request.urlretrieve(a["url"], tmp)
        if a["kind"] == "zip":
            with zipfile.ZipFile(tmp) as z:
                z.extractall(dest)
        elif a["kind"] == "msi":   # 설치하지 않고 풀기만 한다(관리자 권한·시스템 변경 없음)
            run(["msiexec.exe", "/a", str(tmp), "/qn", f"TARGETDIR={dest}"])
        tmp.unlink(missing_ok=True)
        if not (dest / a["check"]).exists():
            found = list(dest.rglob(Path(a["check"]).name))
            if not found:
                raise RuntimeError(f"자산을 풀었는데 {a['check']} 가 없다")
    for st in m.get("steps", []):
        if not _os_ok(st.get("os")):
            continue
        base = [uv, "pip", "install", "--python", py]
        if st.get("torch", True):
            base += ["--torch-backend", backend, "--index-strategy", "unsafe-best-match"]
        if st.get("no_deps"):
            base.append("--no-deps")
        if "lock" in st:
            src = MANIFESTS / env / st["lock"]
            dst = d / ("_" + st["lock"])
            aside = _strip_lock(src, dst, [x.lower() for x in st.get("pypi", [])])
            run(base + ["-r", str(dst)])
            if aside:
                run([uv, "pip", "install", "--python", py, "--no-deps"] + aside)
        elif "req" in st:
            run(base + ["-r", str(MANIFESTS / env / st["req"])])
        elif "editable" in st:
            run(base + ["-e", str(vend / st["editable"])])
        else:
            run(base + list(st["pip"]))
    if m.get("check"):
        run([py, "-c", m["check"]])
    fr = subprocess.run([uv, "pip", "freeze", "--python", py], capture_output=True, env=renv)
    freeze = fr.stdout.decode("utf-8", "replace")
    (d / "freeze.txt").write_text(freeze, encoding="utf-8")
    ver = subprocess.run([py, "-c", "import sys;print(sys.version.split()[0])"], capture_output=True, text=True).stdout.strip()
    torch_v = next((l.split("==", 1)[1] for l in freeze.splitlines() if l.lower().startswith("torch==")), "")
    info = {"env": env, "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"), "python": ver, "torch": torch_v,
            "torch_backend": backend, "freeze_sha": hashlib.sha256(freeze.encode()).hexdigest()[:16],
            "repos": {r["dir"]: r.get("commit", "") for r in m.get("repos", []) if _os_ok(r.get("os"))}}
    (d / "voice-env.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return info


def key_versions(env: str) -> dict:
    """재현 기록용 — 그 환경의 주요 패키지 판."""
    if env == "server":
        return {"python": sys.version.split()[0]}
    f = env_dir(env) / "freeze.txt"
    out = {}
    if f.exists():
        keep = ("torch", "torchaudio", "transformers", "accelerate", "numpy", "qwen-tts", "omnivoice", "chatterbox-tts",
                "faster-whisper", "ctranslate2", "qwen-asr", "funasr", "onnxruntime", "x-voice", "fish-speech")
        for line in f.read_text(encoding="utf-8").splitlines():
            n = line.split("==")[0].split(" @ ")[0].strip().lower()
            if n in keep:
                out[n] = line.split("==", 1)[1] if "==" in line else line.split(" @ ", 1)[-1]
    st = status(env)
    out["freeze_sha"] = st.get("freeze_sha", "")
    out["python"] = st.get("python", "")
    return out


DATA.mkdir(parents=True, exist_ok=True)
