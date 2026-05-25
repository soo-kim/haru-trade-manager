# PRD 13.3 로깅 커버리지 매트릭스

기준 문서: `docs/prd.md` 13.3 필수 로깅 포인트  
기준 코드: `app/core/logging_coverage.py`

| ID | PRD 포인트 | 상태 | 근거 코드 |
|---|---|---|---|
| api_request | API 요청 | partial | `app/core/rate_limited_client.py` |
| api_retry | API 재시도 | partial | `app/orders/service.py` |
| token_refresh | 토큰 갱신 | planned | `app/core/rate_limited_client.py` |
| token_refresh_failed | 토큰 갱신 실패 | planned | `app/core/rate_limited_client.py` |
| order_execute | 주문 실행 | partial | `app/orders/service.py` |
| order_failed | 주문 실패 | implemented | `app/orders/service.py`, `app/services/runtime_safety.py` |
| position_state_transition | 포지션 상태 전환 | implemented | `app/orders/state_machine.py` |
| position_mismatch_detected | 포지션 불일치 감지 | implemented | `app/orders/service.py`, `tests/test_order_reconcile_invariants.py` |
| config_changed | 설정 변경 | implemented | `app/repositories/config.py`, `app/db/models/config.py` |
| system_halt_resume | 시스템 정지/재가동 | implemented | `app/services/runtime_safety.py`, `app/services/runtime_state.py` |
| loop_cycle_anomaly | 루프 사이클 이상 | implemented | `app/services/loop_background.py`, `app/services/loop_runtime.py` |

## 검증

- 테스트 파일: `tests/test_logging_coverage_phase24.py`
- 목적: PRD 13.3 포인트 누락/상태 값 무효화 방지
