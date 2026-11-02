# voice 저장소 규칙

- 출력·문서·커밋 설명은 한국어. 코드 식별자·명령은 원문.
- 서버(`server/voice_server`)는 오케스트레이션만 — torch·엔진 패키지를 서버 환경(`pyproject.toml`)에 넣지 않는다. 엔진 의존성은 `engines/envs/<env>/env.json` + 고정 목록.
- 어댑터(`engines/adapters`)는 서버 패키지를 import 하지 않는다(엔진 환경에서 돈다). 공용은 `_common.py`.
- GPU 번호·모델 경로를 코드에 박지 않는다 — 카드 선택은 설정 `allowed_gpus`(uuid), 모델 위치는 `model_root`/`model_paths`.
- 프로세스 정리는 PID 로만(`pkill -f`·이름 매칭 금지). 취소는 트리 종료 + 확인.
- 배포·검증 진입점: `npm run deploy`(도커 대신 — docs/constraints.md). 완료 = 문서 + deploy + 헤드리스 브라우저 검증 + `tests/plans`·`tests/reports` + 커밋.
- 결과 기록 형식(재현 필드)을 바꾸면 docs/api.md 「결과 기록」과 웹의 불러오기를 함께 고친다.
- push 는 사용자 지시 때만.
