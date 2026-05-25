# Rebuild Roadmap

## 목적

기존 구현은 `legacy/app_v1`로 두고,  
신규 개발은 `app/`를 기준으로 품질 중심 재구축을 진행한다.

## 원칙

1. PRD 불변조건을 테스트로 먼저 고정한다.
2. 불변조건 테스트가 없는 기능은 구현하지 않는다.
3. 루프 A/B/C 책임은 절대 섞지 않는다.
4. 설정 접근은 ConfigManager를 통해서만 한다.
5. 주문 실패 시 상태조회 없는 재시도는 금지한다.

## 현재 완료 (Phase 0)

- `app` 패키지 재구축 골격 구성
- PRD 핵심 불변조건 테스트 추가
  - 백테스트 N+1 시가
  - 주문 실패 후 상태조회 우선
  - 루프 책임 분리
  - Config read-only/범위 검증
- 코어 최소 구현
  - `app/core/config.py`
  - `app/core/rate_limited_client.py`
  - `app/orders/service.py`
  - `app/backtest/core.py`
  - `app/loops/core.py`

## 현재 완료 (Phase 1)

- 전용 DB 모델/세션/리포지토리 추가
  - `app/db/models/*`
  - `app/db/session.py`
  - `app/repositories/*`
- 코어 스키마 마이그레이션 추가
  - `alembic/versions/0004_add_rebuild_core_tables.py`
- 저장소 계층 테스트 추가
  - `tests/test_repositories_*.py`

## 현재 완료 (Phase 2)

- 주문 상태머신 구현
  - `app/orders/state_machine.py`
- 리스크 엔진 구현
  - `app/risk/engine.py`
- 루프 A 포지션/강제청산 판단 계층 분리
  - `app/loops/core.py` (`LoopAPositionManager`)
- 실행 서비스 추가
  - `app/services/trading_service.py`
- 테스트 추가
  - `tests/test_state_machine_phase2.py`
  - `tests/test_risk_engine_phase2.py`
  - `tests/test_loops_phase2.py`
  - `tests/test_trading_service_phase2.py`

## 현재 완료 (Phase 3)

- 키움 REST 통합 계층 추가
  - `app/integrations/kiwoom/client.py`
  - `app/integrations/kiwoom/gateway.py`
- 텔레그램 통합 계층 추가
  - `app/integrations/telegram/client.py`
- 서버시간 동기화 계층 추가
  - `app/core/time_sync.py`
- 레이트리밋 클라이언트 보강
  - 우선순위 큐 + 토큰 캐시 + 호환 enqueue 메서드
- 통합 테스트 추가
  - `tests/test_rate_limited_client_phase3.py`
  - `tests/test_kiwoom_client_phase3.py`
  - `tests/test_kiwoom_gateway_phase3.py`
  - `tests/test_telegram_client_phase3.py`
  - `tests/test_time_sync_phase3.py`

## 현재 완료 (Phase 4 - 기본 전략/명령 계층)

- 전략 1~5 기본 구현
  - `app/strategies/impl/*`
- 전략 레지스트리/타임프레임 스캔 계층 추가
  - `app/strategies/registry.py`
  - `app/loops/core.py` (`run_for_timeframe`)
- 텔레그램 명령 서비스 구현 (`/set`, `/confirm`, `/pause`, `/resume`, `/status`, `/settings`, `/close`)
  - `app/services/telegram_command_service.py`
  - `app/services/runtime_state.py`
- 설정/런타임 API 엔드포인트 추가
  - `app/main.py`
- 테스트 추가
  - `tests/test_strategies_phase4.py`
  - `tests/test_telegram_command_service_phase4.py`
  - `tests/test_api_runtime_phase4.py`

## 현재 완료 (Phase 5 - Trading Runtime 확장 1차)

- Loop B 봉 마감 스케줄 계층 추가
  - `app/loops/loop_b_runtime.py` (`MarketSchedule`, `LoopBRunner`)
- CandleRepository 연동 확장
  - 마지막 봉 시각 조회 `get_last_candle_time`
  - 최근 봉 로딩 `list_recent`
