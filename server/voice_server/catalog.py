"""미리 지정된 TTS·ASR 엔진과 모델 — 모델 관리 화면과 생성 폼이 이 표를 그린다.

엔진 = 격리된 작업자(engines/adapters/<adapter>.py) + 자기 uv 환경(engines/envs/<env>/).
모델 = 엔진이 싣는 가중치 폴더(<model_root>/<owner>/<repo>). 코덱·보코더처럼 따로 받는 것은 「보조 모델」.
`params` 는 그 엔진만의 생성 옵션 스키마다 — 화면이 이것으로 입력 칸을 만들고, 결과 기록에 그대로 남는다.

TTS 실측치(받아쓰기·VRAM·RTF)는 WanAvatar `docs/tts-model-comparison.md`(2026-11-01, 원격 RTX 4080 16 GB,
일본어 참고 11.5 s → 한국어 10문단, 조건당 1~2회)에서 옮겼다. 사람 청취 판정은 Qwen 만 있다(「오히려 기존 QWEN 이 좋아」).
"""
from __future__ import annotations


def P(key, label, type_, default, help_="", group="advanced", **kw) -> dict:
    return {"key": key, "label": label, "type": type_, "default": default, "help": help_, "group": group, **kw}


LANGS = {"ko": "한국어", "ja": "일본어", "en": "영어", "zh": "중국어", "de": "독일어", "fr": "프랑스어",
         "es": "스페인어", "it": "이탈리아어", "pt": "포르투갈어", "ru": "러시아어", "yue": "광둥어"}

# 서비스가 처리하는 공통 TTS 옵션(엔진에 넘기지 않는다)
TTS_COMMON = [
    P("seed", "시드", "int", -1, "-1 이면 무작위로 뽑아 기록에 남긴다. 같은 시드+같은 설정이면 같은 결과를 노린다", "basic", min=-1, max=2**31 - 1),
    P("split", "나누기", "select", "paragraph", "긴 대본을 나눠 생성한다", "basic",
      options=[["paragraph", "빈 줄(문단)"], ["line", "줄마다"], ["none", "통째로"]]),
    P("pause_s", "문단 사이 쉼(초)", "float", 0.6, "", "basic", min=0, max=5, step=0.05),
    P("normalize_numbers", "숫자를 한글로", "bool", True, "한국어 대본의 3도→삼도·4마디→네 마디(엔진에 넘기기 전)", "basic"),
    P("verify", "받아쓰기 검증", "bool", False, "생성 후 ASR 로 받아 적어 일치율을 기록하고, 문턱 미만이면 다시 뽑는다"),
    P("verify_min", "검증 문턱(일치율)", "float", 0.85, "", min=0, max=1, step=0.01),
    P("lead_low_check", "첫머리 저음 검사", "bool", True, "첫 유성음이 참고 f0 의 0.6배 미만이면 다시 뽑는다(참고 끝 소리 번짐)"),
    P("retries", "불량 시 다시 뽑기(회)", "int", 2, "", min=0, max=5),
]

ASR_COMMON = [
    P("language", "언어", "select", "auto", "", "basic", options=[["auto", "자동 감지"]] + [[k, v] for k, v in LANGS.items()]),
]

