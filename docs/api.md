# HTTP API

기본 주소 `http://127.0.0.1:8765`. 본문은 JSON(업로드만 multipart). 오류는 `{"detail": "사람 말"}` + 4xx.
긴 일은 전부 **작업(Job)** 으로 돌려준다 — `POST` 가 작업 보기를 돌려주고, 화면은 `GET /api/jobs/{id}` 를 1초마다 본다.

## 작업(Job) 보기

```json
{"id": "20261102-120432-1fa3fe", "kind": "tts|asr|ref|env|download|load", "title": "…",
 "status": "queued|waiting|loading|running|done|error|cancelled", "stage": "사람 말 단계",
 "progress": 0.0, "created": 1793588672.8, "started": …, "finished": …, "error": "",
 "devices": [0] | ["cpu"], "result": {…}, "cancel_note": "작업자 PID … 트리 종료 확인", "log": ["12:04:32 …"]}
```
`log` 는 `GET /api/jobs/{id}` 에만 있다. 끝난 작업 `result`: tts → `{generation_id, duration, status}` · asr → `{transcript_id, segments, language}` ·
ref → `{ref_id, text, language, window}` · download → 모델별 확인 결과 · env → 설치 정보.

| 메서드 · 경로 | 하는 일 |
|---|---|
| `GET /api/health` | `{ok, service: {version, git, dirty}, data_dir}` |
| `GET /api/system` | OS·CPU·RAM·`gpus[]`(index·name·uuid·total/free/used_gb·temp_c·util·allowed·blocked[이유]·ours_gb·foreign_est_gb)·`workers[]` |
| `GET/PUT /api/settings` · `POST /api/settings/reset` | 설정 전체 / 일부 갱신(모르는 키는 400) |
| `GET /api/catalog` | `{languages, engines, models, envs, defaults}` — 아래 |
| `GET /api/models/{id}` | 모델 하나 + `fingerprint` |
| `PUT /api/models/{id}/path` `{path}` | 「이미 받은 위치」 지정(빈 값이면 기본 위치로). 확인 결과를 돌려준다 |
| `POST /api/models/{id}/download` | 받기 작업(필요한 보조 모델도 함께). `job.extra.bytes = [받은, 전체]` |
| `POST /api/envs/{env}/install` · `GET /api/envs` | 엔진 환경 설치 작업 / 상태 |
| `GET /api/jobs` · `GET /api/jobs/{id}` · `POST /api/jobs/{id}/cancel` | 작업 목록 / 하나(+log) / 취소 |
| `GET /api/workers` · `POST /api/workers/{pid}/stop` · `POST /api/workers/preload {model}` | 상주 작업자 |
| `POST /api/uploads`(multipart `file`) · `GET /api/uploads` · `GET /api/uploads/{id}/audio` · `DELETE` | 음성 올리기(아무 형식 → wav) |
| `POST /api/refs` · `GET /api/refs` · `GET/PATCH/DELETE /api/refs/{id}` | 참조 세트 |
| `POST /api/refs/{id}/recut {start,end,text?}` | 구간 다시 자르기(CPU, 즉시) |
| `GET /api/refs/{id}/audio?which=clip|source` | 잘라 낸 참고 / 원본 |
| `POST /api/text/preview {text, language, split, normalize_numbers}` | 생성 전 미리보기 → `{text_used, parts[], count}`(tts 와 같은 숫자 풀기·나누기) |
| `POST /api/tts` · `GET /api/generations` · `GET/PATCH(name)/DELETE /api/generations/{id}` | 생성 · 결과 |
| `GET /api/generations/{id}/audio[?part=n | ?which=ref]` | 결과 / 문단 / 그때 쓴 참고 |
| `POST /api/asr` · `GET /api/transcripts` · `GET/PATCH/DELETE /api/transcripts/{id}` | 전사 |
| `GET /api/transcripts/{id}/export?fmt=srt|vtt|txt|json&max_chars=0` | 내려받기 |

## 카탈로그

