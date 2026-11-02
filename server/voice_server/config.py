"""경로와 웹에서 바꾸는 설정.

설정 저장소: `<data>/settings.json` 한 파일. 키는 `DEFAULTS` 의 키, 범위는 이 설치 하나,
수명은 사용자가 바꿀 때까지, 지우는 주체는 설정 화면(「기본값으로」)뿐이다.
장치 제한(어떤 GPU 를 쓸지)도 여기 있다 — 코드에 카드 번호를 박지 않는다.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # 저장소 루트
ENGINES_DIR = ROOT / "engines"
WEB_DIST = ROOT / "web" / "dist"
DATA = Path(os.environ.get("VOICE_DATA_DIR") or ROOT / "data").resolve()
ENVS_DIR = Path(os.environ.get("VOICE_ENVS_DIR") or ROOT / "envs").resolve()   # 엔진별 uv 환경
VENDOR_DIR = ENGINES_DIR / "vendor"                  # 엔진 코드 저장소·실행 파일(git clone · zip)


def _default_model_root() -> str:
    # 사용자 방침: 모델 가중치는 NAS(\\192.168.0.13\file-station\models\<owner>\<repo>).
    # 데스크톱 세션은 S:, SSH 세션은 같은 공유를 전역 SMB 로 붙인 N: 로 보인다(SSH 에서는 S: 가 안 보인다 — 2026-11-02 확인).
    # 둘 다 없는 기계는 data/models. 설정 화면에서 바꾼다.
    if sys.platform == "win32":
        for root in (r"S:\models", r"N:\models"):
            if Path(root).is_dir():
                return root
    return str(DATA / "models")


DEFAULTS: dict = {
    "model_root": _default_model_root(),
    "model_paths": {},            # 모델 id → 사용자가 지정한 폴더(「이미 받은 위치」)
    # 자원 — GPU 는 uuid 로 고른다(번호는 PCI 순서와 CUDA 기본 순서가 다르다)
    "gpu_mode": "auto",           # auto(허용된 카드 중 여유 있는 곳) | cpu
    "allowed_gpus": None,         # None = 감지된 전부, [] = 없음, [uuid, …]
    "vram_reserve_gb": 1.0,       # 카드마다 남겨 둘 메모리
    "avoid_foreign_gpu": True,    # 다른 프로그램이 쓰는 중인 카드는 피한다
    "foreign_vram_gb": 2.0,       # 이만큼 넘게 남이 쓰면 「사용 중」으로 본다
    "temp_limit_c": 87,           # 이 온도를 넘으면 그 카드에 새 작업을 넣지 않는다
    "allow_cpu": True,            # GPU 가 없을 때 CPU 로 돌려도 되는 엔진은 CPU 로
    "cpu_threads": 0,             # 0 = 자동
    "idle_unload_min": 20,        # 상주 모델을 이 시간 안 쓰면 내린다
    "max_resident": 3,            # 동시에 올려 둘 작업자 수
    "hf_endpoint": "",            # 비우면 huggingface.co
    "show_test_engines": bool(os.environ.get("VOICE_TEST_ENGINES")),
    "default_tts_model": "qwen3-tts-1.7b-base",
    "default_asr_model": "fw-large-v3",   # 참고 음성 자동 전사·받아쓰기 검증에 쓰는 ASR
}


class Settings:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._data = dict(DEFAULTS)
        if path.exists():
            try:
                self._data.update(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass

    def get(self, key: str):
        with self._lock:
            return self._data.get(key, DEFAULTS.get(key))

    def all(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def update(self, patch: dict) -> dict:
        unknown = [k for k in patch if k not in DEFAULTS]
        if unknown:
            raise KeyError(f"모르는 설정: {', '.join(unknown)}")
        with self._lock:
            self._data.update(patch)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
            return json.loads(json.dumps(self._data))

    def reset(self) -> dict:
        with self._lock:
            self._data = dict(DEFAULTS)
        return self.update({})


DATA.mkdir(parents=True, exist_ok=True)
settings = Settings(DATA / "settings.json")
