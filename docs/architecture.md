# 구조

```
브라우저(web/dist, React) ──HTTP──▶ voice-server(FastAPI, 저장소 .venv)
                                     ├ catalog   엔진·모델·파라미터 스키마
                                     ├ models    위치·확인·받기·지문
                                     ├ envs      엔진별 uv 환경 설치(envs/<env>)
                                     ├ scheduler 작업 큐 · 카드별 락 · 상주 작업자
                                     ├ tasks     참조 세트 · TTS · ASR · 설치 · 받기
                                     └ SQLite + data/ 파일
                                         │ stdin/stdout JSON Lines
                                         ▼
                 엔진 작업자 = <envs/<env>/python> engines/runtime/voice_worker.py --adapter <a>
                                     (CUDA_VISIBLE_DEVICES=<GPU uuid>, HF 오프라인)
```

## 왜 이렇게 나눴나

| 결정 | 근거 |
|---|---|
| 엔진마다 별도 uv 환경 + 작업자 프로세스 | 엔진끼리 transformers·torch 요구가 충돌한다(Qwen 4.57.3 · MOSS 5.0.0 · Higgs 5.22.1 · X-Voice 4.48.3 · Cosy torch 2.3.1). 다른 판에서는 조용히 망가진다(Step-Audio 가 transformers 5.x 에서 EOS 없이 8192 토큰 폭주 → 노드 OOM) |
| 서버는 오케스트레이션만 | 서버 환경에 torch 가 없다. 서버가 죽지 않고 엔진 하나의 실패가 다른 엔진에 번지지 않는다 |
| 작업자 상주 | NAS 로딩이 느리다(4.2 GB: 로컬 4~6 s ↔ NAS 119 s). 한 번 실은 모델은 유휴 한도까지 남긴다 |
| GPU 를 uuid 로 고정 | NVML 번호(PCI 순서)와 CUDA 기본 번호(빠른 카드 먼저)가 다르다. `CUDA_DEVICE_ORDER=PCI_BUS_ID` + `CUDA_VISIBLE_DEVICES=<uuid>` |
| 카드별 락 | 메모리만 보고 「비었다」고 넣었다가 다른 프로그램이 막 올리던 렌더와 겹쳐 그 렌더가 `CUDA error: device not ready` 로 죽은 전례 |
| 취소 = 프로세스 트리 종료 + 확인 | 반복문 자식이 안 멈춰 시험이 27분 더 돈 전례. PID 로만 죽인다(`pkill -f` 는 자기 셸을 죽인다) |
| 로드 전 경로 검사 + 1회 재시도 | HF 오프라인에서 없는 경로를 넘기면 `Repo id must use alphanumeric chars` 같은 엉뚱한 오류. 유휴로 풀린 네트워크 드라이브의 첫 접근 실패(16 s 뒤 재시도 7연속 성공) |

## 작업 흐름

- 모든 긴 일은 `Job`(scheduler.py). 상태 `queued → waiting(자원 대기) → loading → running → done|error|cancelled`.
- GPU 작업은 `acquire(job, engine, model)` 로 작업자를 잡고 `release()` 로 놓는다. 대기 순서는 작업 생성 시각(검증 단계에서 다시 잡아도 원래 순번).
- 카드 고르기: 설정의 허용 목록 → 온도 한도 → 남이 쓰는 메모리(`foreign_vram_gb`) → 락 → (여유 + 우리 유휴 작업자를 내리면 생길 여유 − 예비) ≥ 필요 VRAM.
  카드보다 큰 모델(Fish 19.7 GB)은 카드가 거의 비었을 때만 넣는다(드라이버가 공유 메모리로 넘김).
- CPU: `cpu_ok` 엔진(faster-whisper·Whisper·SenseVoice·모의)만, 쓸 GPU 가 없을 때(또는 CPU 모드).
- 카드 2장 모델(MOSS 8B)은 두 카드의 락을 함께 잡는다.

## 저장

`data/`(VOICE_DATA_DIR): `voice.db`(refs·generations·transcripts·uploads·jobs, 본문은 JSON) · `uploads/<id>/` · `refs/<id>/clip.wav` ·
`generations/<id>/{output.wav, parts/, ref/clip.wav, ref/text.txt}` · `logs/` · `settings.json`.
엔진 환경 `envs/<env>/`(VOICE_ENVS_DIR) · 엔진 코드 저장소·실행 파일 `engines/vendor/<env>/`.
