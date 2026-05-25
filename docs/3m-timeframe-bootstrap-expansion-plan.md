# 3분봉 추가 + 초기 캔들 부트스트랩 확장 계획

작성일: 2026-04-13  
대상: 캔들 수집(초기/증분), 백테스트, Loop B 실시간 전략 실행

## 1) 배경

현재 대시보드의 백테스트 기간 조회에서 보이는 캔들 개수(예: 1d/15m/60m=160, 5m=320)는 키움 응답 한계가 아니라, **초기 부트스트랩에서 저장 시 cap으로 잘라 넣는 로직** 때문에 발생한다.

또한 3분봉(`3m`)은 현재 시스템 전반에서 1급 타임프레임으로 연결되어 있지 않다.

## 2) 현재 상태 요약 (코드 기준)

- 초기 부트스트랩 상한:
  - `("1d", 160), ("5m", 320), ("15m", 160), ("60m", 160)`
  - 위치: `app/main.py`의 `_INITIAL_BOOTSTRAP_TIMEFRAME_LIMITS`
- 부트스트랩 저장 시 cap 적용:
  - `selected = candles[-cap:] if len(candles) > cap else candles`
  - 위치: `app/main.py`의 `_bootstrap_candles_on_first_run`
- 백테스트 캔들 범위 API는 DB 저장량을 그대로 반환:
  - `/dashboard/backtests/candle-range`
  - 위치: `app/main.py`
- 키움 분봉 요청 매핑:
  - `minute_map = {"5m": "5", "15m": "15", "60m": "60"}`
  - 위치: `app/integrations/kiwoom/market_data.py`
- Loop B 실행 슬롯:
  - 5분/15분/60분/일봉만 스케줄링
  - 위치: `app/loops/loop_b_runtime.py`
- 백테스트 UI 타임프레임 선택:
  - `5m/15m/60m/1d`
  - 위치: `app/web/templates/dashboard_app.html`

## 3) 목표

1. **초기 부트스트랩은 cap 없이 수신한 캔들을 모두 저장**한다.  
2. **3분봉을 백테스트와 실시간 전략 실행(Loop B) 모두에서 지원**한다.  
3. 전략 실행 안정성을 위해, 타임프레임 추가로 인한 호출량/신호량 증가를 통제 가능한 형태로 도입한다.

## 4) 핵심 설계 결정

### A. 부트스트랩 cap 정책

- 기존 cap(`160/320`) 제거
- 초기 부트스트랩에서는 수신한 전체 증분 데이터를 `upsert_batch`로 저장
- 필요 시 운영 보호를 위해 “절대 상한(안전 가드)”만 별도 상수로 두되, 기본은 비활성

### B. 3분봉 지원 범위

- 데이터 계층: `3m` 수집/저장/조회 지원
- 백테스트 계층: 수동 백테스트 및 candle-range 조회에서 `3m` 사용 가능
- 실행 계층(Loop B): 3분 슬롯에서 스캔/시그널 생성 가능

### C. 런타임 전략 연결 방식

- 원칙: “백테스트만 3m”가 아니라 “실행도 3m”를 반영
- 1차 계획(권장): 기존 5분 전략(1/3/4)을 **3분으로 전환 가능하도록 구성**
- 주의: 동일 `strategy_id`를 다중 타임프레임에서 동시 실행하면 포지션/우선순위 해석이 모호해질 수 있음
- 따라서 1차 릴리스는 “전략별 단일 실행 타임프레임” 원칙으로 운영 (동시 3m+5m는 후속 확장 항목)

## 5) 구현 체크리스트

### 5.1 초기 부트스트랩 cap 제거

- [x] `app/main.py`의 `_INITIAL_BOOTSTRAP_TIMEFRAMES` 구조를 cap 없는 타임프레임 목록으로 변경
- [x] `_bootstrap_candles_on_first_run`에서 `selected = candles[-cap:] ...` 제거
- [x] 부트스트랩 상태 메시지에 timeframe별 insert/update 수량을 남기도록 보강(관찰성)
- [ ] 대량 최초 적재 시 처리 시간/메모리 리스크 점검

### 5.2 3분봉 데이터 수집/조회 추가

