# 시장데이터·백테스트 기반 정비 계획

작성일: 2026-07-01  
작업 브랜치: `refactor/market-data-backtest-foundation`  
대상 범위: 유니버스 종목 차트 데이터 저장, 데이터 품질 검증, 백테스트 실행 기반

---

## 1. 배경

현재 프로젝트는 자동매매 시스템 재구축을 목표로 시작했지만, 구현 범위가 다음 영역까지 빠르게 확장되어 있다.

- ConfigManager / 설정 이력
- RateLimitedClient / Kiwoom REST 연동
- Loop A/B/C 런타임
- 전략 1~5 기본 구현
- 주문/포지션/리스크 계층
- 텔레그램 명령 서비스
- 대시보드/OTP 인증
- 성과 리포트
- 수동/자동 백테스트 Job API

반면 자동매매와 백테스트의 공통 기반인 **유니버스 종목들의 차트 데이터가 정상적으로, 충분히, 검증 가능하게 저장되는지**는 아직 운영 관점에서 완전히 닫히지 않았다.

따라서 당분간 매매 로직 확장보다 아래 기반을 먼저 안정화한다.

1. 유니버스 종목들의 차트 데이터 수집/저장 안정화
2. timeframe별 데이터 coverage와 품질 확인
3. 백테스트 입력 데이터셋 구성과 결과 재현성 확보
4. 이후 매매 로직을 얹을 수 있는 신뢰 가능한 데이터 기반 마련

---

## 2. 정비 목표

### 2.1 핵심 목표

- 전체 유니버스 종목에 대해 `3m`, `5m`, `15m`, `60m`, `1d` 캔들을 안정적으로 저장한다.
- 초기 적재와 증분 적재를 명확히 구분한다.
- 종목/timeframe별 수집 상태와 누락 여부를 조회할 수 있게 한다.
- 백테스트는 검증된 캔들 데이터만 사용하도록 한다.
- 백테스트 실행 조건과 결과를 비교 가능하게 남긴다.

### 2.2 비목표

이번 정비 단계에서는 아래 작업을 하지 않는다.

- 신규 매매 전략 추가
- 실계좌 주문 로직 고도화
- 포지션/주문 상태머신 확장
- 텔레그램 명령 추가
- 대시보드 디자인 개선
- 성과 리포트 고도화
- 실시간 WebSocket 시세 처리

단, 데이터 수집 상태와 백테스트 실행에 필요한 최소 API/대시보드 표시 보강은 포함할 수 있다.

---

## 3. 현재 코드 기준 관찰 내용

### 3.1 유니버스

관련 파일:

- `app/db/models/universe.py`
- `app/repositories/universe.py`
- `app/services/universe_bootstrap.py`

현재 유니버스는 `symbols` 테이블을 기준으로 관리된다.

주요 필드:

- `ticker`
- `name`
- `market`
- `in_universe`
- `is_active`
- `is_blocked`
- `status`

현재 repository에는 목적별 조회가 일부 분리되어 있다.

- `list_trading_tickers()`
  - `in_universe=true`, `is_active=true`, `is_blocked=false`, `status!=HALTED`
  - 매매 가능 대상
- `list_tracking_tickers()`
  - `in_universe=true`, `is_active=true`
  - 차트 추적 대상
- `list_universe_tickers()`
  - `in_universe=true`
  - 전체 유니버스 대상

이 방향은 유지하되, 앞으로는 **데이터 수집 대상과 매매 대상이 섞이지 않도록** 모든 계층에서 의미를 명확히 해야 한다.

권장 의미:

| 필드 | 의미 |
|---|---|
| `in_universe` | 관리/수집 대상 여부 |
| `is_active` | 전략/백테스트 기본 대상 여부 |
| `is_blocked` | 실매매 진입 금지 여부 |
| `status` | 정상/거래정지/편입제외/청산대기 등 상태 |

### 3.2 캔들 저장

관련 파일:

- `app/db/models/candle.py`
- `app/repositories/candle.py`

현재 캔들 테이블은 `rebuild_candles`이다.

주요 필드:

- `ticker`
- `timeframe`
- `candle_time`
- `open`
- `high`
- `low`
- `close`
- `volume`

