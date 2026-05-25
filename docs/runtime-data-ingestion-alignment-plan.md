# 런타임 데이터 수집 정책 정렬 계획 (실전 우선)

작성일: 2026-04-14  
대상: Loop B 데이터 수집, 유니버스 추적 범위, 장마감 보강 수집, 테스트/실행 환경 정책

## 1) 문제 인식

아래 현 상태는 실전 운용 관점에서 부적절하다.

- `paper` 모드에서 증분 캔들 수집이 비활성화됨
  - 현재 `DbOnlyCandleFetcher`가 빈 리스트를 반환
  - 위치: `app/services/runtime_factory.py`
- 런타임 대상 종목이 `is_active=true`, `is_blocked=false`로 제한됨
  - 위치: `app/repositories/universe.py`의 `list_runtime_tickers`
- 장중 활성 유니버스 외 종목의 장마감 보강 수집 정책이 없음
- `settings.environment == "test"` 분기 기반의 런타임 우회 코드가 존재
  - 위치: `app/main.py`의 alert sink/OTP debug/bootstrap 분기

## 2) 목표

1. 주문 모드(`paper/live`)와 무관하게 데이터 수집은 항상 수행한다.  
2. 활성 유니버스 종목은 `is_blocked` 여부와 무관하게 차트 추적을 지속한다.  
3. 장 종료 후에는 비활성 포함 전체 유니버스에 대해 최소 일봉 증분을 보강한다.  
4. 테스트 격리는 `environment` 우회가 아니라 의존성 주입/테스트 더블로 달성한다.

## 3) 운영 정책 (제안)

### A. 모드 정책

- 주문 모드:
  - `trading_mode`: `paper` 또는 `live` (기존 유지)
- 데이터 수집:
  - 별도 on/off 설정 없이 항상 실데이터 증분 수집을 시도
  - 외부 API 실패 시 DB fallback 사용

### B. 수집 대상 분리

- `trading_tickers` (주문 대상):
  - `in_universe=true`, `is_active=true`, `is_blocked=false`, `status!=HALTED`
- `tracking_tickers` (데이터 추적 대상):
  - `in_universe=true`, `is_active=true` (block 여부 무시)
  - 추가로 `open position` 보유 종목 강제 포함

### C. 시간대별 수집 정책

- 장중(08:00~20:00):
  - `tracking_tickers` 기준 분봉(3m/5m/15m/60m) 증분 수집
- 장종료 후(예: 15:40~20:00 사이 1회):
  - `in_universe=true` 전체 종목 일봉(`1d`) 증분 보강
  - 필요 시 60m 최종 봉 보강

### D. 테스트/환경 정책

- `environment=test` 기반 우회 로직 축소/제거
- 테스트에서 필요한 차이는 다음으로 대체:
  - 의존성 주입으로 외부 호출을 테스트 더블로 교체
  - 부트스트랩은 설정 플래그 없이 기본 동작(항상 시도)으로 유지

## 4) 구현 체크리스트

### 4.1 설정/스키마 정리

- [x] 불필요 설정 제거:
  - `market_data_mode`, `auth_debug_expose_code`, `alerts_enabled`
  - `bootstrap_enabled`, `server_time_offset_seconds`, `nxt_ratio`
- [x] 대시보드 설정 설명/유효값 검증 반영

### 4.2 런타임 티커 공급자 분리

- [x] `UniverseRepository`에 `list_tracking_tickers` 추가 (`is_blocked` 미필터)
- [x] 주문용과 수집용 티커 공급자를 분리
- [x] open position 보유 종목을 tracking 티커에 합집합 처리

### 4.3 데이터 수집기 분리/교체

- [x] `DbOnlyCandleFetcher` 제거 또는 read-only fallback으로 축소
- [x] `paper/live` 주문 모드와 무관하게 `LiveCandleFetcher` 사용 시도
- [x] 외부 API 실패 시 DB fallback/재시도/에러카운트 로깅 보강

### 4.4 Loop B/Loop C 역할 재배치

