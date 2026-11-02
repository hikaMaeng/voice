# 웹 화면 계약 (Playwright 용)

웹은 `web/`(Vite + React 19 + TypeScript, 외부 UI 라이브러리 없음). `npm run build` → `web/dist` → 서버가 `/` 에서 서빙한다
(`app.py` 끝: `/assets` 마운트 + `index.html` 폴백 — **서버 시작 때 `web/dist` 가 있어야 마운트된다**).
개발: `cd web && npm run dev`(5173, `/api` → `http://127.0.0.1:8765` 프록시).

| 파일 | 맡는 것 |
|---|---|
| `web/src/api.ts` | API 타입·`fetch` 래퍼(오류 `detail` → `ApiError.message`) |
| `web/src/state.tsx` | 카탈로그·작업 목록 전역 상태(실행 중 작업 있으면 1초, 없으면 3초 폴링), `useJob`(1초), 결과 「불러오기」 전달 |
| `web/src/components/ui.tsx` | `JobPanel`·`ParamFields`(카탈로그 스키마 → 입력)·`UploadPicker`·`ModelSelect`·`ConfirmButton`·배지 |
| `web/src/pages/*.tsx` | 화면 6개 |

## 선택자 원칙

1. 역할·접근 이름이 먼저: `getByRole('button', {name: '생성'})`, `getByLabel('대본')`. 같은 이름 버튼이 여러 행에 있으면 **행 컨테이너(test id)로 먼저 좁힌다**.
2. `data-testid` 는 컨테이너·반복 항목·문구가 바뀌기 쉬운 상태 표시에만 단다. 반복 항목은 `data-*-id` 로 식별한다.
3. 되돌릴 수 없는 동작(삭제·기본값으로)은 브라우저 `confirm()` 을 쓰지 않는다 — 버튼을 누르면 같은 자리에 `「… 확인」`·`그만두기` 버튼이 나타난다(`role=group`, 이름 `「<버튼> 확인」`).
4. 오류는 `role=alert`(서버 `detail` 그대로), 진행·완료 안내는 `role=status`.
5. 작업 패널은 끝난 상태를 **양의 신호**로 준다: 패널의 `data-status` 가 `done|error|cancelled` 가 된다.

## 공통

| 계약 | 뜻 |
|---|---|
| 해시 라우팅 | `#/models` `#/tts` `#/results` `#/results/<id>`(상세 열림) `#/asr` `#/jobs` `#/settings`. 해시 없으면 `#/tts` |
| `nav[aria-label=주 메뉴]` · `main-nav` · `nav-<route>` | 탭 링크. 현재 탭은 `aria-current="page"` |
| `main` · `page-<route>` | 화면마다 `main` 하나, 제목 `h1#page-title` |
| `active-job-count` | `role=status`, `data-count`=실행 중 작업 수 |
| `catalog-error` | 카탈로그 불러오기 실패 |
| `catalog-pending` | 카탈로그를 기다리는 중(`aria-busy`). 모델 관리·TTS·ASR 은 카탈로그가 와야 그려지고, 결과물·작업·설정은 먼저 그려진다 |
| `error-alert` | 기본 오류(따로 이름 없는 `role=alert`) |
| `commercial-badge` | 안쪽 `[data-commercial]` = `yes`(상업 가능) · `no`(상업 불가) · `limited`(조건부) · `unknown`(확인 필요) |
| `param-<key>` | 동적 파라미터 입력(카탈로그 `common`+`params` 의 `key`). 레이블 = 스키마 `label`. `group=advanced` 는 `<prefix>-params-advanced`(`details`) 안 |

### 작업 패널 (`JobPanel`)

컨테이너 test id 는 화면별(아래 표). 속성: `data-job-id`, `data-status`(queued·waiting·loading·running·done·error·cancelled), `aria-busy`.
안쪽: `job-status`(안쪽 `[data-status]`), `job-stage`(`role=status`), `job-progress`(`progress`, 이름 `진행률 <제목>`), `job-bytes`(받기),
`job-error`(`role=alert`), `job-cancel-note`, 버튼 `작업 취소`, `job-log`(로그 `pre`, `details` 안).

| 화면 | 작업 패널 test id |
|---|---|
| 모델 받기 | `model-download-job`(해당 `model-subrow` 안) |
| 환경 설치 | `env-install-job`(해당 `env-status` 안, 로그 펼침) |
| 참조 세트 | `ref-job` |
| TTS 생성 | `tts-job` |
| ASR | `asr-job` |
| 작업 상세 | `job-detail-panel` |

## 모델 관리 `#/models`

