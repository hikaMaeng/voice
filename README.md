로컬 설치형 TTS·ASR 웹 서비스 — 제로샷 목소리 복제 TTS 10종·ASR 4종을 모델 관리·참조 세트·재현 가능한 결과·자막 출력과 함께 웹으로 쓴다(도커 없음, node + uv).

| Goal                | File                |
|---------------------|---------------------|
| Understand purpose  | README.md           |
| API reference       | docs/api.md         |
| Constraints         | docs/constraints.md |
| Testing             | docs/testing.md     |

| 더 보기 | 파일 |
|---|---|
| 무엇을 하나 · 화면 | [docs/overview.md](docs/overview.md) |
| 구조(서버 · 작업자 · 큐) | [docs/architecture.md](docs/architecture.md) |
| 설치 · 실행 · 다른 PC 이식 | [docs/usage.md](docs/usage.md) |
| 엔진 · 모델 · 라이선스 · 설치 정의 | [docs/internals.md](docs/internals.md) |

## 빠른 시작

```bash
npm run deploy
```

`http://127.0.0.1:8765` 를 연다. 필요: Node 20+, [uv](https://docs.astral.sh/uv/), Git. NVIDIA GPU 가 있으면 쓰고 없으면 CPU 로 도는 엔진만 쓴다.
엔진 환경과 모델은 웹의 **모델 관리** 화면에서 설치·받기·위치 지정한다.
