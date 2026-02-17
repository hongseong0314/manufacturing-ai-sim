# Project Guide

## 1. 시스템 구조
- 전체 흐름: `A -> B -> C`
- 상위 환경: `ManufacturingEnv`
- 하위 환경:
  - `ProcessA_Env`
  - `ProcessB_Env`
  - `ProcessC_Env`

## 2. ManufacturingEnv 핵심
### 2.1 reset()
시그니처:
```python
reset(seed_initial_tasks: bool = True, initial_tasks: Optional[List[Task]] = None)
```
규칙:
- `seed_initial_tasks=True`, `initial_tasks=None`:
  - 기존 동작과 동일하게 초기 Task 자동 생성/주입
- `initial_tasks` 지정:
  - 자동 생성 대신 전달된 Task만 A 큐에 주입
- `seed_initial_tasks=False`, `initial_tasks=None`:
  - A 큐를 비운 상태로 시작

### 2.2 step()
오케스트레이션 순서:
1. `A.step(t)`
2. A 성공 Task를 즉시 B에 전달
3. `B.step(t)`
4. B 성공 Task를 즉시 C에 전달
5. `C.step(t)`

의미:
- `A->B`, `B->C` 전달이 same-step으로 반영됩니다.

## 3. 이벤트 로그/무결성
- 각 공정에서 할당/완료 이벤트 기록
- 검증 시 중점:
  - 중복 할당 여부
  - 공정 순서 위반 여부
  - 완료 시각/할당 시각 정합성

## 4. 수학적 문제정의/알고리즘 레퍼런스
- `docs/model_a_problem_definition.md`
- `docs/model_a_algorithm_design.md`
- `docs/model_b_problem_definition.md`
- `docs/model_b_algorithm_design.md`
- `docs/model_c_problem_definition.md`
- `docs/model_c_algorithm_design.md`
- `docs/system_event_generation.md`

## 5. 테스트 설계 원칙
- 시나리오 격리: reset 옵션으로 초기 Task 주입 제어
- 재현성: deterministic/stochastic 시드 고정
- 플랫폼 호환성: 콘솔 출력 ASCII(`PASS`/`FAIL`)