| test id / 이름 | 뜻 |
|---|---|
| 라디오 `전체`·`TTS`·`ASR` | 종류 거르기 |
| 버튼 `상태 새로 고침` · `catalog-loading` | 카탈로그 다시 읽기(모델 폴더 확인이 NAS 에서 10초 이상 걸릴 수 있다) |
| `engine-section[data-engine]` | 엔진 하나(`h2`=엔진 이름) |
| `engine-use` · `engine-caveat` | 쓸 곳 · 주의 |
| `env-status[data-env][data-installed]` | 환경 상태. 버튼 `환경 설치`/`환경 다시 설치`(설치 정의 없으면 비활성) |
| `models-table` | 표(이름 `<엔진> 모델`) |
| `model-row[data-model-id][data-kind]` | 모델 한 행(`kind`=tts·asr·aux). 행 안 버튼 `받기`·`위치 지정` |
| `model-status[data-state]` | `ok`·`missing`·`error`·`builtin` |
| `model-measured` · `model-location` | 실측 · 위치 |
| `model-subrow[data-model-id]` | 받기 진행·위치 지정 폼이 들어가는 아래 행 |
| `model-path-form` · `model-path-input` · `model-path-result` | 레이블 `이미 받은 모델 폴더 경로`, 버튼 `위치 저장`·`기본 위치로`(빈 값 PUT)·`닫기` |
| `models-error` | 받기·설치 요청 오류 |

## TTS `#/tts`

참조 세트 만들기 (`ref-create`)

| test id / 이름 | 뜻 |
|---|---|
| `ref-upload` · `ref-upload-file` · `ref-upload-select` · `ref-upload-status` · `ref-upload-audio` | 레이블 `음성 파일 올리기`(고르면 바로 업로드) · `올린 음성 고르기` |
| `ref-name` | `세트 이름` |
| `ref-mode` | 라디오 `자동 (ASR 로 언어·전사문)` · `직접 (언어 선택 + 전사문 입력)` |
| `ref-asr-model` · `ref-language` · `ref-start` · `ref-end` · `ref-text` | `자동 전사 ASR 모델`(자동일 때) · 참고 언어 · `시작 (초, 선택)` · `끝 (초, 선택)` · `참고 전사문`(직접일 때) |
| `ref-consent` · `ref-consent-basis` · `ref-consent-agree` · `ref-consent-note` | `동의 근거`(self·other_consent·licensed·synthetic) · 확인 체크 · 메모 |
| `ref-create-blockers` | 만들기를 막는 이유 목록(`role=status`). 하나라도 있으면 버튼 `참조 세트 만들기` 비활성 |
| `ref-create-error` · `ref-create-done` | 요청 오류 · 완료 안내(자동 전사문 표시) |

저장된 참조 세트 (`ref-list-section`)

| test id / 이름 | 뜻 |
|---|---|
| `ref-list` · `ref-list-empty` | 목록 · 빈 상태 |
| `ref-item[data-ref-id][data-selected]` | 세트 하나(`h3`=이름). `data-selected=true` 면 생성 폼에 선택됨 |
| `ref-language-value` · `ref-text-value` · `ref-clip-audio` · `ref-source-audio` | 언어 · 전사문 · 잘린 클립(`src` 에 `rev`) · 원본 |
| `ref-edit-form` · `ref-edit-name` · `ref-edit-language` · `ref-edit-text` | `전사문·이름 고치기 / 구간 다시 자르기`(`details`) 안. 버튼 `세트 저장`(바뀐 게 있을 때만) |
| `ref-recut-form` · `ref-recut-start` · `ref-recut-end` | 버튼 `구간 다시 자르기` |
| 버튼 `이 세트로 생성` · `세트 삭제` → `세트 삭제 확인` | |

생성 (`tts-form-section`)

| test id / 이름 | 뜻 |
|---|---|
| `tts-loaded-banner[data-gen-id][data-ref-mode]` | 불러오기 안내. `ref-mode` = `set`(저장 세트 그대로) · `copy`(결과의 참고 사본, `ref_from_generation`) |
| `tts-loaded-ref` | 참고를 어떻게 쓰는지 문장 |
| `tts-form` · `tts-model` · `tts-language` · `tts-ref` · `tts-text` · `tts-name` · `tts-ref-text` | 레이블 `TTS 모델` · `대본 언어` · `참조 세트`(값 `ref:<id>` 또는 `gen:<결과 id>`) · `대본` · `결과 이름 (선택)` · `참고 전사문 덮어쓰기` |
| `tts-model-info` · `tts-noncommercial-warning` · `tts-model-not-ready` · `tts-env-not-installed` | 모델 라이선스 · 비상업/조건부/확인 필요 경고 · 모델 미준비 · 환경 미설치 |
| `tts-ref-preview` | 고른 참고의 전사문 |
| `tts-params` · `tts-params-advanced` · `param-<key>` | 동적 파라미터 |
| `tts-blockers` · 버튼 `생성` · `tts-error` | |
| `tts-result[data-gen-id][data-status]` · `tts-result-audio` | 완료 결과(링크 `내려받기`·`결과물에서 자세히 보기`) |