ENGINES: dict[str, dict] = {
    # ───────────────────────── TTS ─────────────────────────
    "qwen": {
        "kind": "tts", "label": "Qwen3-TTS Base", "env": "qwen", "adapter": "tts_qwen",
        "languages": ["ko", "ja", "en", "zh", "de", "fr", "es", "it", "pt", "ru"],
        "batch": True, "deterministic": False,
        "use": "기본 나레이션. 발음이 가장 정확하고(받아쓰기 0.975~0.977) 여러 문단을 묶어 생성할 수 있는 유일한 엔진.",
        "caveat": "",
        "params": [
            P("batch_size", "묶음 크기", "int", 6, "문단 여러 개를 한 번에 생성(토큰 루프 한 바퀴). 실측 6", "basic", min=1, max=12),
            P("temperature", "temperature", "float", 0.9, "", min=0.1, max=2, step=0.05),
            P("top_k", "top_k", "int", 50, "", min=1, max=200),
            P("top_p", "top_p", "float", 1.0, "", min=0.05, max=1, step=0.01),
            P("repetition_penalty", "repetition_penalty", "float", 1.05, "", min=1, max=2, step=0.01),
            P("do_sample", "샘플링", "bool", True, "끄면 탐욕 해독"),
            P("subtalker_temperature", "subtalker temperature", "float", 0.9, "", min=0.1, max=2, step=0.05),
            P("subtalker_top_k", "subtalker top_k", "int", 50, "", min=1, max=200),
            P("subtalker_top_p", "subtalker top_p", "float", 1.0, "", min=0.05, max=1, step=0.01),
            P("x_vector_only", "화자 벡터만 쓰기", "bool", False, "참고 전사문 없이 음색만 따른다(ICL 끔)"),
        ],
    },
    "moss": {
        "kind": "tts", "label": "MOSS-TTS v1.5", "env": "moss", "adapter": "tts_moss",
        "languages": ["ko", "ja", "en", "zh"], "batch": False, "deterministic": False,
        "use": "느리고 차분한 낭독(다큐·명상). 발음은 Qwen 과 같은 수준.",
        "caveat": "문장 안에 1~1.75 s 쉼이 들어간다. 8B 는 카드 2장을 한 프로세스가 쓴다.",
        "params": [
            P("audio_temperature", "audio temperature", "float", 1.7, "4B 실측 조건값(8B 는 모델 기본값을 쓴다)", min=0.1, max=3, step=0.05),
            P("audio_top_p", "audio top_p", "float", 0.8, "", min=0.05, max=1, step=0.01),
            P("audio_top_k", "audio top_k", "int", 25, "", min=1, max=200),
            P("audio_repetition_penalty", "audio repetition_penalty", "float", 1.0, "", min=1, max=2, step=0.01),
            P("max_new_tokens", "최대 토큰", "int", 4096, "", min=256, max=16384),
            P("split_layer", "8B 층 분할(카드0 층 수)", "int", 10, "8B 전용. 실측 10 이 맞았고 14 는 카드0 이 넘쳤다", min=1, max=35),
        ],
    },
    "higgs": {
        "kind": "tts", "label": "Higgs TTS 3 4B (transformers 포팅)", "env": "higgs", "adapter": "tts_higgs",
        "languages": ["ko", "ja", "en", "zh"], "batch": False, "deterministic": False,
        "use": "Qwen 과 템포·쉼이 가장 비슷한 두 번째 목소리(내부 시안·비교).",
        "caveat": "비상업 라이선스. 공식 런타임이 아닌 커뮤니티 포팅판.",
        "params": [
            P("temperature", "temperature", "float", 0.8, "모델 카드 예시 값", min=0.1, max=2, step=0.05),
            P("top_k", "top_k", "int", 50, "", min=1, max=200),
        ],
    },
    "omni": {
        "kind": "tts", "label": "OmniVoice", "env": "omni", "adapter": "tts_omni",
        "languages": ["ko", "ja", "en", "zh", "de", "fr", "es", "it", "pt", "ru", "yue"],
        "batch": False, "deterministic": False,
        "use": "가장 빠른 가안(RTF 0.40). 600+ 언어. 확정본은 Qwen 으로.",
        "caveat": "발음이 가끔 뭉개지고 말이 빠르다.",
        "params": [
            P("num_step", "확산 단계", "int", 32, "", min=4, max=64),
            P("guidance_scale", "guidance scale", "float", 2.0, "", min=0, max=10, step=0.1),
            P("speed", "속도", "float", 1.0, "", min=0.5, max=2, step=0.05),
        ],
    },
    "chat": {
        "kind": "tts", "label": "Chatterbox Multilingual V3", "env": "chat", "adapter": "tts_chat",
        "languages": ["ko", "ja", "en", "zh", "de", "fr", "es", "it", "pt", "ru"],
        "batch": False, "deterministic": False,
        "use": "쉼이 거의 없는 촘촘한 발화(광고·쇼츠). VRAM 최소.",
        "caveat": "참고 음성 언어가 대본과 다르면 cfg 를 0 으로(자동).",
        "params": [
            P("cfg_weight", "cfg_weight", "float", -1, "-1 = 자동(참고 언어≠대본 언어면 0, 같으면 0.5)", "basic", min=-1, max=1.5, step=0.05),
            P("exaggeration", "감정 과장", "float", 0.5, "", min=0, max=2, step=0.05),
            P("temperature", "temperature", "float", 0.8, "", min=0.05, max=2, step=0.05),
            P("repetition_penalty", "repetition_penalty", "float", 2.0, "", min=1, max=3, step=0.05),
            P("min_p", "min_p", "float", 0.05, "", min=0, max=1, step=0.01),
            P("top_p", "top_p", "float", 1.0, "", min=0.05, max=1, step=0.01),
        ],
    },
    "cosy": {
        "kind": "tts", "label": "Fun-CosyVoice3", "env": "cosy", "adapter": "tts_cosy",
        "languages": ["ko", "ja", "en", "zh", "de", "fr", "es", "it", "ru", "yue"],
        "batch": False, "deterministic": True,
        "use": "같은 입력이면 같은 출력(md5 동일). 고정 안내 멘트·회귀 시험 기준 음성.",
        "caveat": "발음 정확도가 가장 낮다(0.888).",
        "params": [
            P("speed", "속도", "float", 1.0, "", min=0.5, max=2, step=0.05),
            P("text_frontend", "텍스트 정규화", "bool", True, "CosyVoice 자체 전처리"),
        ],
    },
    "fish": {
        "kind": "tts", "label": "Fish Audio S2-Pro", "env": "fish", "adapter": "tts_fish",
        "languages": ["ko", "ja", "en", "zh", "de", "fr", "es", "it", "pt", "ru"],
        "batch": False, "deterministic": False,
        "use": "비교·연구용.",
        "caveat": "19.7 GB — 16 GB 카드를 넘친다. 가장 느리고 상업 사용 불가.",
        "params": [
            P("temperature", "temperature", "float", 0.8, "", min=0.1, max=2, step=0.05),
            P("top_p", "top_p", "float", 0.8, "", min=0.05, max=1, step=0.01),
            P("repetition_penalty", "repetition_penalty", "float", 1.1, "", min=1, max=2, step=0.01),
            P("max_new_tokens", "최대 토큰", "int", 1024, "0 = 엔진 기본", min=0, max=8192),
            P("chunk_length", "chunk_length", "int", 200, "", min=100, max=300),
        ],
    },
    "drama": {
        "kind": "tts", "label": "Fish Drama 3 (speech.cpp GGUF)", "env": "drama", "adapter": "tts_drama",
        "languages": ["ko", "ja", "en", "zh"], "batch": False, "deterministic": False, "backend": "vulkan",
        "use": "실험용. 연기·감정 표현을 확인할 때.",
        "caveat": "참고 목소리와 덜 닮았다(유사도 0.911). 한국어가 지원 목록에 없다. 카드 메모리와 CPU 를 다 쓴다.",
        "params": [
            P("vulkan_index", "Vulkan 장치 번호", "int", -1, "-1 = 자동(장치 이름·UUID 로 맞춘다). Vulkan 번호는 CUDA 번호와 다르다", min=-1, max=7),
        ],
    },
    "xvoice": {
        "kind": "tts", "label": "X-Voice Stage1 (F5-TTS 계열)", "env": "xvoice", "adapter": "tts_xvoice",
        "languages": ["ko", "ja", "en", "zh", "de", "fr", "es", "it", "pt", "ru"],
        "batch": False, "deterministic": False,
        "use": "실험용. 가장 작은 모델(2.0 GB).",
        "caveat": "발음이 뭉개지고 첫머리 저음이 생긴다(3/10). 비상업.",
        "params": [
            P("nfe_step", "NFE 단계", "int", 32, "", min=4, max=64),
            P("cfg_strength", "cfg strength", "float", 2.0, "", min=0, max=5, step=0.1),
            P("speed", "속도", "float", 1.0, "", min=0.5, max=2, step=0.05),
        ],
    },
    # ───────────────────────── ASR ─────────────────────────
    "fwhisper": {
        "kind": "asr", "label": "faster-whisper (CTranslate2)", "env": "fwhisper", "adapter": "asr_fwhisper",
        "languages": list(LANGS), "cpu_ok": True,
        "use": "기본 ASR. 단어 시각·VAD. 참고 음성 자동 전사에도 쓴다.",
        "caveat": "단어 시각은 실제보다 늘어진다(±0.2 s) — 쉼은 소리 크기로 다시 잰다.",
        "params": [
            P("beam_size", "beam size", "int", 5, "", "basic", min=1, max=10),
            P("vad_filter", "VAD(무음 거르기)", "bool", True, "", "basic"),
            P("word_timestamps", "단어 시각", "bool", True, "", "basic"),
            P("compute_type", "연산 정밀도", "select", "auto", "", options=[["auto", "자동(GPU float16 · CPU int8)"], ["float16", "float16"], ["int8_float16", "int8_float16"], ["int8", "int8"], ["float32", "float32"]]),
            P("temperature", "temperature", "float", 0.0, "0 = 탐욕(실패 시 엔진이 올려 재시도)", min=0, max=1, step=0.1),
            P("condition_on_previous_text", "앞 문장 이어 받기", "bool", True, "끄면 반복 폭주가 줄어든다"),
            P("initial_prompt", "힌트 문장", "text", "", "고유명사·표기 힌트"),
        ],
    },
    "hfwhisper": {
        "kind": "asr", "label": "Whisper (transformers)", "env": "hfwhisper", "adapter": "asr_hfwhisper",
        "languages": list(LANGS), "cpu_ok": True,
        "use": "원본 OpenAI 가중치(transformers). faster-whisper 와 결과 비교용.",
        "caveat": "",
        "params": [
            P("batch_size", "묶음 크기", "int", 8, "", min=1, max=32),
            P("chunk_length_s", "조각 길이(초)", "int", 30, "", min=10, max=30),
            P("word_timestamps", "단어 시각", "bool", True, "", "basic"),
        ],
    },
    "qwen3asr": {
        "kind": "asr", "label": "Qwen3-ASR (+ForcedAligner)", "env": "qwen3asr", "adapter": "asr_qwen3",
        "languages": list(LANGS), "cpu_ok": False,
        "use": "다국어 SOTA 급 공개 ASR. 시각은 ForcedAligner(11개 언어, 한국어 포함)로 맞춘다.",
        "caveat": "시각 정렬에는 보조 모델 Qwen3-ForcedAligner-0.6B 가 필요하다.",
        "params": [
            P("timestamps", "시각 정렬(ForcedAligner)", "bool", True, "", "basic"),
            P("max_new_tokens", "최대 토큰", "int", 1024, "", min=128, max=8192),
        ],
    },
    "sensevoice": {
        "kind": "asr", "label": "SenseVoice Small (FunASR)", "env": "sensevoice", "adapter": "asr_sensevoice",
        "languages": ["ko", "ja", "en", "zh", "yue"], "cpu_ok": True,
        "use": "매우 빠른 비자기회귀 ASR(5개 언어). 감정·이벤트 태그.",
        "caveat": "시각은 VAD 구간 단위(단어 시각 없음).",
        "params": [
            P("use_itn", "역정규화(숫자·문장부호)", "bool", True, "", "basic"),
            P("merge_length_s", "구간 합치기(초)", "float", 15, "", min=1, max=60, step=1),
        ],
    },
    # ───────────────────────── 시험용 ─────────────────────────
    "mock_tts": {
        "kind": "tts", "label": "시험용 TTS(모의)", "env": "server", "adapter": "mock", "test": True,
        "languages": list(LANGS), "batch": True, "deterministic": True, "cpu_ok": True,
        "use": "GPU·가중치 없이 UI·큐·저장·재현을 시험한다(사인파).", "caveat": "실제 음성이 아니다.",
        "params": [P("pitch_hz", "음높이(Hz)", "float", 220.0, "", "basic", min=80, max=800, step=1)],
    },
    "mock_asr": {
        "kind": "asr", "label": "시험용 ASR(모의)", "env": "server", "adapter": "mock", "test": True,
        "languages": list(LANGS), "cpu_ok": True,
        "use": "시험용 — 소리 크기로 구간을 나누고 고정 문장을 돌려준다.", "caveat": "실제 인식이 아니다.",
        "params": [],
    },
}

