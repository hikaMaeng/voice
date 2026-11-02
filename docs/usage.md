# 설치 · 실행

필요: Node 20+, uv, Git. (Windows 에서 X-Voice 의 eSpeak 은 MSI 를 **풀기만** 한다 — 시스템 설치 없음.)

| 명령 | 하는 일 |
|---|---|
| `npm run deploy` | `uv sync --frozen` → `web` 의 `npm ci` → 웹 빌드 → 이전 서버(PID 파일) 트리째 종료·포트 해제 확인 → 새 서버 백그라운드 기동 → `/api/health` 확인 |
| `npm start` | 서버를 앞에서 실행(Ctrl+C 로 끝) — 웹이 이미 빌드돼 있어야 한다 |
| `npm run stop` · `npm run status` | 백그라운드 서버 종료 / 상태 |
| `npm run setup` · `npm run build` | 의존성만 / 웹 빌드만 |
| `npm run test:unit` · `npm run test:e2e` | pytest(모의 엔진) / Playwright(배포된 서버) |

환경 변수: `VOICE_PORT`(8765) · `VOICE_HOST`(127.0.0.1 — 다른 기계에서 열려면 0.0.0.0) · `VOICE_DATA_DIR`(./data) · `VOICE_ENVS_DIR`(./envs) ·
`VOICE_TEST_ENGINES=1`(모의 엔진 표시).

## 첫 사용

1. **설정** — 쓸 GPU 를 고른다(예: 이 PC 는 RTX 3090 만 체크). 모델 루트 확인.
2. **모델 관리** — 쓸 엔진의 「환경 설치」(엔진마다 수 GB, 한 번) → 모델 「받기」 또는 「위치 지정」(이미 받은 폴더).
3. **TTS** — 참고 음성 올리기 → 자동/직접 → 동의 근거 → 참조 세트 저장 → 대본·옵션 → 생성.
4. **ASR** — 파일 → 모델 → 실행 → 타임라인 확인·수정 → SRT 내려받기.

## 모델 위치

기본 모델 루트: Windows 에서 `S:\models` → 없으면 `N:\models` → 없으면 `data/models`. 같은 NAS 공유(`\\192.168.0.13\file-station\models`)가
데스크톱 세션에서는 S:, SSH 세션에서는 전역 SMB 로 붙인 N: 로 보인다. 폴더 규약 `<루트>\<owner>\<repo>`(HF 저장소 이름 그대로).
받기는 `snapshot_download(local_dir=…)` 로 평범한 폴더에 받는다(HF 캐시 구조 아님 — 옮기기·위치 지정이 쉽다).

## 다른 PC 로 이식

저장소를 받아 `npm run deploy` 하고, 엔진 환경은 그 PC 에서 웹으로 새로 설치한다(환경 폴더 복사 금지 — uv 실행기가 만든 기계의 Python 경로를 박아 둔다).
SSH 로 띄울 때는 `VOICE_HOST=0.0.0.0` 이면 LAN 에서 열 수 있다. 원격 4080x2 이식 기록은 `tests/reports/` 를 본다.
