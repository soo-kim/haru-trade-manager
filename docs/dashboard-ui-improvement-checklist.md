# Dashboard UI 보완 계획 (체크리스트)

작성일: 2026-04-13  
대상: `app/main.py` 기반 대시보드/로그인 UI, 설정/백테스트/유니버스 표시, `Makefile`

## 1) 이슈 파악 요약

현재 대시보드 HTML/CSS/JS가 `app/main.py` 문자열에 직접 포함되어 있어 유지보수성이 낮고, 일부 화면은 UX/정보 구조가 불균형하다.

- 로그인/대시보드 HTML이 `app/main.py` 내부 문자열로 존재
- 로그인 버튼 텍스트가 `OTP 검증`으로 노출
- 설정값 섹션이 키 중심 + 컬럼 과다 + 엔터 저장 미지원
- 설정값 섹션만 입력 UI 스타일이 다른 섹션과 불일치
- 설정 변경 이력 카드 크기/필터 라벨 UX가 과도
- 백테스트 결과가 JSON raw 위주로만 노출
- 유니버스 `status`가 코드값 그대로 표시됨
- `Makefile`의 `start`가 항상 `--build`를 수행해 비효율적이고 로그 확인 타깃 부재

## 2) 보완 목표

- `main.py`에서 UI 템플릿/정적 자산을 분리해 변경 영향 범위를 축소한다.
- 설정/백테스트/유니버스 정보를 “운영자가 바로 이해 가능한 화면”으로 재구성한다.
- 대시보드 입력 폼 스타일을 일관화한다.
- 실행/운영 편의(`make` 타깃)를 개선한다.

## 3) 구현 원칙

- 트레이딩 도메인 로직(루프 A/B/C, 주문 처리, 백테스트 체결 규칙)은 건드리지 않고 UI/API 표현 계층 중심으로 수정한다.
- 설정 수정 경로는 계속 `ConfigManager`/`ConfigService`를 사용한다.
- 유니버스 상태 enum 도입 시 기존 저장값과 호환되는 점진적 방식으로 진행한다.

## 4) 작업 체크리스트

### A. 템플릿 분리 + 로그인 UX

- [ ] `app/main.py`의 `_dashboard_login_html`, `_dashboard_app_html`를 파일 기반 템플릿으로 분리
- [ ] CSS/JS를 정적 파일로 분리해 HTML diff 가시성 확보
- [ ] 로그인 버튼 텍스트를 `OTP 검증` -> `인증`으로 변경
- [ ] OTP 입력 폼의 `autocomplete` 비활성화 상태 유지 확인
- [ ] 기존 `/dashboard/login`, `/dashboard/app` 라우트 응답/리다이렉트 동작 회귀 테스트

### B. 설정값 현황/변경 UI 재설계

- [ ] 카드 레이아웃을 `card span-8`로 조정
- [ ] 한 줄에 설정 항목 2개씩 보이도록 그리드화(모바일은 1열)
- [ ] 키 옆에 “항목 설명(의미)” 노출
- [ ] `값`, `속성`, `액션` 컬럼 제거
- [ ] `수정값` 입력에서 Enter 키로 저장 가능하도록 처리
- [ ] 저장 전 확인 다이얼로그는 유지
- [ ] 설정 섹션 입력 스타일을 다른 `.row input/select/textarea` 규칙과 통일

### C. 설정 변경 이력 UI 조정

- [ ] 카드 레이아웃을 `card span-4`로 조정
- [ ] `설정 키 필터` 라벨 제거 (플레이스홀더/aria-label로 대체)
- [ ] 필터 입력 후 Enter로 조회 가능하도록 이벤트 처리
- [ ] 조회 버튼은 유지 여부를 최종 UX 확인 후 결정

### D. 백테스트 결과 가독성 개선

- [ ] `JSON raw` 단일 표시 대신 표/요약 카드 중심으로 렌더링
- [ ] 최소 표시 항목: 작업시각, 상태, 전략, 종목, 캔들수, 신호수, 에러 요약
- [ ] 상태(`queued/running/completed/failed`) 배지 색상 통일
- [ ] 필요 시 “원본 JSON 보기” 토글로 디버그 정보 제공

### E. 유니버스 상태 enum + 한국어 표시

- [ ] 상태 코드 enum 정의 (`normal`, `exit_pending`, `removed`, `halted`)
- [ ] API 응답에 상태 코드 + 한국어 라벨(`status_label_ko`) 제공
- [ ] UI 테이블은 한국어 라벨 기준 표시
- [ ] 미정의 상태값 fallback(`알 수 없음(<raw>)`) 처리
- [ ] 유니버스 리밸런싱/조회 동작에 대한 회귀 테스트

### F. Makefile 운영 편의 개선

- [ ] `make start`는 재빌드 없이 기동(`docker compose up -d`)으로 변경
- [ ] 빌드 포함 기동은 별도 타깃(`start-build`)로 분리
- [ ] 로그 확인 타깃 추가 (`logs`, `logs-follow` 등)
- [ ] `help` 출력에 신규 타깃 설명 반영

## 5) API/모델 보완 체크리스트

- [ ] `/dashboard/settings` 응답에 항목 설명 필드 추가 (`description` 또는 `label`)
- [ ] 설정 설명 메타데이터의 단일 소스는 `ConfigManager` 인접 계층에 정의
- [ ] `/dashboard/universe` 응답에 상태 라벨 필드 추가
- [ ] 기존 클라이언트와의 하위호환(기존 `status` 필드 유지) 보장

## 6) 테스트 체크리스트

- [ ] `tests/test_dashboard_api_phase18.py` 회귀 통과
- [ ] `tests/test_dashboard_product_phase26.py` 회귀 통과
- [ ] 신규 UI 계약 테스트 추가
- [ ] 설정 Enter 저장 키보드 이벤트 동작 수동 점검
- [ ] 모바일 폭(<=1080px)에서 1열 전환 수동 점검
- [ ] `make help`, `make start`, `make start-build`, `make logs` 동작 점검

## 7) 완료 기준 (Definition of Done)

- [ ] `main.py`에서 대시보드/로그인 대형 HTML 문자열 제거 완료
- [ ] 설정값 섹션이 `span-8`, 이력 섹션이 `span-4`로 재배치 완료
- [ ] 설정값 섹션에서 항목 의미 설명 + Enter 저장 동작 확인
- [ ] 백테스트 결과가 비JSON 기본 화면으로 가독성 확보
- [ ] 유니버스 상태가 enum 기반 한국어 라벨로 표시
- [ ] `Makefile`에 로그 조회/재빌드 없는 시작 플로우 추가

## 8) 예상 변경 파일

- `app/main.py`
- `app/core/config.py` (설정 메타데이터 확장 시)
- `app/repositories/universe.py` (필요 시 enum 검증 반영)
- `app/db/models/universe.py` (enum/제약 확장 선택 시)
- `Makefile`
- `tests/test_dashboard_api_phase18.py`
- `tests/test_dashboard_product_phase26.py`
- 신규 템플릿/정적 파일 디렉토리 (예: `app/web/templates`, `app/web/static`)

## 9) 의사결정 필요 항목

- [ ] 대시보드 템플릿 엔진 사용 여부
  - 권장: 우선 정적 파일 분리(의존성 추가 없이), 이후 필요 시 템플릿 엔진 전환
- [ ] 설정 변경 이력의 조회 버튼 유지 여부
  - 권장: Enter 조회 + 버튼 병행(접근성/명시성 확보)