- Loop B 중복 슬롯 실행 방지(동일 봉 재처리 차단)
- 테스트 추가
  - `tests/test_loop_b_runtime_phase5.py`

## 다음 단계

### Phase 6: Trading Runtime 고도화

- Loop A 실시간 포지션 모니터링과 주문 실행 완전 통합
- 주문 실패 분기(조회 실패 시 정지/알림) 강화

## 현재 완료 (Phase 6 - Loop A 통합)

- Loop A 통합 런타임 추가
  - `app/loops/loop_a_runtime.py` (`LoopARunner`, `LoopAResult`)
- 시그널 소비 + 포지션 모니터링 + 청산 주문 + 상태전이 통합
- 저장소 전이 반영 메서드 추가
  - `app/repositories/ordering.py` (`apply_transition`)
- 테스트 추가
  - `tests/test_loop_a_runtime_phase6.py`

## 다음 단계

### Phase 7: 운영 안전장치 강화

- 주문 실패/조회 실패 시 시스템 정지 이벤트와 텔레그램 긴급 알림 연동
- Loop A/B/C 실행기 단일 런너로 묶고 런타임 헬스/지연 지표 추가

## 현재 완료 (Phase 7 - 운영 안전장치 1차)

- 런타임 안전관리 계층 추가
  - `app/services/runtime_safety.py` (`RuntimeSafetyManager`)
- RuntimeState 확장
  - `halted`, `halt_reason`, `halted_at`, `halt()` 지원
- 주문 실패/조회 실패 시 CRITICAL 이벤트 + 런타임 정지 연동
  - `app/orders/service.py`
  - `app/loops/loop_a_runtime.py`
- 런타임 상태 API에 정지 이벤트 노출
  - `app/main.py` (`/system/runtime`)
- 테스트 추가
  - `tests/test_runtime_safety_phase7.py`
  - `tests/test_order_safety_phase7.py`
  - `tests/test_loop_a_safety_phase7.py`

## 다음 단계

### Phase 8: 운영 가시성/지표 강화

- Loop A/B/C 단일 런너와 주기 실행기(헬스/지연 메트릭 포함) 추가
- 장애/정지 이벤트를 일일 리포트로 집계

## 현재 완료 (Phase 8 - 단일 런너/헬스 지표 1차)

- Loop A/B/C 단일 실행 코디네이터 추가
  - `app/services/loop_runtime.py` (`LoopRuntimeCoordinator`)
- 사이클 지표 추가
  - cycle count, duration(avg/max), error count, consecutive errors, lag, degraded
- Loop C 30분 슬롯 중복 실행 방지
- 런타임 API 확장
  - `POST /system/loops/run-cycle`
  - `GET /system/runtime`에 `loop_runtime` 지표 포함
- 테스트 추가
  - `tests/test_loop_runtime_phase8.py`
  - `tests/test_api_runtime_phase4.py` 확장

## 다음 단계

### Phase 9: 운영 자동 실행/리포트

- 루프 주기 실행(background task) + graceful stop/restart
- 일일 장애/정지 이벤트 리포트(텔레그램) 집계

## 현재 완료 (Phase 9 - 운영 자동 실행/리포트 1차)

- 백그라운드 주기 실행기 추가
  - `app/services/loop_background.py` (`LoopBackgroundRunner`)
- 루프 제어 API 추가
  - `POST /system/loops/start`
  - `POST /system/loops/stop`
- 일일 장애 리포트 서비스 추가
  - `app/services/daily_report.py` (`DailyIncidentReporter`)
  - `POST /system/reports/daily`
- RuntimeSafety 이벤트 일자 조회 지원
  - `app/services/runtime_safety.py` (`events_on`)
- 테스트 추가
  - `tests/test_loop_background_phase9.py`
  - `tests/test_daily_report_phase9.py`
  - `tests/test_api_runtime_phase4.py` 확장

## 다음 단계

### Phase 10: 실운영 완성도 향상

- Noop 루프를 실제 Loop A/B/C 실행기로 교체하는 DI 구성
- 장중/장종료 자동 보고 스케줄 정책 세분화

