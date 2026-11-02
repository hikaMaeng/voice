"""단위·통합 시험 — GPU·가중치 없이(모의 엔진). 데이터는 임시 폴더."""
from __future__ import annotations

import io
import os
import tempfile
import time

os.environ.setdefault("VOICE_DATA_DIR", tempfile.mkdtemp(prefix="voice-test-"))
os.environ["VOICE_TEST_ENGINES"] = "1"

import numpy as np  # noqa: E402
import pytest  # noqa: E402
import soundfile as sf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from voice_server import audio as A  # noqa: E402
from voice_server.app import app  # noqa: E402
from voice_server.catalog import ENGINES, MODELS, resolve_params  # noqa: E402
from voice_server.subtitles import render  # noqa: E402
from voice_server.textnorm import read_numbers  # noqa: E402


def test_catalog_complete():
    tts = [k for k, e in ENGINES.items() if e["kind"] == "tts" and not e.get("test")]
    asr = [k for k, e in ENGINES.items() if e["kind"] == "asr" and not e.get("test")]
    assert set(tts) == {"qwen", "moss", "higgs", "omni", "chat", "cosy", "fish", "drama", "xvoice"}   # 10번째는 moss 8B 모델
    assert len([m for m in MODELS.values() if m["kind"] == "tts"]) >= 10
    assert len(asr) >= 5
    for m in MODELS.values():
        assert "license" in m and "commercial" in m
        for r in m["requires"]:
            assert MODELS[r]["kind"] == "aux"


def test_resolve_params_fills_defaults():
    p = resolve_params("qwen", {"temperature": "0.7"})
    assert p["temperature"] == 0.7 and p["top_k"] == 50 and p["seed"] == -1 and p["split"] == "paragraph"


def test_ko_numbers():
    assert read_numbers("3~4개의 4마디") == "서너 개의 네 마디"


def test_split_text():
    assert A.split_text("가\n나\n\n다", "paragraph") == ["가 나", "다"]
    assert A.split_text("가\n나", "line") == ["가", "나"]


def test_pick_window_prefers_sentence_bounds():
    segs = [{"start": 0.0, "end": 4.0, "text": "a"}, {"start": 4.3, "end": 9.0, "text": "b"},
            {"start": 9.4, "end": 14.0, "text": "c"}, {"start": 16.0, "end": 19.9, "text": "d"}]
    s0, s1, text = A.pick_window(segs, 20.0)
    assert 8 <= s1 - s0 <= 15 and text


def test_make_clip_tail_silence():
    sr = 16000
    y = np.ones(sr * 2, np.float32) * 0.5
    c = A.make_clip(y, sr, 0.0, 2.0)
    assert np.abs(c[-int(0.4 * sr):]).max() == 0.0


def test_srt_render():
    segs = [{"start": 0.0, "end": 1.5, "text": "안녕"}, {"start": 61.2, "end": 62.0, "text": "끝"}]
    body, _ = render(segs, "srt")
    assert "00:01:01,200 --> 00:01:02,000" in body
    vtt, _ = render(segs, "vtt")
    assert vtt.startswith("WEBVTT")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    from voice_server import scheduler
    scheduler.shutdown_all()


def _wait(c, jid, t=120):
    for _ in range(t * 5):
        v = c.get(f"/api/jobs/{jid}").json()
        if v["status"] in ("done", "error", "cancelled"):
            return v
        time.sleep(0.2)
    raise AssertionError("작업이 끝나지 않았다")


def test_mock_flow_reproducible(client):
    sr = 24000
    t = np.arange(sr * 12) / sr
    y = (0.3 * np.sin(2 * np.pi * 200 * t) * ((t % 4) < 3)).astype(np.float32)
    b = io.BytesIO()
    sf.write(b, y, sr, format="WAV")
    up = client.post("/api/uploads", files={"file": ("t.wav", b.getvalue(), "audio/wav")}).json()
    bad = client.post("/api/refs", json={"upload_id": up["id"], "mode": "auto", "asr_model": "mock-asr"}).json()
    assert _wait(client, bad["id"])["status"] == "error"   # 동의 없으면 거절
    j = client.post("/api/refs", json={"upload_id": up["id"], "mode": "auto", "asr_model": "mock-asr",
                                       "consent": {"basis": "self", "agreed": True}}).json()
    v = _wait(client, j["id"])
    assert v["status"] == "done", v
    rid = v["result"]["ref_id"]
    req = {"model": "mock-tts", "text": "하나 3개.\n\n둘.", "language": "ko", "ref_id": rid, "params": {"seed": 7, "retries": 0}}
    g1 = client.get(f"/api/generations/{_wait(client, client.post('/api/tts', json=req).json()['id'])['result']['generation_id']}").json()
    assert g1["seed"] == 7 and [p["seed"] for p in g1["parts"]] == [7, 8]
    assert g1["text_used"].startswith("하나 세 개") and g1["ref"]["text"] and g1["params"]["pitch_hz"] == 220.0
    # 참고 세트를 지워도 그때 사본으로 같은 결과가 나온다
    client.delete(f"/api/refs/{rid}")
    req2 = {**req, "ref_id": "", "ref_from_generation": g1["id"], "params": g1["params"]}
    g2 = client.get(f"/api/generations/{_wait(client, client.post('/api/tts', json=req2).json()['id'])['result']['generation_id']}").json()
    assert g2["output"]["sha256"] == g1["output"]["sha256"]
    a = _wait(client, client.post("/api/asr", json={"model": "mock-asr", "upload_id": up["id"]}).json()["id"])
    srt = client.get(f"/api/transcripts/{a['result']['transcript_id']}/export?fmt=srt").text
    assert "-->" in srt


def test_cancel_kills_worker(client):
    from voice_server import scheduler
    j = client.post("/api/workers/preload", json={"model": "mock-tts"}).json()
    _wait(client, j["id"])
    pids = [w["pid"] for w in scheduler.workers_view() if w["model"] == "mock-tts"]
    assert pids
    assert scheduler.stop_worker(pids[0]) is True
    import psutil
    assert not psutil.pid_exists(pids[0]) or psutil.Process(pids[0]).status() == psutil.STATUS_ZOMBIE
