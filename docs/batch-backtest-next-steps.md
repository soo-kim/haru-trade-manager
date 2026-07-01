# 유니버스 배치 백테스트 다음 단계 정비 계획

작성일: 2026-07-02  
작업 브랜치: `refactor/market-data-backtest-foundation`  
대상 범위: 유니버스 배치 백테스트 설계, 실행/저장 구조, coverage·제외 사유 연결, 최소 조회 API

---

## 1. 현재 판단

현재 구현은 **단일 종목 수동 백테스트와 백테스트 결과 영속화 기반**까지 완료된 상태로 본다.

확인된 흐름:

- `POST /system/backtest/run`
  - 요청으로 받은 `candles`와 `signals`를 사용해 비동기 backtest job을 실행한다.
  - 유니버스 조회나 coverage 판정은 하지 않는다.
- `POST /dashboard/backtests/manual-run`
  - `ticker`, `strategy_id`, `timeframe`, `start`, `end`를 받아 DB의 `rebuild_candles`에서 단일 종목 캔들을 읽는다.
  - 전략으로 signal을 생성한 뒤 `BacktestJobService.start_job()`에 넘긴다.
- `AutoBacktestScheduler`
  - 자동 실행 구조는 있으나, 유니버스 전체 종목을 순회하고 종목별 제외 사유와 성과를 비교하는 배치 백테스트는 아니다.
- `backtest_runs`, `backtest_trades`, `backtest_equity_points`
  - 백테스트 실행 결과를 DB에 저장하는 기반은 있다.

따라서 다음 작업은 전략 개선이 아니라 **유니버스 배치 백테스트를 1급 기능으로 추가**하는 것이다.

---

## 2. 목표

### 2.1 핵심 목표

- 유니버스 기준으로 여러 종목을 한 번에 백테스트한다.
- 실행 당시의 universe 기준, coverage 기준, 제외 종목과 제외 사유를 결과와 함께 저장한다.
- 종목별 성과와 전체 성과를 비교 가능하게 만든다.
- 기존 N+1 시가 체결 원칙과 단일 종목 백테스트 저장 구조를 유지한다.
- 실계좌 주문/포지션 경로와 분리된 안전한 분석 기능으로 유지한다.

### 2.2 비목표

이번 단계에서는 아래를 하지 않는다.

- 신규 매매 전략 추가
- 실계좌 주문 로직 변경
- 포지션/주문 상태머신 변경
- 텔레그램 명령 추가
- 대시보드 디자인 개선
- 전략 파라미터 최적화 자동화

단, 배치 백테스트 실행과 결과 확인에 필요한 최소 API와 최소 대시보드 조회 보강은 포함할 수 있다.

---

## 3. 설계 선택: parent run + ticker별 child run

초기 제안에서는 하나의 `backtest_run`에 모든 종목 결과를 누적하는 단순 구조도 가능했지만, 다음 이유로 **parent run + ticker별 child run** 구조를 채택한다.

### 3.1 채택 이유

- 종목별 성공/실패/제외 상태가 명확하게 분리된다.
- 특정 종목만 재실행하거나 결과를 비교하기 쉽다.
- 배치 실행 중 일부 종목 실패가 전체 결과를 망가뜨리지 않는다.
- 대시보드에서 parent summary와 ticker detail을 자연스럽게 나눌 수 있다.
- 향후 전략/파라미터 조합 비교, 재실행, 종목별 상세 조회로 확장하기 좋다.

### 3.2 기본 구조

- parent run
  - 배치 실행 전체를 대표한다.
  - universe 기준, timeframe, 기간, strategy, params, coverage 기준, 전체 summary를 저장한다.
  - 직접 trade를 갖지 않거나, 종합 조회용 summary만 갖는다.
- child run
  - ticker별 실제 백테스트 실행 결과를 저장한다.
  - 기존 `backtest_trades`, `backtest_equity_points`는 child run에 연결한다.
  - 실패하거나 제외된 종목도 조회 가능한 상태로 남긴다.

---

## 4. 데이터 모델 보강안

현재 `backtest_runs`를 확장하는 방식과 별도 detail 테이블을 추가하는 방식을 비교한다.

### 4.1 `backtest_runs` 최소 확장

필요 필드 후보:

- `parent_run_id`: parent batch run ID. 단일 run이면 `NULL`.
- `run_type`: `single`, `batch_parent`, `batch_child`.
- `ticker`: child run의 대상 종목. parent run이면 `NULL` 가능.

이 방식은 기존 repository/list/get 구조를 크게 바꾸지 않고 parent-child 관계를 표현할 수 있다.

### 4.2 별도 child summary 테이블 도입

예상 테이블: `backtest_batch_items`

필드 후보:

- `id`
- `batch_run_id`
- `child_run_id`
- `ticker`
- `status`: `queued`, `running`, `completed`, `failed`, `excluded`
- `exclude_reason`
- `error`
- `candle_count`
- `signal_count`
- `trade_count`
- `summary_json`
- `created_at`
- `completed_at`

### 4.3 권장안