## 현재 완료 (Phase 10 - 실제 실행기 DI 교체 1차)

- 런타임 DI 팩토리 추가
  - `app/services/runtime_factory.py` (`build_runtime_bundle`)
- `main.py`에서 Noop 실행기 제거, 실제 Loop A/B/C 조합으로 교체
- 주문 게이트웨이 모드 분기 추가
  - `paper` 기본 + `live`(`TRADING_MODE` 기준)
  - `app/orders/paper_gateway.py`
- DB 기반 가격/ATR 제공자 추가
  - `DbPriceProvider`, `DbAtrProvider`
- 배경 루프 자동 시작 옵션 연동
  - `ENABLE_BACKGROUND_LOOPS=true` 시 startup 자동 시작
- 테스트 추가
  - `tests/test_runtime_factory_phase10.py`

## 다음 단계

### Phase 11: 실거래 데이터 연동 강화

- Kiwoom 캔들/현재가 fetcher를 Loop B/Loop A provider에 연결
- 유니버스 종목 공급자(활성/블록리스트 반영) 고도화

## 현재 완료 (Phase 11 - 실거래 데이터 연동 1차)

- Kiwoom 시장데이터 게이트웨이 추가
  - `app/integrations/kiwoom/market_data.py`
  - 현재가 조회 + 캔들 증분 파싱
- Runtime Factory live 분기 고도화
  - `LivePriceProvider`, `LiveCandleFetcher` 연결
  - `TRADING_MODE=live` 시 live adapter 사용
- 유니버스 저장소 추가
  - `app/db/models/universe.py`
  - `app/repositories/universe.py` (`list_runtime_tickers`)
- 런타임 티커 공급 순서 개선
  - active universe 우선 사용 (최초 실행 시 코스피200+코스닥150 자동 시드)
- 테스트 추가
  - `tests/test_kiwoom_market_data_phase11.py`
  - `tests/test_repositories_universe.py`
  - `tests/test_runtime_factory_phase10.py` 확장

## 다음 단계

### Phase 12: Live 운영 안정화

- Kiwoom 실응답 스키마 기준 endpoint/api-id/필드 매핑 정밀 보정
- 라이브 모드 모의연결 체크 및 장시간 soak 테스트

## 현재 완료 (Phase 12 - Live 운영 안정화 1차)

- Kiwoom 스키마 파서 유틸 추가
  - `app/integrations/kiwoom/schema.py`
- Order/MarketData adapter의 응답 파싱 내성 강화
  - nested `output/output1/output2`, 대체 필드키 대응
  - `app/integrations/kiwoom/gateway.py`
  - `app/integrations/kiwoom/market_data.py`
- 라이브 모의 연결 체크 추가
  - `run_live_connectivity_check` (`app/services/runtime_factory.py`)
  - `POST /system/live/connectivity-check`
- 다회 사이클 soak 테스트 추가
  - `tests/test_runtime_soak_phase12.py` (200 cycles)
- 테스트 추가
  - `tests/test_kiwoom_schema_phase12.py`
  - `tests/test_runtime_live_check_phase12.py`

## 다음 단계

### Phase 13: Live Preflight/운영 리허설

- 실제 키움 응답 샘플 캡처 기반 필드 맵 고정
- 장전/장중/장후 preflight 체크리스트 자동화

## 현재 완료 (Phase 13 - Preflight/운영 리허설 1차)

- Live preflight 서비스 추가
  - `app/services/live_preflight.py`
  - 필수 점검: live 모드, integrations enabled, runtime halt 상태, background loop, tickers, connectivity
- 운영 리허설 서비스 추가
  - preflight 통과 후 N회 cycle 실행 결과 집계
- API 추가
  - `POST /system/live/preflight`
  - `POST /system/live/rehearsal`
- 테스트 추가
  - `tests/test_live_preflight_phase13.py`
  - `tests/test_api_runtime_phase4.py` 확장

## 다음 단계

### Phase 14: 실응답 샘플 고정/회귀 자동화

- 키움 실제 응답 샘플(json fixtures) 수집 후 파서 회귀 테스트로 고정
- preflight stage별(장전/장중/장후) 정책 분리

