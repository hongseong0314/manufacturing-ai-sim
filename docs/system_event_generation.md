# System Event Generation

시뮬레이션 이벤트와 Task 생성 규칙 정의 문서입니다.

## 1. Time Definition
- time step 단위 진행
- same-step handoff: `A -> B -> C`

## 2. Task Entity
- uid
- spec fields
- rework_count
- timestamps(assigned/completed)

## 3. Generation Rule
- reset 시 초기 주입 정책
- 주기적 배치 생성 정책
- seed 고정 규칙

## 4. Event Taxonomy
- task_assigned
- task_completed
- task_rework_assigned
- pack_completed

## 5. Integrity Rules
- no duplicate assignment
- process order monotonicity
- timestamp consistency