APACHE = "Apache-2.0"
MODELS: dict[str, dict] = {
    # TTS
    "qwen3-tts-1.7b-base": {"engine": "qwen", "repo": "Qwen/Qwen3-TTS-12Hz-1.7B-Base", "label": "Qwen3-TTS 12Hz 1.7B Base",
                            "size_gb": 4.54, "vram_gb": 4.4, "license": APACHE, "commercial": True, "default": True,
                            "need": ["config.json", "*.safetensors"],
                            "measured": "받아쓰기 0.975~0.977 · 유사도 0.966 · RTF 4.2(문단별, 6묶음이면 3~4배 빠름) · 4.4 GB · 사용자 청취 최상"},
    "qwen3-tts-0.6b-base": {"engine": "qwen", "repo": "Qwen/Qwen3-TTS-12Hz-0.6B-Base", "label": "Qwen3-TTS 12Hz 0.6B Base",
                            "size_gb": 2.5, "vram_gb": 3.0, "license": APACHE, "commercial": True,
                            "need": ["config.json", "*.safetensors"], "measured": "실측 없음"},
    "moss-tts-local-v1.5": {"engine": "moss", "repo": "OpenMOSS-Team/MOSS-TTS-Local-Transformer-v1.5", "label": "MOSS-TTS Local-Transformer v1.5 (4B)",
                            "size_gb": 9.0, "vram_gb": 12.0, "license": APACHE, "commercial": True, "requires": ["moss-audio-tokenizer-v2"],
                            "need": ["config.json"], "measured": "받아쓰기 0.969~0.974 · RTF 1.78 · 12 GB · 쉼 0.29~0.33"},
    "moss-tts-v1.5-8b": {"engine": "moss", "repo": "OpenMOSS-Team/MOSS-TTS-v1.5", "label": "MOSS-TTS v1.5 8B (카드 2장)",
                         "size_gb": 17.0, "vram_gb": 10.5, "gpus": 2, "license": APACHE, "commercial": True, "requires": ["moss-audio-tokenizer"],
                         "need": ["config.json"], "measured": "받아쓰기 0.977 · RTF 2.37 · GPU0 7.2 + GPU1 10.5 GB"},
    "moss-audio-tokenizer-v2": {"engine": "moss", "aux": True, "repo": "OpenMOSS-Team/MOSS-Audio-Tokenizer-v2", "label": "MOSS 오디오 토크나이저 v2(코덱)",
                                "size_gb": 1.7, "license": APACHE, "commercial": True, "need": ["config.json"]},
    "moss-audio-tokenizer": {"engine": "moss", "aux": True, "repo": "OpenMOSS-Team/MOSS-Audio-Tokenizer", "label": "MOSS 오디오 토크나이저(코덱, 8B 용)",
                             "size_gb": 1.7, "license": APACHE, "commercial": True, "need": ["config.json"]},
    "higgs-v3-4b-tf": {"engine": "higgs", "repo": "multimodalart/higgs-audio-v3-tts-4b-transformers", "label": "Higgs Audio v3 TTS 4B (transformers)",
                       "size_gb": 9.0, "vram_gb": 8.7, "license": "Boson 연구·비상업", "commercial": False, "requires": ["higgs-v2-tokenizer"],
                       "need": ["config.json"], "measured": "받아쓰기 0.968 · RTF 2.39 · 8.7 GB"},
    "higgs-v2-tokenizer": {"engine": "higgs", "aux": True, "repo": "bosonai/higgs-audio-v2-tokenizer", "label": "Higgs 오디오 토크나이저 v2(코덱)",
                           "size_gb": 0.8, "license": "Boson 연구·비상업", "commercial": False, "need": ["config.json"]},
    "omnivoice": {"engine": "omni", "repo": "k2-fsa/OmniVoice", "label": "OmniVoice 0.6B", "size_gb": 3.0, "vram_gb": 4.8,
                  "license": "Apache-2.0(2차 출처)", "commercial": True, "need": ["config.json"],
                  "measured": "받아쓰기 0.909~0.929 · RTF 0.40 · 4.8 GB"},
    "chatterbox-mtl-v3": {"engine": "chat", "repo": "ResembleAI/chatterbox", "label": "Chatterbox Multilingual V3 0.5B", "size_gb": 6.0, "vram_gb": 3.6,
                          "license": "MIT(2차 출처)", "commercial": True, "need": ["*.safetensors"],
                          "measured": "받아쓰기 0.929~0.953 · RTF 1.38 · 3.6 GB"},
    "cosyvoice3-0.5b": {"engine": "cosy", "repo": "FunAudioLLM/Fun-CosyVoice3-0.5B-2512", "label": "Fun-CosyVoice3 0.5B (2512)", "size_gb": 5.0, "vram_gb": 3.5,
                        "license": "Apache-2.0(2차 출처)", "commercial": True, "need": ["cosyvoice3.yaml"],
                        "measured": "받아쓰기 0.888 · RTF 1.37 · 3.5 GB · 결정적"},
    "fish-s2-pro": {"engine": "fish", "repo": "fishaudio/s2-pro", "label": "Fish Audio S2-Pro 4B", "size_gb": 11.0, "vram_gb": 19.7,
                    "license": "Fish Audio Research(상업 별도 계약)", "commercial": False, "need": ["config.json"],
                    "measured": "받아쓰기 0.949~0.952 · RTF 4.97 · 19.7 GB"},
    "drama-3-q4k": {"engine": "drama", "repo": "sakasegawa/drama-3-GGUF", "label": "Fish Drama 3 35B-A3B Q4_K (GGUF)", "size_gb": 20.8, "vram_gb": 15.0,
                    "license": "Fish Audio Community 1.0(연매출 50만 달러까지)", "commercial": "limited",
                    "file": "Drama-35B-A3B-v3-Q4_K.gguf", "allow": ["Drama-35B-A3B-v3-Q4_K.gguf", "*.md", "*.json"],
                    "need": ["Drama-35B-A3B-v3-Q4_K.gguf"], "measured": "받아쓰기 0.955 · 유사도 0.911 · RTF 1.64 · 16 GB+CPU"},
    "xvoice-stage1": {"engine": "xvoice", "repo": "XRXRX/X-Voice", "label": "X-Voice Base Stage1 0.4B", "size_gb": 1.5, "vram_gb": 2.0,
                      "license": "CC BY-NC 4.0", "commercial": False, "requires": ["vocos-mel-24khz"], "sub": "XVoice_Base_Stage1",
                      "allow": ["XVoice_Base_Stage1/*", "*.md"], "need": ["XVoice_Base_Stage1/model_600000.safetensors", "XVoice_Base_Stage1/vocab.txt"],
                      "measured": "받아쓰기 0.897 · RTF 0.56 · 2.0 GB · 첫머리 저음 3/10"},
    "vocos-mel-24khz": {"engine": "xvoice", "aux": True, "repo": "charactr/vocos-mel-24khz", "label": "Vocos mel 24 kHz(보코더)", "size_gb": 0.05,
                        "license": "MIT", "commercial": True, "need": ["config.yaml"]},
    # ASR
    "fw-large-v3": {"engine": "fwhisper", "repo": "Systran/faster-whisper-large-v3", "label": "faster-whisper large-v3", "size_gb": 3.1, "vram_gb": 4.5,
                    "license": "MIT", "commercial": True, "default": True, "need": ["model.bin", "config.json"]},
    "fw-large-v3-turbo": {"engine": "fwhisper", "repo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo", "label": "faster-whisper large-v3-turbo", "size_gb": 1.6,
                          "vram_gb": 2.5, "license": "MIT", "commercial": True, "need": ["model.bin", "config.json"]},
    "fw-medium": {"engine": "fwhisper", "repo": "Systran/faster-whisper-medium", "label": "faster-whisper medium", "size_gb": 1.5, "vram_gb": 2.5,
                  "license": "MIT", "commercial": True, "need": ["model.bin", "config.json"]},
    "whisper-large-v3": {"engine": "hfwhisper", "repo": "openai/whisper-large-v3", "label": "Whisper large-v3 (OpenAI)", "size_gb": 3.1, "vram_gb": 5.0,
                         "license": "Apache-2.0", "commercial": True, "allow": ["*.json", "model.safetensors", "*.txt", "*.md"], "need": ["config.json", "*.safetensors"]},
    "whisper-large-v3-turbo": {"engine": "hfwhisper", "repo": "openai/whisper-large-v3-turbo", "label": "Whisper large-v3-turbo (OpenAI)", "size_gb": 1.6,
                               "vram_gb": 3.0, "license": "MIT", "commercial": True, "allow": ["*.json", "model.safetensors", "*.txt", "*.md"],
                               "need": ["config.json", "*.safetensors"]},
    "qwen3-asr-1.7b": {"engine": "qwen3asr", "repo": "Qwen/Qwen3-ASR-1.7B", "label": "Qwen3-ASR 1.7B", "size_gb": 4.7, "vram_gb": 6.0,
                       "license": APACHE, "commercial": True, "requires": ["qwen3-forced-aligner-0.6b"], "need": ["config.json"]},
    "qwen3-asr-0.6b": {"engine": "qwen3asr", "repo": "Qwen/Qwen3-ASR-0.6B", "label": "Qwen3-ASR 0.6B", "size_gb": 1.9, "vram_gb": 3.5,
                       "license": APACHE, "commercial": True, "requires": ["qwen3-forced-aligner-0.6b"], "need": ["config.json"]},
    "qwen3-forced-aligner-0.6b": {"engine": "qwen3asr", "aux": True, "repo": "Qwen/Qwen3-ForcedAligner-0.6B", "label": "Qwen3-ForcedAligner 0.6B(시각 정렬)",
                                  "size_gb": 1.9, "license": APACHE, "commercial": True, "need": ["config.json"]},
    "sensevoice-small": {"engine": "sensevoice", "repo": "FunAudioLLM/SenseVoiceSmall", "label": "SenseVoice Small", "size_gb": 0.9, "vram_gb": 1.5,
                         "license": "FunASR 모델 라이선스(모델 카드 확인)", "commercial": None, "requires": ["fsmn-vad"], "need": ["model.pt"]},
    "fsmn-vad": {"engine": "sensevoice", "aux": True, "repo": "funasr/fsmn-vad", "label": "FSMN VAD(구간 나누기)", "size_gb": 0.01,
                 "license": "FunASR 모델 라이선스(모델 카드 확인)", "commercial": None, "need": ["model.pt"]},
    # 시험용
    "mock-tts": {"engine": "mock_tts", "repo": "", "label": "모의 TTS", "size_gb": 0, "vram_gb": 0, "license": "—", "commercial": True, "builtin": True, "need": []},
    "mock-asr": {"engine": "mock_asr", "repo": "", "label": "모의 ASR", "size_gb": 0, "vram_gb": 0, "license": "—", "commercial": True, "builtin": True, "need": []},
}