- [x] Loop B: 장중 `tracking_tickers` 분봉 증분 수집 + 전략 스캔
- [x] Loop C: 장종료 1회 전체 유니버스 `1d` 보강 작업 추가
- [x] 장종료 보강 중 API rate limit 안전장치(배치/슬립) 추가

### 4.5 environment 의존 제거

- [x] `app/main.py`의 `settings.environment == "test"` 분기 목록화
- [x] 기능 플래그(`bootstrap_enabled`) 제거 후 기본 동작(항상 부트스트랩 시도)으로 단순화
- [x] 테스트 코드/픽스처를 설정 제거 기준으로 갱신

### 4.6 관찰성/대시보드

- [x] 수집 대상 카운트(주문/추적/전체) 메트릭 노출
- [x] 장종료 보강 작업의 시작/종료/성공률/종목수 표시
- [ ] 3m 포함 timeframe별 수집 성공률 로그/요약 추가

## 5) 테스트 계획

### 단위 테스트

- [x] `paper` 모드에서도 분봉 증분 fetch 수행 검증
- [x] `list_tracking_tickers`가 `is_blocked=true` 활성종목 포함하는지 검증
- [ ] 장종료 보강이 `in_universe=true` 전체를 대상으로 도는지 검증
- [x] open position 종목이 비활성이어도 tracking 합집합 포함 검증

### 통합 테스트

- [ ] Loop B 3m 슬롯에서 `paper` 모드에서도 캔들 upsert 발생 검증
- [ ] 장종료 보강 후 candle-range(1d) 증가 검증
- [ ] 기존 전략 실행/주문 필터(`is_blocked`) 회귀 없음 검증

### 수동 검증

- [ ] `paper` 모드로 10분 이상 구동 시 3m/5m 캔들 증가 확인
- [ ] `is_blocked=true && is_active=true` 종목의 캔들 증분 확인
- [ ] 장종료 보강 후 비활성 종목의 일봉 최신화 확인

## 6) 리스크 및 대응

- API 호출량 증가:
  - 대응: timeframe별/구간별 배치 제한, 실패 backoff
- 수집과 주문 경계 혼선:
  - 대응: `trading_tickers`와 `tracking_tickers` 인터페이스 분리
- 테스트 안정성 저하:
  - 대응: 외부 연동은 더블/fixture로 통제, 런타임 기본 동작은 항상 실행

## 7) 완료 기준 (DoD)

- [ ] `paper` 모드에서도 실데이터 증분 수집이 지속된다.
- [ ] 활성 유니버스는 block 여부와 무관하게 캔들이 업데이트된다.
- [ ] 장종료 후 전체 유니버스 일봉 보강이 자동 수행된다.
- [ ] `environment=test` 우회 의존이 제거되고, 테스트는 주입 기반으로 동작한다.
- [ ] 관련 단위/통합 테스트가 통과한다.

## 8) 예상 변경 파일

- `app/services/runtime_factory.py`
- `app/repositories/universe.py`
- `app/loops/loop_b_runtime.py`
- `app/services/loop_runtime.py` (필요 시)
- `app/main.py`
- `app/core/config.py`
- `tests/conftest.py`
- `tests/test_loop_b_runtime_phase5.py`
- `tests/test_runtime_factory_phase10.py`
- `tests/test_dashboard_product_phase26.py` (메트릭 확인 시)

## 9) 이번 반영 결과 (2026-04-14)

- 반영 완료 파일:
  - `app/core/config.py`, `app/core/settings.py`, `.env.example`
  - `app/core/time_sync.py`
  - `app/repositories/universe.py`
  - `app/repositories/config.py`
  - `app/services/runtime_factory.py`
  - `app/services/backtest_scheduler.py`
  - `app/services/loop_runtime.py`
  - `app/main.py`
  - `tests/test_config_invariants.py`
  - `tests/test_time_sync_phase3.py`
  - `tests/test_repositories_universe.py`
  - `tests/test_runtime_factory_phase10.py`
- 검증 결과:
  - `pytest -q` 전체 테스트 통과
  - 실행 세트:
    - 전체 스위트 (`./.venv/bin/python -m pytest -q`)