현재 `(ticker, timeframe, candle_time)` unique constraint가 있다. 동일 봉 중복 저장을 막는 기본 구조는 적절하다.

다만 운영/백테스트 기반으로 쓰기 위해서는 다음 보강이 필요하다.

- 종목/timeframe별 수집 상태 저장
- coverage 조회 API/서비스
- 누락/지연/실패 종목 식별
- 진행 중 봉과 확정 봉의 백테스트 사용 정책 명확화
- range 조회 성능을 고려한 인덱스 점검

### 3.3 데이터 수집 런타임

관련 파일:

- `app/loops/loop_b_runtime.py`
- `app/services/runtime_factory.py`
- `app/services/universe_bootstrap.py`

현재 `LoopBRunner`는 다음 책임을 함께 가진다.

1. 봉마감 판단
2. 증분 캔들 동기화
3. 전략 스캔
4. 시그널 큐 적재

실매매 런타임 관점에서는 자연스럽지만, 이번 정비 단계에서는 데이터 수집과 전략 실행을 분리해서 다루는 편이 안전하다.

권장 분리:

- Data Collector
  - 유니버스 종목별 캔들 수집/저장
  - 수집 상태/실패 사유 기록
- Backtest Dataset Builder
  - 저장된 캔들에서 검증된 백테스트 입력 데이터셋 구성
- Backtest Runner
  - 데이터셋 기반 전략 실행과 결과 저장
- Live Trading Loop
  - 이후 정비 완료 후 다시 연결

### 3.4 백테스트

관련 파일:

- `app/backtest/core.py`
- `app/services/backtest_jobs.py`
- `app/main.py`의 `_start_manual_backtest()`

현재 백테스트는 다음 특징을 가진다.

- N+1 시가 체결 원칙은 `BacktestCore.entry_price_n_plus_one_open()`에 반영되어 있다.
- 수동 백테스트는 DB의 `rebuild_candles`에서 지정 종목/timeframe/기간의 캔들을 읽는다.
- 전략으로 signal을 생성한 뒤 `BacktestJobService`가 비동기 job으로 결과를 계산한다.
- Job 상태와 결과는 메모리 딕셔너리에 저장된다.

현재 한계:

- 서버 재시작 시 백테스트 결과가 사라진다.
- 단일 종목/단일 전략/단일 timeframe 중심이다.
- 유니버스 전체 배치 백테스트 결과 비교 구조가 부족하다.
- 백테스트 실행 당시의 데이터 coverage와 제외 종목 사유가 결과와 강하게 묶여 있지 않다.

---

## 4. 정비 방향

### 4.1 데이터 수집을 1급 기능으로 격상

캔들 row 저장 자체뿐 아니라, 수집 작업의 상태와 품질을 별도 관리한다.

필요 기능:

- 종목/timeframe별 최초·최신 candle_time 조회
- row count 조회
- 마지막 수집 성공/실패 시각 조회
- 마지막 오류 메시지 저장
- 연속 실패 횟수 저장
- timeframe별 coverage 요약
- 백테스트 가능 종목 수 계산

### 4.2 수집 상태 테이블 도입 검토

예상 테이블: `candle_collection_state`

예상 필드:

- `ticker`
- `timeframe`
- `first_candle_time`
- `last_candle_time`
- `row_count`
- `last_success_at`
- `last_error_at`
- `last_error`
- `consecutive_error_count`
- `source`
- `updated_at`

이 테이블은 `rebuild_candles`의 보조 상태 테이블이며, canonical OHLCV 데이터는 계속 `rebuild_candles`를 사용한다.

### 4.3 초기 적재와 증분 적재 분리

초기 적재:

- 신규 유니버스 종목 또는 timeframe이 비어 있는 종목에 대해 가능한 과거 캔들을 적재한다.
- 대량 작업이므로 진행률과 부분 실패를 기록한다.
- 실패 종목이 있어도 전체 작업을 중단하지 않는다.

증분 적재:

- 마지막 저장 candle_time 이후 데이터를 가져온다.
- 진행 중 봉은 update, 신규 확정 봉은 insert한다.
- 장마감 이후 전체 유니버스 일봉 보강을 수행한다.