## 현재 완료 (Phase 14 - 실응답 샘플/회귀 자동화 1차)

- 키움 실응답 fixture 추가
  - `tests/fixtures/kiwoom/*`
- fixture 기반 파서 회귀 테스트 추가
  - `tests/test_kiwoom_fixtures_phase14.py`
- preflight stage 정책 세분화
  - `pre_market`, `market`, `post_market` required check 분리
  - `app/services/live_preflight.py`
- 테스트 확장
  - `tests/test_live_preflight_phase13.py` 확장

## 다음 단계

### Phase 15: 성과 측정/페이퍼 합격 판정

- AccountSnapshot/CashFlow 저장 및 자동 입출금 감지(TWR 지원)
- `/paper_report` 기준(신호수/기간/승률/Sharpe/MDD/오류율/포지션불일치) 자동 판정

## 현재 완료 (Phase 15 - 성과/페이퍼 리포트 1차)

- 성과 데이터 모델/마이그레이션 추가
  - `app/db/models/performance.py`
  - `alembic/versions/0005_add_rebuild_performance_tables.py`
- 페이퍼 트레이드 모델 추가
  - `app/db/models/paper.py`
- 성과/페이퍼 리포지토리 추가
  - `app/repositories/performance.py`
  - `app/repositories/paper.py`
- 성과 서비스(TWR/현금흐름 감지) 추가
  - `app/services/performance.py`
- 페이퍼 합격 판정 서비스 추가
  - `app/services/paper_report.py`
- API/텔레그램 연동 추가
  - `POST /system/performance/snapshot`
  - `POST /system/performance/cash-flow`
  - `POST /system/performance/cash-flow/detect`
  - `GET /system/performance/twr`
  - `GET /paper_report`
  - `/telegram/command`의 `/report`, `/paper_report` 지원
- 테스트 추가
  - `tests/test_repositories_performance_phase15.py`
  - `tests/test_performance_service_phase15.py`
  - `tests/test_paper_report_phase15.py`
  - `tests/test_api_runtime_phase4.py` 확장
  - `tests/test_telegram_command_service_phase4.py` 확장

## 다음 단계

### Phase 16: 백테스트 비동기 실행/웹 대시보드 고도화

- 백테스트 job id/진행률/완료 알림 플로우 구현
- 대시보드용 성과/설정/유니버스 조회 API 정리

## 현재 완료 (Phase 16 - 백테스트 Job/대시보드 API 1차)

- 백테스트 비동기 Job 서비스 추가
  - `app/services/backtest_jobs.py`
  - job 상태: `queued/running/completed/failed`
  - 진행률/결과/오류 조회 지원
  - 완료/실패 시 텔레그램 알림 훅 지원
- 백테스트 API 추가
  - `POST /system/backtest/run`
  - `GET /system/backtest/jobs`
  - `GET /system/backtest/jobs/{job_id}`
- 유니버스 대시보드 API 1차 추가
  - `GET /system/universe`
  - `POST /system/universe/upsert`
  - `POST /system/universe/{ticker}/block`
- 유니버스 저장소 확장
  - `app/repositories/universe.py` (`list_symbols`, `set_blocked`)
- 테스트 추가/확장
  - `tests/test_backtest_jobs_phase16.py`
  - `tests/test_api_runtime_phase4.py` 확장
  - `tests/test_repositories_universe.py` 확장

## 다음 단계

### Phase 17: 대시보드/운영 완성도 2차

- 백테스트 성과 지표(Sharpe/MDD/EV) 상세 계산 고도화
- 대시보드용 조회 API 정규화(필터/페이징/기간 쿼리)
- 운영 알림 템플릿(일일/주간) 정리

## 현재 완료 (Phase 17 - 대시보드/운영 완성도 2차)

- 백테스트 지표 고도화
  - `app/services/backtest_jobs.py`
  - `expectancy`, `expectancy_r`, `sharpe_ratio`, `mdd`, `profit_factor` 추가
- 백테스트 job 조회 API 정규화
  - `GET /system/backtest/jobs`에 `status`, `offset`, `limit` 필터 지원
