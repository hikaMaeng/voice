# 내부

## 엔진 · 모델 카탈로그 (정본: `server/voice_server/catalog.py`)

TTS 10종(실측: 원격 RTX 4080 16 GB, 일본어 참고 11.5 s → 한국어 10문단, 조건당 1~2회, Whisper medium 받아쓰기 일치율. 출처 WanAvatar `docs/tts-model-comparison.md`):

| 엔진 · 모델 | 환경 | 상업 | 받아쓰기 | VRAM | 비고 |
|---|---|---|---|---|---|
| qwen · Qwen3-TTS 1.7B Base(**기본**) / 0.6B Base | qwen(torch 2.8 · transformers 4.57.3) | ○ Apache | 0.975~0.977 | 4.4 GB | 묶음 생성(6) |
| moss · MOSS-TTS Local-Transformer v1.5 4B | moss(torch 2.9.1 · transformers 5.0.0) | ○ | 0.969~0.974 | 12 GB | 문장 안 1~1.75 s 쉼 |
| moss · MOSS-TTS v1.5 8B | moss | ○ | 0.977 | 7.2+10.5 GB | **카드 2장**(층 10/26 분할) |
| higgs · Higgs v3 4B(transformers 포팅) | higgs(transformers 5.22.1) | ✕ | 0.968 | 8.7 GB | |
| omni · OmniVoice 0.6B | omni | ○ | 0.909~0.929 | 4.8 GB | RTF 0.40 |
| chat · Chatterbox Multilingual V3 | chat(torch 2.6) | ○ MIT | 0.929~0.953 | 3.6 GB | 참고 언어≠대본 언어면 cfg 0(자동). 이 서비스 실측: 짧은 첫 문단이 27.3 s 로 폭주(3090·4080 에서 같은 길이로 재현) → `warn` |
| cosy · Fun-CosyVoice3 0.5B | cosy(Python 3.10 · torch 2.3.1) | ○ | 0.888 | 3.5 GB | 결정적 |
| fish · Fish S2-Pro 4B | fish | ✕ | 0.949~0.952 | 19.7 GB | 16 GB 카드 넘침 |
| drama · Fish Drama 3 Q4_K GGUF | drama(speech.cpp 0.10.0 Vulkan) | △ | 0.955 | 16 GB+CPU | Vulkan 번호 ≠ CUDA 번호. 카드 이름으로 맞추고, 같은 이름(4080x2)이면 남은 메모리로 가리며 못 가리면 경고 — 옵션 「Vulkan 장치 번호」로 고정 |
| xvoice · X-Voice Stage1 0.4B | xvoice(transformers 4.48.3, eSpeak) | ✕ NC | 0.897 | 2.0 GB | 첫머리 저음 3/10 |

ASR 5종 9모델: faster-whisper(large-v3 **기본**·large-v3-turbo·medium) · Whisper transformers(large-v3·large-v3-turbo) ·
Qwen3-ASR(1.7B·0.6B + ForcedAligner 0.6B) · SenseVoice Small(+FSMN VAD) · NVIDIA Nemotron 3.5 ASR Streaming 0.6B.

| ASR | 시각 | 비고 |
|---|---|---|
| faster-whisper | 단어(±0.2 s) | VAD. PyAV 판 충돌로 파일 대신 16 kHz 배열을 넘긴다 |
| Whisper transformers | 단어 / 일·중은 구간 | 띄어쓰기 없는 언어는 파이프라인 「단어」가 문장 덩어리(일본어 25 s 에 7개) → 구간 시각 |
| Qwen3-ASR | 단어(ForcedAligner, 11개 언어) | |
| SenseVoice | VAD 구간(상한 10 s) | 30 s 상한이면 깨끗한 음성 25 s 가 한 구간이었다 |
| Nemotron 3.5 ASR | 소리 크기로 나눈 구간 | 카드에 시각 출력이 없다. NeMo 대신 transformers(`AutoModelForRNNT`, ≥5.13). 언어는 locale(ko-KR·ja-JP — `ja` 는 거절된다). **자동 감지는 한국어 첫 구간을 일본어로 오인**(실측) → 언어 지정 권장 |

넣지 않은 것: **Nemotron 3.5 Transcribe 30B-A4B**(2026-10-28, 67.5 GB BF16) — 공식 런타임이 vLLM(Linux)·H100 80 GB 대상이고
Windows 네이티브는 GGML 로 RTX 5090·PRO 6000 만 지원한다고 카드가 적는다. 3090·4080 에서는 돌릴 수 없다(FP8·NVFP4 판도 30B 급).
Step-Audio 는 한국어 발음이 무너져 넣지 않는다(WanAvatar 결정).

## 엔진 환경 설치 정의 (`engines/envs/<env>/env.json`)