### 4.4 백테스트 데이터셋 기준 명확화

백테스트 실행 시 다음 정보를 결과와 함께 남긴다.

- 실행 시각
- 유니버스 기준
- 대상 종목 수
- 제외 종목과 제외 사유
- timeframe
- 기간
- 사용 candle row 수
- 전략 ID와 파라미터
- slippage/commission
- 데이터 coverage 기준

초기에는 완전한 스냅샷 테이블까지 만들지 않더라도, 백테스트 결과 비교가 가능하도록 실행 메타데이터를 저장한다.

### 4.5 백테스트 결과 영속화

현재 메모리 job 결과는 운영 도구로 부족하다.

예상 테이블:

#### `backtest_runs`

- `id`
- `name`
- `strategy_id`
- `timeframe`
- `start_at`
- `end_at`
- `params_json`
- `slippage_pct`
- `commission_pct`
- `status`
- `created_at`
- `completed_at`
- `summary_json`

#### `backtest_trades`

- `run_id`
- `ticker`
- `entry_signal_time`
- `entry_time`
- `entry_price`
- `exit_time`
- `exit_price`
- `side`
- `pnl`
- `return_pct`
- `exit_reason`
- `bars_held`

#### `backtest_equity_points`

- `run_id`
- `timestamp`
- `equity`
- `drawdown`

---

## 5. 우선순위 작업안

### Phase 1-A. 현재 상태 가시화

- [x] 캔들 coverage 서비스 추가
- [x] timeframe별 저장 종목 수 조회
- [x] 종목별 최신 candle_time 조회
- [x] 최근 수집 지연 종목 조회
- [x] 백테스트 가능 종목 수 조회
- [x] 최소 API 또는 대시보드 요약 추가

### Phase 1-B. 수집 상태 관리

- [x] `candle_collection_state` 스키마 설계
- [x] Alembic migration 추가
- [x] 캔들 upsert 후 상태 갱신
- [x] 수집 실패 시 오류 상태 기록
- [x] 상태 repository/service 추가

### Phase 1-C. 수집 파이프라인 정리

- [x] 초기 적재 서비스와 증분 적재 서비스 분리
- [x] 특정 ticker/timeframe 재수집 기능 추가
- [x] 장마감 전체 유니버스 `1d` 보강 검증
- [x] `3m/5m/15m/60m/1d` 수집 성공률 로그 추가
- [x] API rate limit과 부분 실패 정책 점검

### Phase 1-D. 백테스트 기반 정리

- [x] 백테스트 run/trade/equity 결과 저장 스키마 설계
- [x] 메모리 job 결과를 DB 결과와 연결
- [x] 백테스트 실행 메타데이터 저장
- [x] 단일 종목 수동 백테스트 결과 영속화
- [x] 유니버스 배치 백테스트 설계

### Phase 1-E. 검증

- [x] 캔들 중복 저장 방지 테스트
- [x] 진행 중 봉 update / 신규 봉 insert 테스트
- [x] coverage 계산 테스트
- [x] 수집 실패 상태 기록 테스트
- [x] 백테스트가 N+1 시가 체결을 유지하는지 회귀 테스트
- [x] 백테스트 결과 저장/조회 테스트

---

## 6. 설계 원칙

1. **매매 대상과 데이터 수집 대상을 분리한다.**
   - block된 종목도 데이터 추적은 계속할 수 있다.
   - 매매 가능 여부는 주문 계층에서만 의미를 가진다.

2. **canonical OHLCV 저장소는 하나로 유지한다.**
   - 백테스트용 별도 캔들 테이블을 만들지 않는다.
   - 백테스트는 검증된 `rebuild_candles`를 읽는다.

3. **백테스트는 확정 봉 기준으로 실행한다.**
   - 진행 중 봉이 DB에 update될 수 있어도, 백테스트 입력에서는 제외하거나 명시적으로 통제한다.

4. **백테스트 결과는 비교 가능해야 한다.**
   - 전략 결과만 저장하지 않고 데이터 범위와 제외 사유를 함께 남긴다.

