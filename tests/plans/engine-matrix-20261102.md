# Test Plan: engine-matrix

## Created
2026-11-02

## Goal
요구사항 3·5(「원하는 스크립트로 TTS」「ASR 모델에 따라 타임라인 결과」)와 추가 지시(「이 PC 에서 3090 만으로 잘 구동」「4080x2 에도 이식해 구동 확인」)를
엔진마다 실제 GPU 로 확인한다. 각 엔진이 (1) 자기 uv 환경에서 (2) NAS 의 모델을 싣고 (3) 같은 참조 세트·대본으로 음성을 만들고 (4) 기록이 남는지.

## Environment
- 1차: 이 PC(hikaTR, Windows 11) — RTX 3090 24 GB(허용) + RTX 4080(설정에서 제외). 모델 `S:\models`.
- 2차: 원격 4080x2(m42-server2) — RTX 4080 16 GB × 2. 모델 `N:\models`(SSH 세션, 같은 NAS 공유).
- 서버: `uv run voice-server --port 8770`(실측용, 데이터 `data/`) 또는 `npm run deploy`(8765).

## Preconditions
- 설정 `allowed_gpus` 를 웹 설정 API(`PUT /api/settings`)로 지정 — 1차는 3090 uuid 하나.
- 엔진 환경 설치 완료(`GET /api/envs` installed=true), 모델 확인 ok(`GET /api/catalog` check.ok).
- 참조 세트: 일본어 애니 음성(보컬 분리본 25.4 s, WanAvatar vn48 `ref/vocals.wav`) → 자동 모드(faster-whisper large-v3)로 만든 세트.

## Steps
1. `uv run python tests/integration/engine_matrix.py --base <서버> --ref <세트 id> --upload <업로드 id> --tts <모델들> --asr <모델들> --verify`
2. 대본(2문단, 숫자·약어 포함): 「이해되는 에이아이, 1편. 엘엘엠의 어텐션이란?」 / 「똑같이 밥이 들어가는데, 하나는 걱정이고 하나는 핀잔이죠.」 · 시드 2026 · 받아쓰기 검증 켬.
3. ASR 은 같은 업로드(25.4 s)를 모델마다 전사.
4. 카드 2장 모델(MOSS 8B)은 허용 카드가 1장이면 즉시 거절되는지, 2장(4080x2)이면 도는지.

## Expected Results
- TTS: 작업 done, 결과 기록에 env 판·장치(허용한 카드만)·문단별 검사가 있고 출력 길이 > 0. 불량이면 다시 뽑기 기록(attempts).
- ASR: 구간 ≥ 1, 언어 ja, 시각이 단조 증가.
- 3090 만 허용일 때 4080 에 우리 작업자가 뜨지 않는다(`device[].uuid`).

## Logs To Capture
결과 JSON(`tests/reports/engine-matrix/<시각>.json`), 실패 작업의 `log` 꼬리, 작업자 로그(`data/logs/worker-*.log`), nvidia-smi 사용량.

## Locator Contract
해당 없음(API 시험). 브라우저 시험은 `tests/plans/browser-e2e-20261102.md`.