- 성과 조회 API 정규화
  - `GET /system/performance/snapshots` (기간/타입/페이징)
  - `GET /system/performance/cash-flows` (기간/감지타입/페이징)
  - `app/services/performance.py`, `app/repositories/performance.py` 확장
- 유니버스 조회 API 정규화
  - `GET /system/universe`에 market/active/blocked/status/query/페이징 필터 추가
  - `app/repositories/universe.py` 필터 지원 확장
- 운영 리포트 템플릿 확장
  - `app/services/daily_report.py`
  - 주간 템플릿/주간 1회 발송 제어 추가
  - `POST /system/reports/weekly` 추가
- 테스트 추가/확장
  - `tests/test_backtest_jobs_phase16.py` 확장
  - `tests/test_daily_report_phase9.py` 확장
  - `tests/test_performance_service_phase15.py` 확장
  - `tests/test_repositories_universe.py` 확장
  - `tests/test_api_runtime_phase4.py` 확장

## 다음 단계

### Phase 18: 웹 대시보드 UI/인증(OTP) 1차

- PRD 11장 기준 OTP 로그인 플로우 구현
- 핵심 대시보드 화면용 API 응답 스키마 안정화
- 조회 API의 총개수/페이지 메타 제공

## 현재 완료 (Phase 18 - 웹 대시보드 인증/API 1차)

- OTP 인증 플로우 구현
  - `app/services/auth.py`
  - 4자리 OTP, 3분 만료, IP당 분당 3회 요청 제한 + 10분 lock, 24시간 세션 쿠키
  - OTP 오입력 경고 텔레그램 알림 훅
- 인증 API 추가
  - `POST /auth/otp/request`
  - `POST /auth/otp/verify`
  - `GET /auth/session`
  - `POST /auth/logout`
- 대시보드 세션 보호 API 추가
  - `GET /dashboard/summary`
  - `GET /dashboard/backtests`
  - `GET /dashboard/universe`
  - `GET /dashboard/performance/snapshots`
- 조회 API 메타(total/offset/limit/page) 확장
  - `GET /system/backtest/jobs`
  - `GET /system/universe`
  - `GET /system/performance/snapshots`
  - `GET /system/performance/cash-flows`
- 테스트 추가/확장
  - `tests/test_auth_phase18.py`
  - `tests/test_dashboard_api_phase18.py`
  - 기존 API/서비스 테스트 회귀 통과

## 다음 단계

### Phase 19: 대시보드 UI/운영 자동화 2차

- PRD 11장 OTP 로그인 화면/세션 UX 구현
- 대시보드 핵심 화면(에쿼티/포지션/전략성과/설정이력) 1차 UI
- 정기 자동 백테스트 스케줄(루프C 연계) 초안 구현

## 현재 완료 (Phase 19 - 대시보드 UI/운영 자동화 2차)

- OTP 로그인 UI/세션 UX 1차 구현
  - `GET /dashboard/login` (OTP 요청/검증 화면)
  - `GET /dashboard/app` (세션 인증 후 대시보드 화면)
  - 미인증 접근 시 로그인 페이지로 리다이렉트
- 대시보드 UI 데이터 연동
  - 요약(runtime/TWR/paper pass) + 최근 백테스트/유니버스 표시
  - `data/meta` 응답 스키마 유지
- 자동 백테스트 스케줄러(Loop C 연계) 추가
  - `app/services/backtest_scheduler.py`
  - 장 마감 시간 이후 일 1회 자동 trigger (옵션)
  - `RuntimeMaintenanceService.after_aggregate` 훅으로 Loop C에서 실행
  - 상태/수동 실행 API:
    - `GET /system/backtest/auto/status`
    - `POST /system/backtest/auto/run-now`
- 설정 추가
  - `ENABLE_AUTO_BACKTEST`
  - `AUTO_BACKTEST_RUN_HOUR`
- 테스트 추가/확장
  - `tests/test_backtest_scheduler_phase19.py`
  - `tests/test_dashboard_api_phase18.py` 확장
  - `tests/test_api_runtime_phase4.py` 확장

