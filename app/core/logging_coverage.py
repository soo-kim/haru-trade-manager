from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoggingPointCoverage:
    prd_point: str
    status: str
    evidence: str
    note: str = ""


PRD_13_3_COVERAGE: dict[str, LoggingPointCoverage] = {
    "api_request": LoggingPointCoverage(
        prd_point="API 요청",
        status="partial",
        evidence="app/core/rate_limited_client.py",
        note="요청 큐/우선순위/간격 제어는 존재하나 구조화 로그 확장은 추가 예정",
    ),
    "api_retry": LoggingPointCoverage(
        prd_point="API 재시도",
        status="partial",
        evidence="app/orders/service.py",
        note="주문 실패시 상태조회 기반 1회 재시도 정책 반영",
    ),
    "token_refresh": LoggingPointCoverage(
        prd_point="토큰 갱신",
        status="planned",
        evidence="app/core/rate_limited_client.py",
        note="토큰 캐시 구조 존재, 상세 갱신 로깅은 구현 예정",
    ),
    "token_refresh_failed": LoggingPointCoverage(
        prd_point="토큰 갱신 실패",
        status="planned",
        evidence="app/core/rate_limited_client.py",
        note="경고/치명 단계 로그 정책 연결 예정",
    ),
    "order_execute": LoggingPointCoverage(
        prd_point="주문 실행",
        status="partial",
        evidence="app/orders/service.py",
        note="주문 경로와 결과 객체는 고정, 구조화 출력은 보강 예정",
    ),
    "order_failed": LoggingPointCoverage(
        prd_point="주문 실패",
        status="implemented",
        evidence="app/orders/service.py, app/services/runtime_safety.py",
        note="실패 시 runtime halt + critical 이벤트 기록",
    ),
    "position_state_transition": LoggingPointCoverage(
        prd_point="포지션 상태 전환",
        status="implemented",
        evidence="app/orders/state_machine.py",
        note="전이 규칙 및 불변조건 테스트 고정",
    ),
    "position_mismatch_detected": LoggingPointCoverage(
        prd_point="포지션 불일치 감지",
        status="implemented",
        evidence="app/orders/service.py, tests/test_order_reconcile_invariants.py",
        note="불일치 시 예외/정지 시나리오 검증",
    ),
    "config_changed": LoggingPointCoverage(
        prd_point="설정 변경",
        status="implemented",
        evidence="app/repositories/config.py, app/db/models/config.py",
        note="config_history 적재 및 조회 API 제공",
    ),
    "system_halt_resume": LoggingPointCoverage(
        prd_point="시스템 정지/재가동",
        status="implemented",
        evidence="app/services/runtime_safety.py, app/services/runtime_state.py",
        note="halt/resume 상태 및 이벤트 기록",
    ),
    "loop_cycle_anomaly": LoggingPointCoverage(
        prd_point="루프 사이클 이상",
        status="implemented",
        evidence="app/services/loop_background.py, app/services/loop_runtime.py",
        note="사이클 지표(지연/오류/duration) 노출",
    ),
}


def required_point_count() -> int:
    return 11


def missing_points() -> list[str]:
    if len(PRD_13_3_COVERAGE) < required_point_count():
        return [f"missing_count={required_point_count() - len(PRD_13_3_COVERAGE)}"]
    return []