`python` · `torch_backend`(uv `--torch-backend`; NVIDIA 없으면 cpu 로) · `repos[{url, commit, dir, recursive}]` · `assets[{os, url, dest, kind: zip|msi, check}]` ·
`steps[{os?, lock|req|pip|editable, no_deps?, torch?, pypi?}]` · `check`.
- `lock-win32.txt` = 원격 4080x2 에서 **실제로 10종이 돈 환경의 `uv pip freeze`**(2026-11-02). 설치 때 `+cu128` 표기와 `-e` 줄을 걷어 내고 쓴다.
- `pypi: ["torchcodec"]`: torch 색인에 Windows 휠이 없는 패키지는 PyPI 일반 판을 `--no-deps` 로 따로 받는다.
- ASR 환경(fwhisper·hfwhisper·qwen3asr·sensevoice)은 원격 고정 목록이 없어 이름만 적었고, 설치 후 `envs/<env>/freeze.txt` 가 그 기계의 실제 판이다.
- 설치가 끝나면 `envs/<env>/voice-env.json`(python·torch·freeze_sha·repos 커밋) — 결과 기록의 `env` 가 이것을 쓴다.

## 작업자 규약 (`engines/runtime/voice_worker.py`)

stdin JSON 한 줄 = 요청. `load {model: {id, path, aux{id: path}, file?, sub?}}` · `tts {items[{text, out, seed}], ref{audio, text, language}, language, params}` ·
`asr {audio, language|null, params}` · `ping` · `shutdown`. 응답 `progress`(stage·done·total·pct·log) → `result` | `error{message, trace}`.
프로토콜은 원래 fd 1 의 복제본으로만 쓰고 fd 1 은 stderr 로 돌린다(라이브러리 출력이 프로토콜을 깨지 않게).
어댑터(`engines/adapters/*.py`)는 `load()` + `tts()`/`tts_batch()` 또는 `asr()`. 엔진 판마다 인자 이름이 달라 `filtered()` 로 받는 인자만 넘기고, 못 넘긴 키는 로그에 남긴다.
시드: 문단 i 는 `seed + i`, 다시 뽑기 a 회째는 `+ 7919·a`. 묶음 생성(qwen)은 묶음 첫 문단의 시드를 쓰고 `seed_used` 로 기록.

## 참고(제로샷) 음성 (`server/voice_server/audio.py`)

| 규칙 | 근거(WanAvatar 실측) |
|---|---|
| 문장 경계에서만 자르고 8~15 s, 말이 빽빽하고 1 s 넘는 쉼이 없는 창 | 말 중간에서 자르면 끊긴 억양을 배운다 |
| 끝은 조용해진 뒤 소리가 다시 커지는 지점 앞에서 · 끝에 0.4 s 무음 · 앞 0.1 s | 참고 끝 0.1 s 의 97 Hz 저음 → 출력 첫머리 저음 8/40 → 수정 후 0/40 |
| 파일 끝을 「쉼」으로 치지 않는다 | 샘플이 다음 소리 도중에 잘려 있을 수 있다 |
| 쉼은 소리 크기로 잰다 | Whisper 단어 끝 20.28 s ↔ 실제 19.8 s |
| 자동 전사문은 사람이 고친다(PATCH·recut) | 복제 품질이 참고 전사 정확도에 기댄다 |

결과 검사: 기본(`check_wav`: 존재·NaN·무음·글자당 0.04~0.6 s) · 문단 길이 이상(`rate_outliers`: 문단 3개 이상에서 글자당 길이가 중앙값의 1.8배·+2 s 초과) · 끝 소음(`tail_noise`, 검증 켬: 받아쓰기 마지막 구간 끝 + 0.4 s 뒤 큰 소리 ≥ 1 s — Chatterbox 가 문단 끝에 말 아닌 소리 5~14 s 를 붙였는데 일치율 1.0·길이 검사 통과로 `ok` 였던 실측(스킬 시험 2026-11-02)에서 넣었다) · 첫머리 저음(`lead_low` ≥ 0.15 s: 첫 유성음 f0 < 참고 f0 × 0.6 — 받아쓰기는 이것을 못 잡는다) ·
받아쓰기 검증(선택, 기본 ASR 로 받아 적어 글자 일치율 < 문턱이면 다시). 일치율은 거친 자다(고유명사·숫자는 ASR 쪽이 틀리기도 한다).
한국어 숫자는 엔진에 넘기기 전에 글자로 푼다(`textnorm.py`, WanAvatar `ko_numbers.py` 복사).

## 재현 기록

결과(`generations`)는 api.md 「결과 기록」 필드를 모두 담는다. 모델 지문 = 4 MiB 미만 파일은 내용 sha256, 큰 가중치는 이름·크기(+ `.cache/huggingface/download/*.metadata` 의 HF 커밋).
NAS 의 수 GB 가중치를 매번 해시하지 않는 대신 「같은 파일 이름·크기·설정 파일」을 같은 모델로 본다 — 가중치만 같은 크기로 바뀌면 못 가린다(한계).
결정적이지 않은 엔진은 같은 시드여도 GPU 커널 비결정성 때문에 비트 단위로 같지 않을 수 있다(cosy·모의 엔진은 같다).