```json
{"languages": {"ko": "한국어", …},
 "engines": {"qwen": {"key", "kind": "tts|asr", "label", "env", "languages": ["ko", …], "batch", "deterministic",
                      "use", "caveat", "models": ["qwen3-tts-1.7b-base", …],
                      "common": [파라미터…], "params": [파라미터…], "cpu_ok"?, "test"?}},
 "models": {"qwen3-tts-1.7b-base": {"id", "engine", "kind": "tts|asr|aux", "repo", "label", "size_gb", "vram_gb", "gpus",
            "license", "commercial": true|false|"limited"|null, "requires": [보조 모델 id], "measured"?, "default"?,
            "location": "S:\\models\\Qwen\\…", "check": {"ok", "path", "missing": [], "size_gb", "error"?, "custom"}}},
 "envs": {"qwen": {"env", "installed", "python"?, "torch"?, "installed_at"?, "freeze_sha"?}},
 "defaults": {"tts_model", "asr_model"}}
```
파라미터: `{"key", "label", "type": "int|float|bool|select|text", "default", "help", "group": "basic|advanced", "min"?, "max"?, "step"?, "options"?: [[값, 이름]]}`.
`common` 은 서비스가 처리하는 값(시드·나누기·검증 …), `params` 는 엔진에 넘기는 값. 요청의 `params` 에는 둘을 섞어 `{key: 값}` 으로 보낸다.

## 요청 본문

```jsonc
// POST /api/refs  — 참조 세트 만들기
{"upload_id": "…", "name": "…", "mode": "auto|manual",
 "language": "",          // auto 면 비워 두면 ASR 이 감지, manual 이면 필수
 "text": "",              // auto 면 비우면 ASR 결과, manual 이면 필수
 "start": null, "end": null,   // 초. 비우면 auto 는 8~15 s 창 자동 선택, manual 은 앞뒤 무음만 걷음
 "asr_model": "fw-large-v3", "asr_params": {},
 "consent": {"basis": "self|other_consent|licensed|synthetic", "agreed": true, "note": ""}}

// POST /api/tts
{"model": "qwen3-tts-1.7b-base", "text": "대본(빈 줄 = 문단)", "language": "ko",
 "ref_id": "…" /* 또는 */ , "ref_from_generation": "결과 id(그때 참고 사본을 쓴다)",
 "ref_text": "",          // 이번 생성에만 참고 전사문을 고쳐 쓸 때
 "params": {"seed": -1, "split": "paragraph", "temperature": 0.9, …}, "name": ""}

// POST /api/asr
{"model": "fw-large-v3", "upload_id": "…", "language": "auto", "params": {"beam_size": 5, …}, "name": ""}
```

## 결과 기록(재현)

`GET /api/generations/{id}`:
`engine, model{ id, repo, path, revision(HF 커밋), sha(설정 파일 해시+가중치 이름·크기), files }, aux_models[], env{torch, transformers, …, freeze_sha, python},
service{version, git, dirty}, device[{index, name, uuid}], language, text(원문), text_used(엔진에 넘긴 글), params(기본값까지 채운 전부; seed 는 실제 값),
seed, ref{id, name, rev, language, text, window, cut, pad, f0_median, clip_sha256, consent, upload}, parts[{i, text, seed, seed_used, file, dur, infer_s, attempts,
checks{basic, lead_low_s, match, heard, tail_noise_s, failed}}], output{file, sr, duration, sha256}, timings{gen_s, verify_s, total_s}, license, commercial, status: ok|warn`

**불러오기** = 화면이 이 기록으로 폼을 채운다: `model`, `language`, `text`, `params`(seed 포함 실제 값),
참고는 `ref.id` 가 아직 있고 `clip_sha256` 이 같으면 그 세트, 아니면 `ref_from_generation={id}` 로 그때 사본을 쓴다.

`GET /api/transcripts/{id}`: `upload{…}, engine, model{지문}, env, params, language, segments[{start, end, text, words?[{start, end, word, prob}]}], device, timings, edited?`