MVP에서는 **`backtest_runs`에 parent-child 최소 필드 추가 + `summary_json`/`meta_json` 활용**을 우선한다.

단, 다음 조건 중 하나가 확인되면 `backtest_batch_items`를 추가한다.

- 제외 종목이 많아 `summary_json`만으로 조회/페이지네이션이 불편하다.
- 대시보드에서 ticker별 item을 독립적으로 필터링/정렬해야 한다.
- child run을 만들지 않는 excluded ticker도 DB row로 안정적으로 관리해야 한다.

운영 조회성을 생각하면 최종 구조는 `backtest_batch_items`가 더 낫지만, 첫 구현은 migration 범위를 최소화해도 된다. 구현 직전 현재 `backtest_runs` 모델과 repository를 다시 확인하고 결정한다.

---

## 5. BatchBacktestService

예상 파일:

- `app/services/batch_backtest.py`
- `tests/test_batch_backtest_service.py`

### 5.1 책임

`BatchBacktestService`는 다음 책임을 가진다.

1. 대상 universe 조회
2. ticker/timeframe별 coverage 확인
3. 제외 사유 산출
4. 종목별 candle range 조회
5. strategy instance 생성
6. 종목별 signal 생성
7. ticker별 child backtest 실행
8. parent run summary 갱신
9. 실패/제외 종목을 숨기지 않고 저장

### 5.2 입력 모델

필드 후보:

- `strategy_id`
- `timeframe`
- `start`
- `end`
- `universe_filter`
  - `active_only`
  - `exclude_blocked`
  - `include_halted`
  - `tickers` optional override
- `params`
  - `k`
  - `slippage_pct`
  - ATR risk params는 기존 config default 사용 또는 명시 override
- `min_candles`
- `coverage_policy`
  - `require_state_success`
  - `allow_partial_range`

### 5.3 출력 모델

parent run summary 예시:

```json
{
  "run_type": "batch_parent",
  "target_count": 180,
  "completed_count": 142,
  "failed_count": 3,
  "excluded_count": 35,
  "trade_count": 481,
  "win_rate": 0.53,
  "total_pnl": 1234567.0,
  "profit_factor": 1.42,
  "mdd": -230000.0,
  "children": {
    "completed": 142,
    "failed": 3,
    "excluded": 35
  },
  "exclude_reasons": {
    "insufficient_candles": 21,
    "coverage_gap": 9,
    "collection_state_failed": 5
  }
}
```

child run meta 예시:

```json
{
  "run_type": "batch_child",
  "parent_run_id": "batch-...",
  "ticker": "005930",
  "strategy_id": "volatility_breakout",
  "timeframe": "3m",
  "start": "2026-06-01T00:00:00+09:00",
  "end": "2026-07-01T00:00:00+09:00",
  "candle_count": 1820,
  "signal_count": 24,
  "coverage": {
    "first_candle_time": "...",
    "last_candle_time": "...",
    "row_count": 1820,
    "last_success_at": "..."
  }
}
```

excluded item 예시:

```json
{
  "ticker": "000660",
  "status": "excluded",
  "reason": "insufficient_candles",
  "candle_count": 42,
  "required_min_candles": 100
}
```

---

## 6. Coverage와 제외 사유 정책

배치 백테스트 결과는 전략 성과뿐 아니라 **실행 대상이 왜 그렇게 구성됐는지**를 설명해야 한다.

### 6.1 기본 제외 사유

- `not_in_universe`
- `inactive_symbol`
- `blocked_symbol`
- `halted_symbol`
- `no_collection_state`
- `collection_state_failed`
- `insufficient_candles`
- `coverage_gap`
- `no_signals`
- `strategy_error`
- `backtest_error`

### 6.2 `no_signals` 처리

`no_signals`는 에러가 아니다.

- 캔들 coverage는 충분하지만 전략 조건이 발생하지 않은 경우다.
- child run은 `completed`로 저장하되 `trade_count=0`, `signal_count=0`으로 남긴다.
- parent summary에는 별도 count로 표시한다.

### 6.3 부분 실패 정책

- 한 종목 실패가 batch 전체를 실패시키면 안 된다.
- 실패 ticker는 child run 또는 batch item에 `failed`로 남긴다.
- parent run은 전체 작업이 끝나면 `completed_with_errors` 또는 `completed` + `failed_count > 0` 형태로 표현한다.

---

## 7. API 설계

### 7.1 System API

우선 system API를 추가한다.

```text
POST /system/backtest/batch/run
GET  /system/backtest/batch/jobs
GET  /system/backtest/batch/jobs/{job_id}
GET  /system/backtest/batch/jobs/{job_id}/items
```

요청 예시:

```json
{
  "strategy_id": "volatility_breakout",
  "timeframe": "3m",
  "start": "2026-06-01T00:00:00+09:00",
  "end": "2026-07-01T00:00:00+09:00",
  "universe": {
    "active_only": true,
    "exclude_blocked": true,
    "include_halted": false
  },
  "params": {
    "k": 0.5,
    "slippage_pct": 0.05
  },
  "min_candles": 100
}
```

