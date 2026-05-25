# Haru Trade Manager

PRD 기반 자동매매 시스템 재구축 저장소입니다.

## Quick Start

1. Python 3.14+
2. `python3 -m pip install -e ".[dev]"`
3. `cp .env.example .env`
4. `uvicorn app.main:app --reload`

## DB Migration

- `make migrate` 또는 `alembic upgrade head`

## 구현 상태 (현재)

- `app/` 기준 신규 구현
- ConfigManager (검증/읽기 전용 키 보호/전략 오버라이드 검증)
- RateLimitedClient (0.2초 간격, 우선순위 큐, 토큰 캐시)
- PostgreSQL 전용 SQLAlchemy/Alembic 구성
- 핵심 테이블:
  - `rebuild_config`, `rebuild_config_history`
  - `rebuild_candles`
  - `rebuild_signals`, `rebuild_orders`, `rebuild_positions`
  - `rebuild_account_snapshots`, `rebuild_cash_flows`
  - `paper_portfolio`, `paper_orders`, `paper_trades`
- 주문 상태 재조회 기반 재시도 (`OrderService`)
- 포지션 상태머신 (`OPEN -> HALF_CLOSED -> CLOSED`)
- 리스크 엔진 (ATR, 한도, 15:20 우선순위 강제청산 계산)
- 루프 A/B/C 책임 분리 스켈레톤
- Loop B 봉마감 스케줄 + 캔들 증분 동기화 런타임
- Loop A 시그널 소비 + 포지션 모니터링 + 상태전이 + 청산 주문 통합 런타임
- 전략 1~5 기본 구현 + 전략 레지스트리
- 키움 REST 클라이언트/게이트웨이 + 서버시간 동기화 서비스
- 텔레그램 알림 클라이언트
- 텔레그램 명령 서비스 (`/set`, `/confirm`, `/pause`, `/resume`, `/status`, `/settings`, `/close`, `/report`, `/paper_report`)
- 런타임 상태/설정 API
- 주문 실패/조회 실패 시 런타임 정지 + CRITICAL 이벤트 기록 + 텔레그램 긴급 알림 훅
- Loop A/B/C 단일 런너 + 사이클 헬스 지표(지연/오류/성능)
- 백그라운드 루프 start/stop 제어 + 일일 장애 리포트 전송 API
- 런타임 DI 팩토리로 실제 Loop A/B/C 조합 연결 (Noop 제거)
- 주문 게이트웨이 `paper|live` 분기 (`TRADING_MODE`)
- Kiwoom 시장데이터 게이트웨이(현재가/캔들 증분) 연결
- 유니버스 기반 티커 공급(active/blocked 반영)
- 최초 실행 시 코스피200+코스닥150(총 350) 자동 유니버스 시드
- Kiwoom 응답 스키마 다중 포맷 파서(`output/output1/output2`) 적용
- Live preflight 체크리스트 + 운영 리허설(cycle dry-run) API
- 성과 측정(TWR)용 스냅샷/입출금 기록 + 자동 입출금 감지
- 페이퍼 트레이딩 합격 판정(`/paper_report`) 서비스
- 백테스트 비동기 실행(Job ID/진행률/결과 + Sharpe/MDD/EV 지표) API
- 유니버스/성과 조회 API 필터/페이징 지원
- 운영 리포트 일일/주간 템플릿 + 주간 리포트 API
- OTP 기반 인증(요청/검증/세션/로그아웃) API
- 대시보드 세션 보호 API 스키마(`data`/`meta`) 1차
- OTP 로그인 페이지/대시보드 페이지(HTML) 1차
- Loop C 연계 자동 백테스트 스케줄러(일 1회, 옵션)
- 대시보드 포지션/설정이력 API 1차
- 대시보드 전략 성과 카드 API(승률/손익비/기대값)
- OTP 검증 실패 누적 잠금 + 리포트 내 자동 백테스트 결과 요약
- 전략 성과 카드 정렬/필터/기간 UI + 리포트 Top/Bottom 전략 요약
- OTP 인증/세션 감사 로그 저장 + 대시보드 조회 API (`/dashboard/auth/audit`)
- 텔레그램 `/report`, `/paper_report` 자동 백테스트 상태 요약 연동
- 텔레그램 `/status`에 루프 실행/사이클/자동 백테스트 요약 통합
- 인증 감사 24시간 지표 API (`/dashboard/auth/metrics`) + 대시보드 카드
- PRD 13.3 로깅 커버리지 매트릭스 + 고정 테스트

## API

- `GET /healthz`
- `POST /auth/otp/request`
- `POST /auth/otp/verify`
- `GET /auth/session`
- `POST /auth/logout`
- `GET /config`
- `POST /config`
- `GET /system/runtime`
- `POST /system/loops/run-cycle`
- `POST /system/loops/start`
- `POST /system/loops/stop`
- `POST /system/reports/daily`
- `POST /system/reports/weekly`
- `POST /system/live/connectivity-check`
- `POST /system/live/preflight`
- `POST /system/live/rehearsal`
- `POST /system/performance/snapshot`
- `POST /system/performance/cash-flow`
- `POST /system/performance/cash-flow/detect`
- `GET /system/performance/snapshots`
- `GET /system/performance/cash-flows`
- `GET /system/performance/twr`
- `GET /paper_report`
- `POST /system/backtest/run`
- `GET /system/backtest/jobs`
- `GET /system/backtest/jobs/{job_id}`
- `GET /system/backtest/auto/status`
- `POST /system/backtest/auto/run-now`
- `GET /system/universe`
- `POST /system/universe/upsert`
- `POST /system/universe/{ticker}/block`
- `GET /dashboard/summary`
- `GET /dashboard/backtests`
- `GET /dashboard/universe`
- `GET /dashboard/performance/snapshots`
- `GET /dashboard/login`
- `GET /dashboard/app`
- `GET /dashboard/positions`
- `GET /dashboard/settings/history`
- `GET /dashboard/strategy-performance`
- `GET /dashboard/auth/audit`
- `GET /dashboard/auth/metrics`
- `POST /telegram/command`

## 주요 환경변수

- `ENABLE_BACKGROUND_LOOPS` (`true|false`): 앱 시작 시 백그라운드 루프 자동 시작
- `TRADING_MODE` (`paper|live`): 주문 게이트웨이 모드
- `ENABLE_AUTO_BACKTEST` (`true|false`): Loop C 주기에서 자동 백테스트 실행 여부
- `AUTO_BACKTEST_RUN_HOUR` (`0~23`): 자동 백테스트 실행 기준 시각(UTC hour)

## 테스트

- `make test`
- 현재 테스트 통과: `111 passed`

## 재구축 상태

- 신규 재구축 코드는 `app/` 기준으로 진행합니다.
- 이전 구현은 `legacy/app_v1` 및 `legacy/tests_v1`에 보존되어 있습니다.
- 로드맵: [docs/rebuild-roadmap.md](/Users/soo/Dropbox/git/haru-trade-manager/docs/rebuild-roadmap.md)
