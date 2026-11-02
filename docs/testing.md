# 시험

| 층 | 명령 | 무엇을 | 기록 |
|---|---|---|---|
| 단위·통합(모의 엔진) | `npm run test:unit` | 카탈로그 완결성 · 파라미터 채우기 · 숫자 읽기 · 참고 창 고르기 · 끝 무음 · SRT/VTT · 업로드→세트(동의 거절 포함)→TTS→**참고 세트 삭제 후 사본으로 같은 해시 재현**→ASR→SRT · 작업자 트리 종료 확인 | pytest 출력 |
| 엔진 실측(GPU) | `uv run python tests/integration/engine_matrix.py …` | TTS·ASR 모델마다 같은 참조·대본으로 실제 생성·전사, 결과 기록 | `tests/reports/engine-matrix/<시각>.json` + 같은 폴더의 보고서 |
| 브라우저(헤드리스) | `VOICE_E2E_BASE=http://192.168.0.29:8765 [VOICE_E2E_GPU=1] npm run test:e2e`(원격 4080x2 에 배포된 서버를 개발 PC 에서) | 화면 6개를 마크업 계약으로 조작 — 모의 엔진으로 업로드→참조 세트→생성→결과 불러오기→ASR→SRT, 설정의 GPU 체크 | `tests/reports/browser-e2e/<시각>.md` |

계획서: `tests/plans/*-YYYYMMDD.md`. 보고서: `tests/reports/<이름>/YYYYMMDD_HHMMSS.md`.

## 브라우저 시험 마크업 계약

선택자 우선순위: 역할+접근 이름(`getByRole('link', {name: 'TTS'})`) → 레이블(`getByLabel`) → `data-testid`(정본 [ui-contract.md](ui-contract.md)).
구조 의존 선택자 금지. 모의 엔진은 서버를 `VOICE_TEST_ENGINES=1` 로 띄우거나 설정 `show_test_engines` 를 켜서 보인다.

## 알려진 한계

- 받아쓰기 일치율은 거친 자다: 약어·숫자 표기 차이로 멀쩡한 문단을 불량으로 본 실측(「에이아이, 일편」↔「AI 1편」 0.61) 뒤 원문·숫자 풀기·로마자→한글 글자 이름 비교를 더했다(같은 예 0.974). 고유명사 오인식은 여전히 낮게 나온다.
- 비결정 엔진은 같은 시드여도 GPU 비결정성 때문에 비트 단위 재현을 보장하지 않는다. 재현 시험(해시 동일)은 결정적 엔진(모의·CosyVoice)으로 한다.
- Chatterbox 는 짧은 첫 문단에서 27.3 s 로 폭주했다(3090·4080 에서 같은 시드로 같은 길이 재현). 다시 뽑기 3회가 모두 실패하면 결과는 `warn` 이고 마지막 시도가 남는다.
- Whisper(transformers)의 일본어 구간은 굵다(25 s 에 3구간). 촘촘한 자막에는 faster-whisper·Qwen3-ASR·SenseVoice 를 쓴다.
- Nemotron 3.5 ASR 은 시각을 주지 않아 소리 크기로 나눈 구간 단위다. 자동 언어 감지는 한국어 첫 구간을 일본어로 오인했다 — 언어를 지정한다.

## 실행 기록

| 보고서 | 무엇 |
|---|---|
| `tests/reports/engine-matrix/20261102_141959.md` | 1차 — 개발 PC RTX 3090: TTS 11모델 · ASR 9모델, 실측 중 찾아 고친 결함 |
| `tests/reports/engine-matrix/20261102_154459.md` | 2차 — 원격 RTX 4080 x2 이식: TTS 11모델(MOSS 8B 카드 2장) · ASR 9모델 × 일·한 |
| `tests/reports/browser-e2e/20261102_155451.md` | 개발 PC 헤드리스 브라우저 → 원격 서버, 시험 4개 통과(실제 Qwen 생성 포함) |