5. **매매 로직은 이번 단계에서 동결한다.**
   - 데이터 기반이 안정화되기 전에는 전략/주문 로직을 확장하지 않는다.

6. **실패는 숨기지 않는다.**
   - 특정 종목/timeframe 수집 실패는 전체 실패가 아니라 상태로 기록한다.
   - 운영자는 어떤 종목이 왜 백테스트 대상에서 제외됐는지 알 수 있어야 한다.

---

## 7. 완료 기준

이번 정비 단계의 완료 기준은 다음과 같다.

- [x] 전체 유니버스 기준 timeframe별 캔들 coverage를 조회할 수 있다.
- [x] 종목/timeframe별 마지막 수집 상태와 오류를 조회할 수 있다.
- [x] 초기 적재와 증분 적재가 구분되어 실행된다.
- [x] 장마감 이후 전체 유니버스 일봉 보강 결과를 확인할 수 있다.
- [x] 백테스트 실행 결과가 DB에 저장된다.
- [x] 백테스트 결과에 데이터 범위와 실행 메타데이터가 포함된다.
- [x] 기존 N+1 시가 체결 원칙이 유지된다.
- [x] 관련 테스트가 통과한다.

---

## 8. 구현 결과 요약

이번 정비 브랜치에서 다음 구현을 추가했다.

- `candle_collection_state` 테이블/모델/repository를 추가해 종목·timeframe별 최초/최신 봉, row 수, 마지막 성공/실패, 오류 메시지, 연속 실패 횟수를 저장한다.
- `CandleCoverageService`를 추가해 전체 유니버스 기준 coverage, 미수집 종목, stale 종목, 실패 상태 종목, 백테스트 가능 종목 수를 계산한다.
- 대시보드 읽기 API에 다음 endpoint를 추가했다.
  - `GET /dashboard/market-data/coverage`
  - `GET /dashboard/market-data/collection-states`
- `CandleCollectionService`를 추가해 초기 적재, 증분 적재, 특정 ticker/timeframe 재수집을 같은 정책으로 실행하고 부분 실패를 상태로 기록한다.
- 기존 `bootstrap_candles_on_first_run()` 경로에서도 캔들 upsert 성공/실패가 `candle_collection_state`에 반영되도록 했다.
- 장중 `LoopBRunner` 증분 수집과 장마감 `post_market_backfill`도 같은 상태 기록 경로를 사용하도록 보강해, 실제 운영 수집 경로에서 상태 테이블이 비는 문제를 막았다.
- `backtest_runs`, `backtest_trades`, `backtest_equity_points` 테이블/모델/repository를 추가했다.
- `BacktestJobService`가 메모리 job 상태를 유지하면서도 실행 메타데이터, summary, trade, equity point를 DB에 저장하도록 연결했다.
- 서버 재시작 뒤에도 `BacktestJobService.get_job/list_jobs/count_jobs`가 `backtest_runs`에서 완료 run을 복원해 조회할 수 있도록 보강했다.
- 유니버스 배치 백테스트는 이 저장 구조를 기준으로 `backtest_runs.meta_json`에 universe 기준/제외 사유/coverage 기준을 넣고, 종목별 체결은 `backtest_trades`에 누적하는 방식으로 확장한다.
- 검증: `./.venv/bin/python -m pytest -q` 결과 `134 passed, 1 warning`.
- 검증: `DATABASE_URL=${TEST_DATABASE_URL:-postgresql+psycopg://haru:haru@localhost:6432/haru_trade_test} ./.venv/bin/alembic upgrade head` 통과.
- 검증: 변경 파일 대상 `ruff check` 및 `compileall` 통과.

---

## 9. 참고 파일

- `docs/runtime-data-ingestion-alignment-plan.md`
- `docs/3m-timeframe-bootstrap-expansion-plan.md`
- `docs/functional-spec-v0.1.md`
- `app/db/models/candle.py`
- `app/db/models/universe.py`
- `app/repositories/candle.py`
- `app/repositories/universe.py`
- `app/services/universe_bootstrap.py`
- `app/loops/loop_b_runtime.py`
- `app/backtest/core.py`
- `app/services/backtest_jobs.py`
- `app/main.py`