응답 예시:

```json
{
  "ok": true,
  "job_id": "batch-...",
  "status": "queued",
  "meta": {
    "run_type": "batch_parent",
    "strategy_id": "volatility_breakout",
    "timeframe": "3m",
    "target_count": 180,
    "start": "2026-06-01T00:00:00+09:00",
    "end": "2026-07-01T00:00:00+09:00"
  }
}
```

### 7.2 Dashboard API

system API가 안정화된 뒤 dashboard action을 추가한다.

```text
POST /dashboard/backtests/batch-run
GET  /dashboard/backtests/{job_id}/items
```

기존 `GET /dashboard/backtests`는 batch parent run을 목록에 포함하도록 보강한다.

---

## 8. 대시보드 최소 표시

디자인 개선이 아니라 운영자가 결과를 확인할 수 있는 최소 정보만 표시한다.

목록 화면 필수 컬럼:

- 실행 시각
- run type: single / batch
- strategy
- timeframe
- 기간
- status
- 대상 종목 수
- 완료/실패/제외 종목 수
- trade count
- total pnl
- win rate
- profit factor

상세 화면 필수 정보:

- parent summary
- 제외 사유별 count
- ticker별 child result
- ticker별 제외/실패 사유
- child run 상세 링크 또는 조회 endpoint

---

## 9. 구현 순서

### Phase 2-A. 현재 backtest 저장 구조 점검

- [x] `app/db/models/backtest.py` 확인
- [x] `app/repositories/backtest.py` 확인
- [x] parent-child 표현을 `backtest_runs` 확장만으로 충분히 할지 결정
- [x] 필요한 migration 초안 작성

완료 기준:

- parent run과 child run의 저장 방식이 확정된다.
- 제외 ticker 저장 방식이 확정된다.

### Phase 2-B. BatchBacktestService 도입

- [x] `BatchBacktestService` 생성
- [x] universe 조회 정책 구현
- [x] coverage 판정 구현
- [x] 제외 사유 enum 또는 상수 정의
- [x] ticker별 candle 조회 구현
- [x] ticker별 signal 생성 구현
- [x] child run 실행/저장 구현
- [x] parent summary 집계 구현

완료 기준:

- mock repository/session 기반 테스트에서 일부 종목 실패가 전체 batch를 중단하지 않는다.
- `no_signals`가 실패가 아니라 completed zero-trade로 저장된다.

### Phase 2-C. API 추가

- [x] `BatchBacktestRunRequest` 추가
- [x] `POST /system/backtest/batch/run` 추가
- [x] batch job 조회 API 추가
- [x] batch item 조회 API 추가

완료 기준:

- API 테스트에서 parent job 생성과 item 조회가 가능하다.

### Phase 2-D. Dashboard 최소 연동

- [x] `GET /dashboard/backtests`에 batch parent 표시 보강
- [x] `POST /dashboard/backtests/batch-run` 추가
- [x] batch items 조회 endpoint 추가

완료 기준:

- 대시보드에서 batch parent와 ticker별 item을 확인할 수 있다.

### Phase 2-E. 검증

- [x] N+1 시가 체결 회귀 테스트 유지
- [x] 단일 종목 수동 백테스트 기존 테스트 유지
- [x] batch parent/child 저장 테스트 추가
- [x] coverage 제외 사유 테스트 추가
- [x] 부분 실패 지속 실행 테스트 추가
- [x] migration upgrade 테스트 실행
- [x] 전체 테스트 실행

---

## 10. 주요 원칙

1. **배치 백테스트는 주문 경로와 완전히 분리한다.**
   - 실계좌 주문, 포지션, 주문 상태머신을 건드리지 않는다.

2. **전략 성과와 데이터 품질을 분리해서 기록한다.**
   - 성과가 나쁘거나 좋아도 coverage와 제외 사유 없이는 해석하지 않는다.

3. **부분 실패를 정상 운영 시나리오로 취급한다.**
   - 실패 종목이 있어도 batch는 끝까지 진행하고, 실패를 결과에 남긴다.

4. **기존 단일 백테스트 흐름을 깨지 않는다.**
   - `dashboard_manual`과 `system_api` 기반 단일 run은 계속 동작해야 한다.

5. **N+1 시가 체결 원칙을 유지한다.**
   - batch child run도 기존 `BacktestCore` 원칙을 사용한다.

6. **먼저 비교 가능한 저장 구조를 닫고, 전략 최적화는 그 다음에 한다.**
   - 파라미터 grid search나 전략 랭킹은 이번 단계의 후속 작업이다.

---

## 11. 이후 확장 후보

이번 MVP 이후 확장 후보:

- 전략별 batch 비교
- `k` 값 grid search
- timeframe별 batch 비교
- ticker별 재실행
- excluded ticker 재수집 후 재실행
- batch 결과 CSV export
- Telegram 요약 알림
- 대시보드 차트/랭킹 UI

이 확장들은 batch parent-child 저장 구조가 안정화된 뒤 진행한다.
