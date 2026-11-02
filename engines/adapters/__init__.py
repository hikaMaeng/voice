"""엔진 어댑터 — 하나가 엔진 하나. `Adapter(ctx)` 에 load() 와 tts()/tts_batch() 또는 asr() 를 둔다.

엔진별 로딩·추론 코드는 WanAvatar 나레이션 스킬(tts_engine_worker.py · tts_worker.py, 2026-11-01~02 원격 4080x2 에서
10종 실행 확인)에서 옮겼다. import 하지 않고 복사한다.
"""
