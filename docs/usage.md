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

## 운영 방식(2026-11-02 사용자 지시)

| 역할 | 기계 | 방법 |
|---|---|---|
| 코드 수정·관리 | 개발 PC(`F:\dev\voice`) | 커밋 → `git push origin main`(https://github.com/hikaMaeng/voice) |
| 서버 실행·실제 시험(GPU) | 원격 4080x2(`D:\voice`) | `git pull` → `npm run deploy`(아래) |
| 시험 브라우저 | 개발 PC | Chrome·Playwright 로 `http://192.168.0.29:8765` |

개발 PC 에서는 서버를 띄우지 않는다. 원격 배포(PowerShell, uv 가 PATH 밖에 있다):

```powershell
$env:PATH='D:\wanrender\bin;'+$env:PATH; $env:VOICE_HOST='0.0.0.0'; cd D:\voice; git pull; npm run deploy
```

SSH 로 배포하면 서버가 세션과 함께 죽지 않게 `scripts/voice.mjs` 가 WMI(`Win32_Process.Create`)로 세션 밖에서 띄운다.
원격은 SSH 세션에서 S: 가 안 보여 모델 루트가 `N:\models`(같은 NAS 공유)로 잡힌다.

## 다른 PC 로 이식

저장소를 받아 `npm run deploy` 하고, 엔진 환경은 그 PC 에서 웹으로 새로 설치한다(환경 폴더 복사 금지 — uv 실행기가 만든 기계의 Python 경로를 박아 둔다).
SSH 로 띄울 때는 `VOICE_HOST=0.0.0.0` 이면 LAN 에서 열 수 있다. 원격 4080x2 이식 기록은 `tests/reports/` 를 본다.

## 명령줄 · 에이전트에서 쓰기

전역 스킬 `voice-service`(`C:\Users\hika0\.claude\skills\voice-service`, 개발 PC)가 이 서비스의 HTTP 클라이언트다 — 표준 라이브러리만 쓰는 `scripts/voice_client.py`.

```bash
python voice_client.py status
python voice_client.py tts --ref <세트 id> --text-file script.txt --out out.wav [--model …] [--seed 7] [--verify]
python voice_client.py asr --audio talk.mp4 --out talk.srt [--model fw-large-v3] [--lang ko]
python voice_client.py replay <결과 id> --out again.wav
```
주소는 `--url` > env `VOICE_URL` > `http://192.168.0.29:8765`. 목소리 사용 근거(`--consent`) 없이는 참조 세트를 만들지 않는다.
2026-11-02 확인: 스킬로 Qwen 생성(2문단 일치율 1.0) → 스킬 ASR 로 SRT 4구간 → `replay` 결과 wav 가 원본과 sha256 동일(같은 카드).
