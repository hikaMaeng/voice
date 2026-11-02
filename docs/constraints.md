# 제약

## 실행

- 도커를 쓰지 않는다(사용자 지시). 표준 배포 진입점 `npm run deploy` 가 compose 대신 같은 계약을 맡는다:
  로컬 빌드(uv sync · npm ci · vite build) → **이전 인스턴스 제거**(PID 파일의 프로세스 트리 종료 + 포트 해제 확인) → 새 인스턴스 기동 → health 확인.
- 서버는 기본 `127.0.0.1` 에만 연다. 인증이 없으므로 `0.0.0.0` 은 믿는 LAN 에서만.
- 엔진 환경은 엔진마다 따로(`envs/<env>`). 서버 환경에 torch 를 넣지 않는다.
- 작업자는 `HF_HUB_OFFLINE=1` 로 돈다 — 받기는 서버의 「받기」 작업만 한다.
- GPU 선택은 설정(`allowed_gpus`, uuid)으로만. 코드에 카드 번호를 쓰지 않는다.
- 프로세스 정리는 PID 로만(`pkill -f`·이름 매칭 금지).
- push 는 사용자 지시가 있을 때만.

## 목소리 복제 동의

참조 세트를 만들 때 근거를 고르고 확인해야 한다: `self`(본인) · `other_consent`(당사자 동의) · `licensed`(사용권) · `synthetic`(합성 목소리).
근거·메모·시각을 세트와 각 결과의 참고 사본에 남긴다. WanAvatar `docs/voice-consent-design.md` 의 다사용자 설계(확인 문장 녹음·CER 판정)는
로컬 1인 설치에는 과하다고 보고 **기록만** 둔다 — 서비스형으로 열 때는 그 설계를 따른다.

## 라이선스

모델 관리 화면이 모델마다 라이선스와 상업 가능 여부를 보여 주고, 결과 기록에도 남긴다. 상업 불가: Higgs v3(Boson 연구) · Fish S2-Pro(Fish Audio Research) ·
X-Voice(CC BY-NC 4.0). 조건부: Drama 3(Fish Audio Community, 연매출 50만 달러까지). 확인 필요: SenseVoice·FSMN VAD(FunASR 모델 라이선스).

## 브라우저 시험 마크업 계약

- 화면마다 랜드마크(`header`·`nav`·`main`), 탭은 `nav` 안의 링크(접근 이름 = 화면 이름).
- 폼 입력은 모두 `label` 로 이름을 갖는다. 버튼은 보이는 글이 접근 이름이다.
- 오류는 `role="alert"`, 진행은 `role="progressbar"`(aria-valuenow).
- 명시적 시험 고리는 `data-testid` — 목록은 [ui-contract.md](ui-contract.md)(프론트가 정본). 구조 의존 선택자(nth-child 등)는 쓰지 않는다.
