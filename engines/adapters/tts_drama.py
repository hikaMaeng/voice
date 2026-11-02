"""Fish Drama 3 GGUF — speech.cpp worker(JSON Lines, Vulkan). GPU 에 못 올린 전문가 층은 CPU 가 계산한다.

Vulkan 장치 번호는 CUDA·nvidia-smi 번호와 다르다(원격 4080x2 실측: Vulkan0 = GPU1). CUDA_VISIBLE_DEVICES 도 Vulkan 에는
안 먹는다. 그래서 「자동」은 서버가 정한 카드의 이름·메모리로 speech.exe 의 장치 목록과 맞추고, 못 맞추면 설정 값을 쓴다.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess

import numpy as np

from ._common import vendor


def _exe() -> str:
    base = vendor("drama", "speech")
    for root, _, files in os.walk(base):
        for f in files:
            if f in ("speech.exe", "speech"):
                return os.path.join(root, f)
    raise RuntimeError(f"speech.cpp 실행 파일이 없다: {base} — 환경을 설치한다")


class Adapter:
    def __init__(self, ctx):
        self.ctx = ctx
        self.wk = None
        self.voice_for = None

    def load(self):
        self.exe = _exe()
        m = self.ctx.model
        self.gguf = os.path.join(m["path"], m.get("file") or "Drama-35B-A3B-v3-Q4_K.gguf")
        if not os.path.exists(self.gguf):
            raise RuntimeError(f"GGUF 가 없다: {self.gguf}")

    def _vulkan_index(self, p) -> int:
        v = int(p.get("vulkan_index", -1))
        if v >= 0:
            return v
        want = os.environ.get("VOICE_GPU_NAME", "")
        try:
            out = subprocess.run([self.exe, "devices"], capture_output=True, text=True, encoding="utf-8", timeout=60).stdout
            for line in out.splitlines():
                if "Vulkan" in line and want and want.split()[-1] in line:
                    return int(line.split("Vulkan", 1)[1].split()[0].strip(":"))
        except Exception as ex:
            self.ctx.log(f"Vulkan 장치 목록 실패: {ex}")
        return int(os.environ.get("VOICE_VULKAN_INDEX", "0"))

    def _start(self, ref, p):
        if self.wk is not None and self.voice_for == (ref["audio"], ref["text"]):
            return
        if self.wk is not None:
            self.wk.kill()
        vf = ref["audio"] + ".drama-voice.gguf"   # 참고 음성마다 다르다 — 그 사본 옆에 둔다
        if not os.path.exists(vf):
            self.ctx.progress(stage="참고 목소리 인코딩")
            subprocess.run([self.exe, "voice", self.gguf, ref["audio"], "--transcript", ref["text"], vf], check=True)
        vk = self._vulkan_index(p)
        self.ctx.log(f"speech.cpp Vulkan{vk}")
        self.wk = subprocess.Popen([self.exe, "worker", self.gguf, "--add-voice", "ref=" + vf, "--device", f"Vulkan{vk}"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")
        ready = json.loads(self.wk.stdout.readline())
        if ready.get("type") != "ready":
            raise RuntimeError("speech.cpp worker: " + json.dumps(ready, ensure_ascii=False)[:600])
        self.sr = ready.get("model", {}).get("sample_rate", 44100)
        self.voice_for = (ref["audio"], ref["text"])
        self.n = 0

    def tts(self, text, ref, lang, p):
        self._start(ref, p)
        self.n += 1
        rid = f"r{self.n}"
        self.wk.stdin.write(json.dumps({"type": "synthesize", "id": rid, "text": text, "voice": "ref"}, ensure_ascii=False) + "\n")
        self.wk.stdin.flush()
        pcm = []
        while True:
            line = self.wk.stdout.readline()
            if not line:
                raise RuntimeError("speech.cpp worker 가 끝났다")
            msg = json.loads(line)
            if msg.get("id") != rid or msg["type"] == "progress":
                continue
            if msg["type"] == "chunk":
                pcm.append(np.frombuffer(base64.b64decode(msg["pcm"]), dtype="<i2"))
            elif msg["type"] == "end":
                break
            else:
                raise RuntimeError(json.dumps(msg, ensure_ascii=False)[:400])
        return np.concatenate(pcm).astype(np.float32) / 32768, self.sr