for _k, _m in MODELS.items():
    _m["id"] = _k
    _m.setdefault("gpus", 1)
    _m.setdefault("requires", [])
    _m["kind"] = "aux" if _m.get("aux") else ENGINES[_m["engine"]]["kind"]
for _k, _e in ENGINES.items():
    _e["key"] = _k
    _e["models"] = [m for m, v in MODELS.items() if v["engine"] == _k and not v.get("aux")]
    _e["common"] = TTS_COMMON if _e["kind"] == "tts" else ASR_COMMON


def visible(show_test: bool) -> tuple[dict, dict]:
    eng = {k: v for k, v in ENGINES.items() if show_test or not v.get("test")}
    mods = {k: v for k, v in MODELS.items() if v["engine"] in eng}
    return eng, mods


def resolve_params(engine: str, given: dict) -> dict:
    """스키마 기본값을 채운 「실제로 쓴 값」 — 결과 기록에 이것을 남긴다(기본값이 나중에 바뀌어도 재현되게)."""
    e = ENGINES[engine]
    out = {}
    for p in e["common"] + e["params"]:
        v = given.get(p["key"], p["default"])
        if p["type"] == "int":
            v = int(v)
        elif p["type"] == "float":
            v = float(v)
        elif p["type"] == "bool":
            v = bool(v) if not isinstance(v, str) else v.lower() in ("1", "true", "on", "yes")
        out[p["key"]] = v
    return out