불러오기 규칙: 모델·언어·대본(`text` 원문)·`params` 전부(시드는 기록된 실제 값). 참고는 `ref.id` 가 목록에 있고 `clip_sha256` **과 언어가** 같으면 그 세트(전사문만 바뀌었으면 기록된 전사문을 `ref_text` 로 덮어씀), 아니면 `ref_from_generation`.

## 결과물 `#/results`

| test id / 이름 | 뜻 |
|---|---|
| `gen-table` · `gen-row[data-gen-id]` · `gen-list-empty` | 목록. 행 안 `gen-status`(안쪽 `[data-status]`=ok·warn), 버튼 `상세`, 링크 `내려받기` |
| `gen-detail[data-gen-id]` | 상세(`#/results/<id>`) |
| `gen-detail-audio` · 버튼 `불러오기` · `결과 삭제` → `결과 삭제 확인` | |
| `gen-rename-form` · `gen-rename-input` | 레이블 `결과 이름`, 버튼 `이름 저장` |
| `gen-seed` · `gen-text` · `gen-ref-audio` · `gen-ref-text` | 시드 · 대본 · 그때 쓴 참고 사본 |
| `gen-parts-table` · `gen-part-row[data-part][data-failed]` | 문단별 basic·lead_low_s·match·attempts·문단 재생 |
| `gen-params` · `gen-model-fingerprint` · `gen-env` | 파라미터 · 모델 지문 · 환경 판(키-값 표) |

## ASR `#/asr`

| test id / 이름 | 뜻 |
|---|---|
| `asr-upload*` | 업로드/선택(`ref-upload*` 와 같은 구조) |
| `asr-model` · `asr-language` · `asr-name` · `asr-params` | 레이블 `ASR 모델` · `언어`(auto 포함) · `전사 이름 (선택)` |
| `asr-blockers` · 버튼 `전사 실행` · `asr-error` | |
| `transcript-table` · `transcript-row[data-transcript-id]` · `transcript-list-empty` | 저장된 전사. 행 안 버튼 `열기`·`전사 삭제` |
| `asr-viewer[data-transcript-id]` | 결과 보기 |
| `asr-audio` · `asr-current-time[data-active-index]` | 원본 재생 · 재생 위치와 현재 구간 번호(0부터, 없으면 -1) |
| `asr-timeline` · `asr-timeline-seg[data-index][data-active]` | 가로 막대 시각화(`aria-hidden`, 마우스 전용 — 같은 동작을 구간 버튼이 준다) |
| `asr-segments` · `asr-segment[data-index][data-active]` | 구간 목록. 현재 구간은 `aria-current="true"`. 버튼 이름 `구간 N 재생 m:ss.ss부터`, 글 레이블 `구간 N 글`(`asr-segment-text`) |
| 버튼 `구간 수정 저장` · `asr-save-status` | 고친 구간은 `words` 를 버리고 PATCH |
| `asr-export` · `asr-max-chars` · `asr-export-srt|vtt|txt|json` | 링크 `SRT 내려받기` 등(`export?fmt=&max_chars=`) |

## 작업 `#/jobs`

| test id / 이름 | 뜻 |
|---|---|
| `jobs-table` · `job-row[data-job-id][data-kind][data-status]` · `jobs-empty` | 행 안 버튼 `로그`·`취소`(진행 중일 때) |
| `job-detail` · `job-detail-panel` · `job-result` | 상세(로그 펼침) · 결과 값 |
| `workers-table` · `worker-row[data-pid]` · `workers-empty` | 상주 작업자. 행 안 버튼 `내리기`(작업 중이면 비활성) |

## 설정 `#/settings`

| test id / 이름 | 뜻 |
|---|---|
| `settings-form` | 버튼 `설정 저장`(바뀐 게 있을 때만) · `고친 것 되돌리기` · `기본값으로` → `모든 설정을 기본값으로` |
| `settings-all-gpus` | 체크 `감지된 GPU 전부 사용`(켜면 `allowed_gpus=null`) |
| `gpu-table` · `gpu-row[data-gpu-uuid][data-gpu-index]` · `gpu-allow` · `gpu-blocked` | 카드별 체크(이름 `GPU<n> <카드 이름> 사용`, 「전부」가 켜져 있으면 비활성) · 못 쓰는 이유 배지 |
| `settings-no-gpu` | GPU 없음 |
| `settings-gpu-mode` · `settings-vram-reserve` · `settings-foreign-vram` · `settings-temp-limit` · `settings-avoid-foreign` · `settings-allow-cpu` | 자원 |
| `settings-model-root` · `settings-hf-endpoint` · `settings-idle-unload` · `settings-max-resident` · `settings-cpu-threads` · `settings-default-tts` · `settings-default-asr` · `settings-show-test` | 모델·작업자 |
| `settings-status` · `settings-error` | 저장 결과 |
| `system-info` · `system-version` · `system-data-dir` | 시스템 정보 |