- [x] `KiwoomMarketDataGateway`의 minute map에 `3m -> "3"` 추가
- [x] 미지원 timeframe 요청 시 묵시적 `5m` fallback 금지(명시적 에러 처리)
- [x] candle-range API 입력 타임프레임 검증 목록에 `3m` 포함
- [x] 관련 단위 테스트 보강

### 5.3 백테스트(수동) 3분봉 추가

- [x] 대시보드 백테스트 타임프레임 select에 `3m` 옵션 추가
- [x] 수동 백테스트 API(`manual-run`)에서 `3m` 정상 처리 확인
- [x] 백테스트 결과 표기(현재 대시보드 표)의 timeframe 컬럼에 `3m` 반영 확인

### 5.4 Loop B 실시간 실행 3분봉 추가

- [x] `MarketSchedule.due_timeframes`에 3분 슬롯(`mm % 3 == 0`) 추가
- [x] `slot_key`에 `3m` 버킷 처리 추가
- [x] Loop B 동작 테스트(중복 슬롯 방지 포함) 보강
- [x] 기존 5m/15m/60m/1d와 충돌 없이 동작하는지 회귀 확인

### 5.5 전략 실행 타임프레임 정렬

- [x] 3분봉 실행 대상 전략(기존 5분 전략 1/3/4) 적용 방식 확정
- [x] `StrategyRegistry` 초기화 구성 조정 (전략별 실행 timeframe 명시)
- [x] 전략 성과/포지션 표시 시 timeframe 변화가 해석 가능하도록 점검
- [ ] 운영 중 신호량 급증 시 보호 정책(예: max_positions/risk_per_trade_pct) 점검

## 6) 테스트 계획

### 단위/통합

- [x] `tests/test_kiwoom_market_data_phase11.py`에 `3m` payload 검증 추가 (`tic_scope="3"`)
- [x] `tests/test_loop_b_runtime_phase5.py`에 3분 슬롯 시나리오 추가
- [x] 대시보드 백테스트 엔드포인트 테스트에 `3m` 케이스 추가
- [x] cap 제거 후 부트스트랩 관련 테스트/픽스처 업데이트

### 수동 검증

- [ ] 최초 기동 후 `dashboard/backtests/candle-range`에서 기존 cap 숫자 고정 현상 해소 확인
- [ ] 3분봉 candle-range 조회 가능 확인
- [ ] 3분봉 수동 백테스트 실행 및 결과 생성 확인
- [ ] Loop B 주기 실행 로그에서 3분 슬롯 처리 확인

## 7) 리스크 및 대응

- 데이터량 증가:
  - 대응: 초기 부트스트랩 실행 시간 모니터링, 필요 시 배치 커밋/로그 보강
- API 호출량 증가(3분 주기):
  - 대응: 레이트리밋 설정/실패 재시도 정책 점검
- 신호량 증가로 인한 포지션 과밀:
  - 대응: 리스크 엔진 설정(`max_positions`, `risk_per_trade_pct`) 사전 점검
- 전략 타임프레임 혼합에 따른 해석 혼선:
  - 대응: 1차 릴리스에서 전략별 단일 실행 타임프레임 원칙 유지

## 8) 완료 기준 (DoD)

- [x] 초기 부트스트랩에서 cap 절단 없이 수신 데이터 전체가 저장된다.
- [x] 대시보드 백테스트에서 `3m` 선택/조회/실행이 동작한다.
- [x] Loop B가 3분 슬롯에서 실시간 스캔을 수행한다.
- [x] 변경 범위 관련 테스트가 모두 통과한다.
- [ ] 운영 로그/대시보드에서 변경 효과를 확인할 수 있다.

## 9) 예상 변경 파일

- `app/main.py`
- `app/integrations/kiwoom/market_data.py`
- `app/loops/loop_b_runtime.py`
- `app/strategies/registry.py`
- `app/web/templates/dashboard_app.html`
- `tests/test_kiwoom_market_data_phase11.py`
- `tests/test_loop_b_runtime_phase5.py`
- `tests/test_dashboard_product_phase26.py` (또는 관련 대시보드 테스트)
- `tests/test_bootstrap_candles_phase30.py`
