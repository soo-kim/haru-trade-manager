# Implementation Kickoff Guide (v0.1)

## 1. 문서 목적

이 문서는 `docs/prd.md`를 실제 개발 착수 단위로 분해한 실행 가이드다.

- 무엇을 먼저 만들지
- 어떤 순서로 검증할지
- 착수 전 확정해야 할 의사결정이 무엇인지

## 2. 착수 우선순위

### P0 (바로 시작)

1. 프로젝트 골격 생성
- Python 런타임, FastAPI, SQLAlchemy/Alembic, 테스트 프레임워크 기본 구성
- Docker Compose로 `app`, `postgres` 기동

2. 공통 코어 구현
- `ConfigManager` 싱글턴 + DB 영속화 + 범위 검증
- `RateLimitedClient` 싱글턴 + 우선순위 큐 + 토큰 갱신 훅
- 구조화 로깅(JSON) 공통 유틸

3. 데이터 계층 구현
- 캔들/포지션/주문/설정 이력/스냅샷/현금흐름 테이블 생성
- 초기 마이그레이션 및 인덱스 설계

4. 루프 스켈레톤 구현
- 루프 A/B/C 프레임과 스케줄러 엔트리포인트
- 공통 종료/일시정지 플래그

### P1 (P0 직후)

1. 캔들 증분 수집 + 전략 인터페이스
2. 주문 실행기(실거래/페이퍼 모드 분기 포함)
3. 리스크 엔진(포지션 사이징, 한도 체크, 정지 조건)
4. 텔레그램 알림/명령 기본 세트

### P2 (운영 안정화)

1. 웹 대시보드(설정/성과/백테스트/유니버스)
2. 백테스트 엔진 고도화(워크포워드, 몬테카를로)
3. 운영 관측성 강화(지표, 경고 임계치, 리포트)

## 3. 모듈 경계 (초기안)

- `app/core/config_manager.py`
- `app/core/rate_limited_client.py`
- `app/core/time_sync.py`
- `app/core/logging.py`
- `app/data/models/*.py`
- `app/data/repositories/*.py`
- `app/loops/loop_a.py`
- `app/loops/loop_b.py`
- `app/loops/loop_c.py`
- `app/strategies/base.py`
- `app/strategies/*.py`
- `app/risk/engine.py`
- `app/orders/executor.py`
- `app/integrations/kiwoom/*.py`
- `app/integrations/telegram/*.py`
- `app/api/*.py`

## 4. Sprint 0 완료 기준 (Definition of Done)

- 컨테이너 기동 후 헬스체크 OK
- DB 마이그레이션 1회로 핵심 테이블 생성
- `ConfigManager` 읽기/쓰기/검증/이력 테스트 통과
- `RateLimitedClient` 요청 간격/우선순위/락 동작 테스트 통과
- 루프 A/B/C가 mock 의존성으로 최소 1사이클 실행 가능
- JSON 로그 파일 로테이션 확인

## 5. 선결 의사결정 (코딩 시작 전)

1. 기술 스택 확정
- Python 버전
- ORM(SQLAlchemy + Alembic 여부)
- 작업 큐(내장 큐 vs Redis/Celery)

2. 키움 API 상세 확정
- 서버시간 조회 엔드포인트
- NXT 주문 제약
- 미수 가능 종목/증거금률 조회 API

3. 운영 기본값 확정
- 페이퍼 초기 자본금
- 기본 전략별 파라미터 오버라이드 값
- `sync_mode` 기본값 유지(auto) 여부

## 6. 문서 사용 방법

- 상세 요구사항: `docs/functional-spec-v0.1.md`
- 실행 백로그: `docs/engineering-backlog-v0.1.md`
- 원본 PRD: `docs/prd.md`