## 다음 단계

### Phase 20: 대시보드 기능 확장 3차

- 포지션/전략성과/설정이력 카드 UI 및 대응 API 연결
- OTP 보안 정책 강화(로그인 실패 누적 잠금/알림 문구 세분화)
- 자동 백테스트 결과를 일일/주간 리포트에 통합

## 현재 완료 (Phase 20 - 대시보드 기능 확장 1차)

- 대시보드 API 확장
  - `GET /dashboard/positions`
  - `GET /dashboard/settings/history`
  - 기존 대시보드 API와 동일한 `data/meta` 스키마 적용
- 저장소 확장
  - `app/repositories/ordering.py` (`list_positions`, `count_positions`)
  - `app/repositories/config.py` (`list_history`, `count_history`)
- 자동 백테스트 스케줄러 완성도 보강
  - `app/services/backtest_scheduler.py`
  - 상태 조회/수동 실행 API (`/system/backtest/auto/*`) 연동
- 대시보드 무DB(degraded) 안전성 보강
  - DB 연결 실패 시 예외 전파 대신 `ok=false` 응답 유지
- 테스트 추가/확장
  - `tests/test_repositories_ordering.py` 확장
  - `tests/test_repositories_config.py` 확장
  - `tests/test_dashboard_api_phase18.py` 확장
  - 전체 회귀 통과

## 다음 단계

### Phase 21: 대시보드/운영 고도화 4차

- 전략 성과 카드(승률/손익비/기대값) 모델링 및 API
- OTP 실패 누적 잠금 정책(요청 제한 외 검증 실패 누적) 추가
- 자동 백테스트 결과를 일일/주간 리포트 본문에 통합

## 현재 완료 (Phase 21 - 대시보드/운영 고도화 4차)

- 전략 성과 카드 모델/API 추가
  - `app/services/strategy_performance.py`
  - `GET /dashboard/strategy-performance`
  - 전략별 승률/손익비(payoff_ratio)/기대값(expectancy)/profit_factor 집계
- OTP 검증 실패 누적 잠금 추가
  - `app/services/auth.py`
  - 요청 제한과 별도로 검증 실패 누적 시 `otp_verify_locked` 처리
- 자동 백테스트 결과 리포트 통합
  - `app/services/backtest_scheduler.py`에 job 완료 스냅샷 추적 추가
  - `app/services/daily_report.py`에 auto backtest 섹션 추가
  - 일일/주간 리포트 본문에 최근 자동 백테스트 결과 표시
- 데이터 모델/스키마 정합성 보강
  - `paper_trades.strategy_id` 반영
  - `alembic/versions/0006_add_strategy_id_to_paper_trades.py`
- 테스트 추가/확장
  - `tests/test_strategy_performance_phase21.py`
  - `tests/test_auth_phase18.py` 확장
  - `tests/test_daily_report_phase9.py` 확장
  - `tests/test_backtest_scheduler_phase19.py` 확장
  - `tests/test_dashboard_api_phase18.py` 확장

## 다음 단계

### Phase 22: 대시보드 UI/운영 고도화 5차

- 전략 성과 카드 UI(정렬/필터/기간) 추가
- OTP 잠금 상태 UX 메시지/해제 가이드 강화
- 리포트 템플릿(일/주)에 전략 성과 Top/Bottom 자동 요약 추가

## 현재 완료 (Phase 22 - 대시보드 UI/운영 고도화 5차)

- 전략 성과 UI/필터/정렬 확장
  - `GET /dashboard/strategy-performance`에 기간/전략ID/query/min_trades/sort 파라미터 지원
  - `app/services/strategy_performance.py` 정렬/필터 로직 확장
  - `/dashboard/app` 전략 성과 카드에 필터/정렬 입력 UI 추가
- OTP 잠금 UX 메시지 강화
  - `/dashboard/login`에서 오류코드별 사용자 안내문구 제공
  - `otp_verify_locked`, 요청 제한, 만료/불일치 케이스 분기 안내
- 리포트 전략 요약 추가
  - `app/services/daily_report.py`에 전략 Top/Bottom 요약 섹션 추가
  - 자동 백테스트 요약 + 전략 요약이 일/주 리포트 본문에 함께 포함
- 데이터 모델/마이그레이션 보강
  - `paper_trades.strategy_id` 반영
  - `alembic/versions/0006_add_strategy_id_to_paper_trades.py`
- 테스트 추가/확장
  - `tests/test_strategy_performance_phase21.py` 확장
  - `tests/test_daily_report_phase9.py` 확장
  - `tests/test_auth_phase18.py` 확장
  - `tests/test_dashboard_api_phase18.py` 확장
  - 전체 회귀 통과

## 다음 단계

### Phase 23: 운영 품질 고도화 6차

- OTP 인증/세션 감사 로그(요청/실패/잠금/해제) 이벤트 저장
- 대시보드 전략 성과 표 렌더링(숫자 포맷/하이라이트/정렬 상태 표시)
- 자동 백테스트 요약을 텔레그램 명령(`/report`, `/paper_report`)에도 연결

## 현재 완료 (Phase 23 - 운영 품질 고도화 6차)

- OTP 인증/세션 감사 로그 저장 및 조회
  - `app/db/models/auth_audit.py`
  - `alembic/versions/0007_add_auth_audit_logs.py`
  - `app/services/auth.py` 감사 포인트 연계
  - `GET /dashboard/auth/audit` 추가
- OTP 잠금 해제 이벤트 로깅 보강
  - 요청 제한 잠금 해제: `otp_request_unlocked`
  - 검증 실패 잠금 해제: `otp_verify_unlocked`
- 대시보드 전략 성과 표 렌더링 개선
  - 숫자 포맷/양음수 하이라이트/정렬 상태 표시
  - 필터(기간/쿼리/최소 거래수) + 정렬 입력 유지
- 텔레그램 명령 리포트 확장
  - `/report` 결과에 자동 백테스트 상태 요약 추가
  - `/paper_report` 결과에 자동 백테스트 상태 요약 추가
- 테스트 추가/확장
  - `tests/test_auth_phase18.py` 확장
  - `tests/test_dashboard_api_phase18.py` 확장
  - `tests/test_telegram_command_service_phase4.py` 확장
  - 전체 회귀 통과 (`104 passed`)

## 다음 단계

### Phase 24: 운영 안정성/관측 강화 7차

- 인증/세션 감사 대시보드 카드(최근 실패율, 잠금 건수) 추가
- 필수 로깅 포인트(PRD 13.3) 커버리지 매트릭스와 테스트 고정
- 텔레그램 `/status` 출력에 백그라운드 루프/자동 백테스트 요약 통합

## 현재 완료 (Phase 24 - 운영 안정성/관측 강화 7차)

- 인증/세션 감사 지표 대시보드 카드 추가
  - `GET /dashboard/auth/metrics?last_hours=24`
  - 최근 구간 실패율/잠금/해제 건수 집계 반환
  - `/dashboard/app`에 Auth Audit 카드 연동
- PRD 13.3 로깅 커버리지 매트릭스 고정
  - `app/core/logging_coverage.py`
  - `docs/logging-coverage-matrix.md`
  - `tests/test_logging_coverage_phase24.py`
- 텔레그램 `/status` 출력 확장
  - 루프 실행 여부/사이클 수/최근 소요시간 포함
  - 자동 백테스트 상태/최근 job id 포함
- 테스트 추가/확장
  - `tests/test_telegram_command_service_phase4.py` 확장
  - `tests/test_dashboard_api_phase18.py` 확장
  - 전체 회귀 통과 (`108 passed`)

## 다음 단계

### Phase 25: 운영 관측 완성 8차

- Auth audit 대시보드 필터 UI(이벤트 타입/IP/성공여부/기간) 추가
- `/dashboard/auth/audit` 결과를 표 렌더링으로 전환(페이지네이션/정렬)
- `/status` 명령에 당일 리스크 핵심 지표(critical count, halted_at) 추가

## 적용 규칙

- 신규 기능은 `app/` 하위에만 추가
- `legacy/`는 참조 전용(수정 금지)
