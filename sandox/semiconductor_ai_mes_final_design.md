# AI 기반 반도체 MES 시스템 최종 설계서

## 1. 시스템 목표

본 시스템은 반도체 제조 공정에서 Product, Lot, Wafer, Carrier, Route, Operation, Equipment, Recipe, WIP, 품질, 이벤트, Genealogy를 통합 관리하는 AI 기반 MES이다.

목표는 단순 MES 기능 구현이 아니라, 현재 workspace의 다공정 제조 시뮬레이터를 기반으로 AI 추천, Rule Engine 검증, 이벤트 추적, KPI 평가가 가능한 simulator-backed MES MVP를 설계하는 것이다.

핵심 원칙은 다음과 같다.

- AI는 직접 장비를 제어하지 않는다.
- AI는 추천을 생성하고, MES Rule Engine이 검증한 뒤 command를 실행한다.
- 모든 추천, 검증, 실행은 `correlation_id`로 추적한다.
- 4-layer 의사결정 구조를 데이터 모델, API, 이벤트, MVP 개발 순서에 일관되게 반영한다.
- 현재 workspace는 production MES나 실제 fab digital twin이 아니라 연구용 다공정 제조 시뮬레이터이다.

---

## 2. 현재 시뮬레이터와 MES 매핑

현재 repository는 A -> B -> C 3단계 제조 흐름을 가진다.

```text
A: machining / process QA
B: cleaning / process QA
C: packing / finalization
```

MES 관점 매핑은 다음과 같다.

| 현재 시뮬레이터 | MES 개념 | 설명 |
|---|---|---|
| `Task` | Wafer 또는 Wafer-level work item | Lot 내부 개별 처리 단위 |
| `job_id` | Lot ID / Work Order ID | 여러 Task가 하나의 생산 지시를 구성 |
| `due_date` | Due Date / Commit Date | 납기 및 priority 계산 기준 |
| `spec_a`, `spec_b` | Operation Spec / Control Limit | 공정별 품질 판정 기준 |
| `location` | Lot/Wafer Current Location | `QUEUE_A`, `PROC_*`, `COMPLETED` 등 |
| `realized_qa_A/B` | Inspection / Metrology Result | 공정 결과 품질값 |
| `rework_count` | Rework Count | 재작업 횟수 |
| `history` | Event History / Audit Trail | Lot/Wafer 이력 |
| `ProcessA_Machine`, `ProcessB_Machine`, `ProcessC_Machine` | Equipment / Tool | 장비 자원 |
| `u`, `v` | Consumable / Chemical Usage | 소모품, bath, chamber 상태 |
| `m_age`, `b_age` | Equipment Age / Degradation | 장비 열화 상태 |
| `scheduler_A/B` | Layer 1 Dispatch Policy | 후보 Lot/Wafer 선택 |
| `tuner_A/B` | Layer 2 APC / Recipe Policy | Recipe 및 교체 추천 |
| `packer_C` | Layer 1 Packing Policy | 출하/패키징 조합 결정 |
| `DefaultMetaScheduler` | Layer 3 Orchestration | 공정 간 WIP/납기/품질 조정 |
| 향후 objective optimizer | Layer 4 System Objective | fab-level 목적함수와 weight 결정 |
| `get_decision_state()` | MES Decision Snapshot | AI 및 Rule Engine 입력 상태 |
| `env.step(actions)` | Command Execution Cycle | 검증된 action 적용 |

현재 구조의 핵심은 environment와 decision logic의 분리이다.

- Environment: 상태 전이, 물리 모델, QA, 이벤트 로그 적용
- Scheduler/Tuner/Packer: 공정별 의사결정
- Meta Scheduler: 공정 간 의사결정 조합
- Factory: config 기반 정책 조립

MES 설계에서도 이 구조를 유지한다.

### 2.1 구현 경계: Simulator Kernel / MES Shell

구현은 기존 시뮬레이터를 반도체 MES로 직접 변형하지 않는다. 현재
`src/environment/*`, `src/schedulers/*`, `src/tuners/*`, `src/agents/*`는
제조 의사결정 실험을 실행하는 simulator kernel로 유지한다.

그 위에 별도 MES shell을 추가한다.

```text
Simulator Kernel
  - Task, Machine, ManufacturingEnv
  - A/B/C process physics
  - scheduler/tuner/packer/meta scheduler baseline
  - step(actions), get_decision_state()

MES Shell
  - Product/Lot/Wafer/Carrier/Equipment/Recipe domain model
  - simulator state -> MES DTO adapter
  - FeatureSnapshot / AIRecommendation / Event / Genealogy
  - Rule Engine
  - layered decision service
  - simulator action adapter
```

초기 구현 위치는 `src/mes/`로 둔다. 이 패키지는 기존 simulator kernel을
호출하고 감싸지만, process environment 내부에 MES 규칙을 직접 넣지 않는다.
이 경계를 지켜야 기존 실험/테스트가 깨지지 않고, 나중에 실제 Equipment
Adapter나 production MES backend로 교체할 수 있다.

---

## 3. 전체 아키텍처

```text
ERP / PLM / SCM
    ↓
MES Core
    ├─ Product / Route / Operation Management
    ├─ Lot / Wafer / Carrier Management
    ├─ WIP Tracking
    ├─ Dispatching
    ├─ Reservation / Track-In / Track-Out
    ├─ Equipment Management
    ├─ Recipe Management
    ├─ Quality / SPC / APC
    ├─ Genealogy / Traceability
    ├─ Event / Audit Log
    ├─ Rule Engine
    └─ AI Recommendation Gateway
          ├─ Layer 4 Objective Optimizer
          ├─ Layer 3 Stage Priority / WIP Orchestrator
          ├─ Layer 1 Dispatch / Packing Ranker
          └─ Layer 2 Recipe / APC Recommender
    ↓
Equipment Integration
    ├─ Equipment Simulator
    ├─ SECS/GEM Adapter
    ├─ OPC-UA Adapter
    ├─ PLC/SCADA Adapter
    └─ Sensor / Metrology Adapter
    ↓
Equipment / Tool / Chamber / Sensor
```

MVP에서는 실제 장비 연동 대신 현재 simulator를 Equipment Simulator로 사용한다.
즉, `ManufacturingEnv`는 runtime kernel이고, MES API와 AI Gateway는
`src/mes/` shell에서 simulator state/action을 변환한다.

```text
MES API
  → Candidate Generator
  → AI Recommendation Gateway
  → Rule Engine
  → Simulator Adapter
  → ManufacturingEnv.step(actions)
  → Event / KPI / Genealogy 저장
```

---

## 4. 4-Layer 의사결정 구조

본 MES의 핵심은 4-layer 의사결정 구조이다. 최종 action은 단일 AI 모델의 결과가 아니라 여러 layer의 추천이 연결된 decision chain이다.

```text
Layer 4: System-Level Objective
    전체 fab throughput, yield, cost, robustness, due-date 목표 설정

Layer 3: Cross-Stage Coupling
    공정 간 WIP, starvation, blocking, rework, 납기 전파 판단

Layer 1: Task Allocation
    어떤 Lot/Wafer를 어떤 Equipment에 언제 투입할지 결정

Layer 2: Process-Level Dynamics
    Recipe, APC, consumable/solution replacement, 품질 drift 보정
```

Layer 1과 Layer 2는 실행 직전 같은 시점에 결합된다. 즉, "무엇을 어느 장비에 투입할 것인가"와 "어떤 recipe/control로 처리할 것인가"가 함께 Rule Engine 검증 대상이 된다.

### 4.1 Layer별 역할

| Layer | MES 역할 | 현재 코드 대응 | 입력 | 출력 |
|---|---|---|---|---|
| Layer 4 | Fab-level objective | 향후 AI supervisor | KPI, SLA, cost, yield objective | `objective_id`, policy weight |
| Layer 3 | Cross-stage WIP orchestration | `DefaultMetaScheduler` | A/B/C queue, incoming, rework, due date | stage priority |
| Layer 1 | Dispatch / Packing | `scheduler_A/B`, `packer_C` | 후보 Lot, 장비 상태, batch size | selected lot/wafer/equipment |
| Layer 2 | Recipe / APC / Maintenance | `tuner_A/B` | 선택 Lot, 장비 열화, spec | recipe, replace flag |

### 4.2 Decision Chain

모든 AI 추천은 독립 레코드이면서 동시에 하나의 chain으로 연결된다.

```text
OBJECTIVE_SELECTED
  correlation_id = CORR_001
  recommendation_id = REC_L4_001
  layer_id = L4
    ↓ parent_recommendation_id
STAGE_PRIORITY_UPDATED
  recommendation_id = REC_L3_001
  layer_id = L3
  parent_recommendation_id = REC_L4_001
    ↓
DISPATCH_RECOMMENDED
  recommendation_id = REC_L1_001
  layer_id = L1
  parent_recommendation_id = REC_L3_001
    ↓
RECIPE_RECOMMENDED
  recommendation_id = REC_L2_001
  layer_id = L2
  parent_recommendation_id = REC_L1_001
    ↓
RULE_VALIDATION_PASSED
    ↓
COMMAND_EXECUTED
```

이 구조를 통해 특정 Track-In command가 어떤 fab-level objective, 어떤 stage priority, 어떤 dispatch 추천, 어떤 recipe 추천에서 비롯되었는지 추적할 수 있다.

### 4.3 예시: Packing 의사결정

Packing 공정의 의사결정은 다음처럼 분해된다.

```text
π(a | s)
= π(customer_or_due_priority | fab_state)
  × π(pack_combination | customer_or_due_priority, local_pack_state)
```

상위 layer는 "지금 어떤 고객사/제품군/납기 위험군을 우선할 것인가"를 결정하고, 하위 layer는 "선택된 우선순위 안에서 어떤 조합이 최적인가"를 결정한다.

---

## 5. AI 추천과 Rule Engine 실행의 분리

AI는 다음을 수행한다.

- Layer 4: 목적함수와 KPI weight 추천
- Layer 3: 공정별 priority, WIP pressure, bottleneck 대응 추천
- Layer 1: dispatch/packing 후보 ranking
- Layer 2: recipe/APC/maintenance 추천

AI는 다음을 직접 수행하지 않는다.

- 장비 직접 제어
- Track-In 강제 실행
- Hold 해제
- Recipe download
- Carrier 이동
- Lot 상태 변경 확정

최종 실행은 반드시 Rule Engine을 통과한다.

```text
Decision State
    ↓
Feature Snapshot 저장
    ↓
Candidate Generation
    ↓
Layered AI Recommendation
    ↓
Rule Engine Validation
    ↓
Reservation / Track-In / Recipe Apply Command
    ↓
Event Log / Audit / Genealogy / KPI Update
```

Rule Engine은 다음을 검증한다.

- Lot 상태가 dispatch 가능한지
- Hold 상태가 아닌지
- Operation과 Equipment capability가 일치하는지
- Recipe가 승인되었는지
- Equipment 상태가 IDLE 또는 RESERVED인지
- Queue Time, carrier, batch 조건을 만족하는지
- 동일 Lot/Wafer가 중복 dispatch되지 않는지
- 상위 layer 추천과 하위 layer 추천의 `correlation_id`가 일치하는지
- AI confidence가 운영 기준 이상인지
- override가 필요한 경우 operator approval이 있는지

---

## 6. 핵심 데이터 모델

### 6.1 Product

| Field | Type | 설명 |
|---|---|---|
| `product_id` | string | 제품 ID |
| `product_family` | string | 제품군 |
| `priority_class` | string | normal, hot, engineering |
| `default_route_id` | string | 기본 route |
| `spec_profile_id` | string | 품질 spec |
| `customer_id` | string | 고객 |
| `margin_value` | number | 수익성/우선순위 score 입력 |

현재 `Task.material_type`, `color`, `customer_id`, `margin_value`, `spec_a`, `spec_b`를 Product 속성으로 확장한다.

### 6.2 Lot

| Field | Type | 설명 |
|---|---|---|
| `lot_id` | string | Lot ID |
| `product_id` | string | 제품 |
| `route_id` | string | 현재 route |
| `current_operation_id` | string | 현재 operation |
| `carrier_id` | string | carrier |
| `status` | enum | CREATED, RELEASED, WAIT, RESERVED, PROCESSING, HOLD, REWORK, COMPLETED, SCRAPPED, SHIPPED |
| `priority` | number | dispatch priority |
| `due_date` | datetime | 납기 |
| `quantity` | number | wafer 수량 |
| `rework_count` | number | rework 횟수 |

현재 `job_id`는 MVP에서 `lot_id`로 매핑한다.

### 6.3 Wafer

| Field | Type | 설명 |
|---|---|---|
| `wafer_id` | string | Wafer ID |
| `lot_id` | string | 소속 Lot |
| `slot_no` | number | Carrier slot |
| `status` | enum | WAIT, PROCESSING, HOLD, SCRAPPED, COMPLETED |
| `current_operation_id` | string | 현재 operation |
| `qa_results` | json | 공정별 metrology 결과 |
| `genealogy_parent_ids` | array | parent wafer/material |
| `genealogy_child_ids` | array | child output |

현재 `Task.uid`는 MVP에서 `wafer_id` 또는 wafer-level work item ID로 사용한다.

### 6.4 Carrier

| Field | Type | 설명 |
|---|---|---|
| `carrier_id` | string | FOUP/Carrier ID |
| `carrier_type` | string | FOUP, cassette 등 |
| `location` | string | stocker, equipment, port |
| `status` | enum | AVAILABLE, RESERVED, IN_USE, HOLD |
| `lot_id` | string | 적재 Lot |

### 6.5 Route / Operation

| Field | Type | 설명 |
|---|---|---|
| `route_id` | string | Route ID |
| `operation_id` | string | Operation ID |
| `operation_seq` | number | 순서 |
| `operation_type` | string | PHOTO, ETCH, CLEAN, METRO, CMP, PACK |
| `equipment_group_id` | string | 가능한 장비군 |
| `recipe_group_id` | string | 가능한 recipe군 |
| `queue_time_min/max` | number | queue time 제약 |
| `rework_route_id` | string | rework route |
| `next_operation_rules` | json | 분기 조건 |

반도체 공정은 re-entry와 rework를 가지므로 단순 선형 flow만 가정하지 않는다.

```text
CLEAN_100 → PHOTO_110 → ETCH_120 → METRO_130
        ↘ rework → PHOTO_110
METRO_130 → CVD_140 → CMP_150 → METRO_160 → PACK_900
```

### 6.6 Equipment

| Field | Type | 설명 |
|---|---|---|
| `equipment_id` | string | 장비 ID |
| `equipment_group_id` | string | 장비군 |
| `status` | enum | IDLE, RESERVED, RUN, DOWN, PM, SETUP, QUAL, ENGINEERING, WAIT_RECIPE, WAIT_MATERIAL |
| `current_lot_id` | string | 처리 중 Lot |
| `current_recipe_id` | string | 현재 recipe |
| `capable_operations` | array | 처리 가능 operation |
| `batch_size` | number | batch capacity |
| `health_state` | json | age, usage, sensor state |
| `last_event_time` | datetime | 마지막 이벤트 |

현재 `ProcessA_Machine.u/m_age`, `ProcessB_Machine.v/b_age`, `status`, `batch_size`, `finish_time`이 health 및 상태 모델의 시작점이다.

### 6.7 Recipe

| Field | Type | 설명 |
|---|---|---|
| `recipe_id` | string | Recipe ID |
| `recipe_version` | string | Version |
| `operation_id` | string | 대상 operation |
| `equipment_group_id` | string | 대상 장비군 |
| `approval_status` | enum | DRAFT, APPROVED, LOCKED, RETIRED |
| `parameter_set` | json | recipe parameter |
| `control_limits` | json | 허용 범위 |
| `download_status` | enum | NOT_DOWNLOADED, DOWNLOADED, VERIFIED |
| `compare_result` | enum | MATCH, MISMATCH, UNKNOWN |

현재 `recipe: [s1, s2, s3]`, `[r1, r2, r3]`를 MVP recipe parameter로 사용한다.

### 6.8 FeatureSnapshot

AI 입력 snapshot을 저장한다.

| Field | Type | 설명 |
|---|---|---|
| `feature_snapshot_id` | string | Feature snapshot ID |
| `correlation_id` | string | decision chain ID |
| `layer_id` | enum | L1, L2, L3, L4 |
| `source` | string | simulator, MES, event_replay |
| `decision_state` | json | `get_decision_state()` 또는 MES DTO |
| `features` | json | 모델 입력 feature |
| `created_at` | datetime | 생성 시간 |

### 6.9 AIRecommendation

AI 추천은 모든 layer에서 동일한 envelope로 저장한다.

| Field | Type | 설명 |
|---|---|---|
| `recommendation_id` | string | 추천 ID |
| `recommendation_type` | enum | OBJECTIVE, STAGE_PRIORITY, DISPATCH, RECIPE, MAINTENANCE, PACK |
| `layer_id` | enum | L1, L2, L3, L4 |
| `objective_id` | string | 적용된 fab-level objective |
| `policy_id` | string | 사용된 policy/config ID |
| `model_id` | string | 모델 ID |
| `model_version` | string | 모델 버전 |
| `feature_snapshot_id` | string | 입력 feature snapshot |
| `parent_recommendation_id` | string | 상위 layer 추천 ID |
| `correlation_id` | string | 전체 decision chain ID |
| `candidate_actions` | json | 후보 action 목록 |
| `recommended_action` | json | 추천 action |
| `score` | number | 추천 score |
| `confidence` | number | confidence |
| `reasons` | array | 추천 근거 |
| `rule_validation_status` | enum | PENDING, PASSED, REJECTED, OVERRIDDEN |
| `rule_validation_reasons` | array | 거절/수정 사유 |
| `final_command_id` | string | 실행 command |
| `created_at` | datetime | 생성 시간 |

### 6.10 Event

| Field | Type | 설명 |
|---|---|---|
| `event_id` | string | Event ID |
| `event_type` | string | OBJECTIVE_SELECTED, DISPATCH_RECOMMENDED, TRACK_IN 등 |
| `timestamp` | datetime | 발생 시각 |
| `correlation_id` | string | decision chain ID |
| `recommendation_id` | string | 연결 추천 |
| `parent_recommendation_id` | string | 상위 추천 |
| `layer_id` | enum | L1, L2, L3, L4 |
| `lot_id` | string | Lot |
| `wafer_ids` | array | Wafer 목록 |
| `equipment_id` | string | 장비 |
| `operation_id` | string | 공정 |
| `recipe_id` | string | Recipe |
| `actor_type` | enum | SYSTEM, OPERATOR, AI, RULE_ENGINE |
| `payload` | json | 상세 데이터 |

### 6.11 Genealogy

| Field | Type | 설명 |
|---|---|---|
| `genealogy_id` | string | Genealogy record |
| `parent_entity_type` | string | Lot, Wafer, Material, Carrier |
| `parent_entity_id` | string | Parent ID |
| `child_entity_type` | string | Output type |
| `child_entity_id` | string | Child ID |
| `operation_id` | string | 생성/변환 공정 |
| `equipment_id` | string | 장비 |
| `event_id` | string | 연결 event |
| `correlation_id` | string | decision chain ID |
| `timestamp` | datetime | 발생 시각 |

---

## 7. MES 주요 모듈

### 7.1 Lot / Wafer Management

기능:

- Create Lot
- Release Lot
- Hold Lot
- Release Hold
- Split Lot
- Merge Lot
- Scrap Wafer
- Rework Lot
- Change Priority
- Change Route
- Reserve Lot
- Track-In
- Track-Out

Track-In 검증:

- Lot 상태가 WAIT 또는 RESERVED인지
- Hold 상태가 아닌지
- 현재 Operation이 맞는지
- Equipment가 해당 Operation을 처리 가능한지
- Equipment 상태가 IDLE 또는 RESERVED인지
- Carrier 위치가 장비 port와 일치하는지
- Recipe가 승인되었는지
- Recipe가 장비에 존재하고 compare가 통과했는지
- Queue Time 제약을 위반하지 않는지
- Batch 조건이 충족되었는지
- AI 추천 chain의 `correlation_id`가 유효한지

### 7.2 WIP Tracking

조회 기준:

- 공정별 WIP
- 제품별 WIP
- Lot 상태별 WIP
- 장비별 대기 Lot
- Queue Time 위험 Lot
- 납기 위험 Lot
- Hold Lot
- Rework Lot
- AI 추천 대기 Lot
- 예약되었지만 Track-In되지 않은 Lot

### 7.3 Equipment Management

관리 항목:

- Equipment ID
- Equipment Group
- Process Capability
- Current Status
- Current Lot
- Reserved Lot
- Current Recipe
- Chamber Status
- Alarm Status
- PM Schedule
- Utilization
- MTBF / MTTR
- Health State
- Last Event Time

### 7.4 Recipe / APC Management

기능:

- Recipe 등록
- Version 관리
- Approval / Lock
- Equipment mapping
- Parameter limit 검증
- Recipe download status 관리
- Recipe compare
- Layer 2 recipe recommendation 검증
- APC 결과와 품질 결과 연결

### 7.5 Genealogy / Traceability

추적 대상:

- Product -> Lot -> Wafer
- Wafer -> Operation 이력
- Operation -> Equipment / Chamber
- Operation -> Recipe version
- Operation -> QA result
- Layer 4 objective -> Layer 3 priority -> Layer 1 dispatch -> Layer 2 recipe
- Recommendation -> Rule validation -> Command -> Event
- Rework parent/child 관계
- Scrap 원인

---

## 8. Dispatching 설계

Dispatching은 "어떤 Lot/Wafer를 어떤 Equipment에 먼저 투입할지" 결정하는 기능이다. 본 설계에서는 Dispatching을 다음 단계로 나눈다.

```text
1. Candidate Generation
2. Layer 4 Objective Selection
3. Layer 3 Stage Priority Recommendation
4. Layer 1 Dispatch Ranking / Recommendation
5. Layer 2 Recipe/APC Recommendation
6. Rule Engine Validation
7. Reservation / Track-In
```

### 8.1 Candidate Generation

입력:

- 현재 operation의 WAIT Lot/Wafer
- Rework 대상
- Equipment group
- Equipment status
- Recipe availability
- Queue time
- Due date
- Carrier location
- Batch size

후보 제외 조건:

- Hold 상태
- Operation 불일치
- Equipment capability 불일치
- Recipe 미승인
- Carrier 위치 불일치
- Queue time hard violation
- 동일 cycle 내 중복 할당
- 장비 DOWN/PM/QUAL 상태

### 8.2 Recommendation Envelope

AI 출력은 단순 action JSON이 아니라 MES가 검증할 recommendation envelope이다.

공통 필드:

```json
{
  "recommendation_id": "REC_L1_001",
  "recommendation_type": "DISPATCH",
  "layer_id": "L1",
  "objective_id": "OBJ_THROUGHPUT_YIELD_BALANCED",
  "policy_id": "POLICY_DISPATCH_RANKER_V1",
  "model_id": "dispatch-ranker",
  "model_version": "0.1.0",
  "feature_snapshot_id": "FS_L1_001",
  "parent_recommendation_id": "REC_L3_001",
  "correlation_id": "CORR_001",
  "candidate_actions": [],
  "recommended_action": {},
  "score": 0.91,
  "confidence": 0.84,
  "reasons": [],
  "rule_validation_status": "PENDING"
}
```

### 8.3 Layer별 Envelope 예시

#### Layer 4 Objective

```json
{
  "recommendation_id": "REC_L4_001",
  "recommendation_type": "OBJECTIVE",
  "layer_id": "L4",
  "objective_id": "OBJ_BALANCED_001",
  "policy_id": "FAB_OBJECTIVE_POLICY_BASELINE",
  "model_id": "objective-selector",
  "model_version": "0.1.0",
  "feature_snapshot_id": "FS_L4_001",
  "parent_recommendation_id": null,
  "correlation_id": "CORR_001",
  "candidate_actions": [
    {"objective_id": "OBJ_THROUGHPUT_FIRST"},
    {"objective_id": "OBJ_YIELD_FIRST"},
    {"objective_id": "OBJ_BALANCED_001"}
  ],
  "recommended_action": {
    "objective_id": "OBJ_BALANCED_001",
    "weights": {
      "throughput": 1.0,
      "yield": 1.0,
      "tardiness": 0.5,
      "cost": 0.2
    }
  },
  "score": 0.88,
  "confidence": 0.82,
  "reasons": ["fab_wip_high", "yield_risk_normal"],
  "rule_validation_status": "PENDING"
}
```

#### Layer 3 Stage Priority

```json
{
  "recommendation_id": "REC_L3_001",
  "recommendation_type": "STAGE_PRIORITY",
  "layer_id": "L3",
  "objective_id": "OBJ_BALANCED_001",
  "policy_id": "WIP_ORCHESTRATOR_BASELINE",
  "model_id": "stage-priority-model",
  "model_version": "0.1.0",
  "feature_snapshot_id": "FS_L3_001",
  "parent_recommendation_id": "REC_L4_001",
  "correlation_id": "CORR_001",
  "candidate_actions": [
    {"stage": "A", "priority": 0.5},
    {"stage": "B", "priority": 0.8},
    {"stage": "C", "priority": 0.3}
  ],
  "recommended_action": {
    "stage_priorities": {
      "A": 0.5,
      "B": 0.8,
      "C": 0.3
    },
    "focus_reason": "B_bottleneck_and_rework_pressure"
  },
  "score": 0.86,
  "confidence": 0.8,
  "reasons": ["b_queue_high", "rework_pool_increasing"],
  "rule_validation_status": "PENDING"
}
```

#### Layer 1 Dispatch

```json
{
  "recommendation_id": "REC_L1_001",
  "recommendation_type": "DISPATCH",
  "layer_id": "L1",
  "objective_id": "OBJ_BALANCED_001",
  "policy_id": "DISPATCH_RANKER_FIFO_PLUS_DUE",
  "model_id": "dispatch-ranker",
  "model_version": "0.1.0",
  "feature_snapshot_id": "FS_L1_001",
  "parent_recommendation_id": "REC_L3_001",
  "correlation_id": "CORR_001",
  "candidate_actions": [
    {
      "lot_id": "LOT_001",
      "wafer_ids": ["W001"],
      "equipment_id": "CLEAN_01",
      "operation_id": "CLEAN_100"
    }
  ],
  "recommended_action": {
    "lot_id": "LOT_001",
    "wafer_ids": ["W001"],
    "equipment_id": "CLEAN_01",
    "operation_id": "CLEAN_100",
    "reservation_ttl_sec": 60
  },
  "score": 0.91,
  "confidence": 0.84,
  "reasons": ["due_date_risk_high", "equipment_idle"],
  "rule_validation_status": "PENDING"
}
```

#### Layer 2 Recipe/APC

```json
{
  "recommendation_id": "REC_L2_001",
  "recommendation_type": "RECIPE",
  "layer_id": "L2",
  "objective_id": "OBJ_BALANCED_001",
  "policy_id": "APC_USAGE_AWARE_BASELINE",
  "model_id": "recipe-apc-model",
  "model_version": "0.1.0",
  "feature_snapshot_id": "FS_L2_001",
  "parent_recommendation_id": "REC_L1_001",
  "correlation_id": "CORR_001",
  "candidate_actions": [
    {
      "recipe_id": "RCP_CLEAN_03",
      "parameters": {"r1": 50.0, "r2": 50.0, "r3": 30.0}
    }
  ],
  "recommended_action": {
    "recipe_id": "RCP_CLEAN_03",
    "parameters": {"r1": 50.0, "r2": 50.0, "r3": 30.0},
    "replace_solution": false
  },
  "score": 0.89,
  "confidence": 0.81,
  "reasons": ["solution_usage_medium", "spec_margin_safe"],
  "rule_validation_status": "PENDING"
}
```

### 8.4 Rule Validation

Rule Engine은 Layer 1 dispatch와 Layer 2 recipe를 함께 검증한다.

```json
{
  "correlation_id": "CORR_001",
  "dispatch_recommendation_id": "REC_L1_001",
  "recipe_recommendation_id": "REC_L2_001",
  "validation_status": "PASSED",
  "validated_command": {
    "command_type": "RESERVE_AND_TRACK_IN",
    "lot_id": "LOT_001",
    "wafer_ids": ["W001"],
    "equipment_id": "CLEAN_01",
    "operation_id": "CLEAN_100",
    "recipe_id": "RCP_CLEAN_03"
  }
}
```

거절 예시:

```json
{
  "validation_status": "REJECTED",
  "reasons": [
    "RECIPE_NOT_APPROVED",
    "CARRIER_NOT_AT_EQUIPMENT_PORT"
  ]
}
```

### 8.5 Simulator Action 변환

검증 통과 후 MVP에서는 simulator action으로 변환한다.

```json
{
  "A": {
    "A_0": {
      "task_uids": [1, 2],
      "recipe": [10.0, 2.0, 1.0],
      "task_type": "new",
      "replace_consumable": false
    }
  }
}
```

---

## 9. AI 입력 Feature

### 9.1 공통 Feature

| Category | Feature |
|---|---|
| Time | current_time, shift, remaining_horizon |
| Lot | lot_id, product_id, priority, due_date, slack, status |
| Wafer | wafer_count, wafer_status, qa history |
| Operation | current_operation, route_step, queue_time_min/max |
| Equipment | status, capability, batch_size, current_recipe, health_state |
| WIP | upstream_wip, current_wip, downstream_wip, rework_wip |
| Quality | spec, previous QA, predicted QA, fail risk |
| Maintenance | consumable usage, solution usage, machine age, PM due |
| Business | customer_id, margin_value, commit risk |
| History | previous dispatch, previous recipe, rework_count |
| Chain | objective_id, parent_recommendation_id, correlation_id |

현재 simulator의 `get_decision_state()`는 MVP feature snapshot의 시작점이다.

```text
time
max_steps
num_completed
tasks
A/B/C.machines
A/B/C.wait_pool_uids
A/B.rework_pool_uids
A/B.finishing_now_uids
B.incoming_from_A_uids
C.incoming_from_B_uids
queue_stats
```

### 9.2 Layer별 Feature Snapshot

- L4: fab KPI, global WIP, throughput gap, yield trend, tardiness trend
- L3: stage별 queue, rework pool, incoming handoff, bottleneck score
- L1: candidate lot/equipment pair, due date, priority, queue time
- L2: selected lot, equipment health, recipe history, spec margin, consumable state

각 layer의 feature는 `feature_snapshot_id`로 저장되고 AIRecommendation과 연결된다.

---

## 10. API 설계

### 10.1 Core MES API

```http
GET /api/v1/lots
GET /api/v1/lots/{lot_id}
GET /api/v1/equipment
GET /api/v1/equipment/{equipment_id}
GET /api/v1/recipes
GET /api/v1/recipes/{recipe_id}
GET /api/v1/wip
GET /api/v1/kpis/fab
GET /api/v1/kpis/ai
```

### 10.2 Decision State API

```http
GET /api/v1/decision-state
POST /api/v1/feature-snapshots
```

MVP에서는 simulator의 `get_decision_state()`를 MES DTO로 변환하고, layer별 feature snapshot을 저장한다.

### 10.3 Dispatch Candidate API

```http
GET /api/v1/dispatch/candidates?operation_id=CLEAN_100
POST /api/v1/dispatch/candidates
```

응답:

```json
{
  "correlation_id": "CORR_001",
  "operation_id": "CLEAN_100",
  "candidates": [
    {
      "lot_id": "LOT_001",
      "wafer_ids": ["W001"],
      "equipment_id": "CLEAN_01",
      "rule_precheck_status": "ELIGIBLE"
    }
  ]
}
```

### 10.4 AI Recommendation API

AI API는 recommendation envelope 형식으로 통일한다.

```http
POST /api/v1/ai/recommendations/objective
POST /api/v1/ai/recommendations/stage-priority
POST /api/v1/ai/recommendations/dispatch
POST /api/v1/ai/recommendations/recipe
POST /api/v1/ai/recommendations/pack
GET  /api/v1/ai/recommendations/{recommendation_id}
GET  /api/v1/ai/recommendations?correlation_id=CORR_001
```

요청:

```json
{
  "correlation_id": "CORR_001",
  "layer_id": "L1",
  "objective_id": "OBJ_BALANCED_001",
  "policy_id": "DISPATCH_RANKER_FIFO_PLUS_DUE",
  "feature_snapshot_id": "FS_L1_001",
  "parent_recommendation_id": "REC_L3_001",
  "candidate_actions": []
}
```

응답은 항상 recommendation envelope이다.

### 10.5 Rule Validation API

```http
POST /api/v1/rules/validate
```

요청:

```json
{
  "correlation_id": "CORR_001",
  "recommendation_ids": ["REC_L1_001", "REC_L2_001"]
}
```

응답:

```json
{
  "correlation_id": "CORR_001",
  "validation_status": "PASSED",
  "validated_command": {},
  "reasons": []
}
```

### 10.6 Command API

```http
POST /api/v1/commands/reserve
POST /api/v1/commands/track-in
POST /api/v1/commands/track-out
POST /api/v1/commands/hold
POST /api/v1/commands/release
```

MVP에서는 command를 simulator action으로 변환한다.

### 10.7 Event / Genealogy API

```http
GET /api/v1/events?lot_id=LOT_001
GET /api/v1/events?correlation_id=CORR_001
GET /api/v1/genealogy/lot/{lot_id}
GET /api/v1/genealogy/wafer/{wafer_id}
```

---

## 11. 이벤트 설계

이벤트는 traceability, genealogy, audit, AI recommendation history를 모두 지원해야 한다. 특히 4-layer decision chain을 `correlation_id`로 연결해야 한다.

### 11.1 핵심 이벤트

- `OBJECTIVE_SELECTED`
- `STAGE_PRIORITY_UPDATED`
- `DISPATCH_RECOMMENDED`
- `RECIPE_RECOMMENDED`
- `PACK_RECOMMENDED`
- `RULE_VALIDATION_PASSED`
- `RULE_VALIDATION_REJECTED`
- `COMMAND_EXECUTED`
- `LOT_RESERVED`
- `TRACK_IN`
- `TRACK_OUT`
- `QA_MEASURED`
- `REWORK_REQUESTED`
- `CONSUMABLE_REPLACED`
- `PACK_COMPLETED`
- `LOT_COMPLETED`

### 11.2 Decision Chain 이벤트 예시

```json
[
  {
    "event_type": "OBJECTIVE_SELECTED",
    "correlation_id": "CORR_001",
    "recommendation_id": "REC_L4_001",
    "layer_id": "L4",
    "payload": {
      "objective_id": "OBJ_BALANCED_001"
    }
  },
  {
    "event_type": "STAGE_PRIORITY_UPDATED",
    "correlation_id": "CORR_001",
    "recommendation_id": "REC_L3_001",
    "parent_recommendation_id": "REC_L4_001",
    "layer_id": "L3",
    "payload": {
      "stage_priorities": {
        "A": 0.5,
        "B": 0.8,
        "C": 0.3
      }
    }
  },
  {
    "event_type": "DISPATCH_RECOMMENDED",
    "correlation_id": "CORR_001",
    "recommendation_id": "REC_L1_001",
    "parent_recommendation_id": "REC_L3_001",
    "layer_id": "L1",
    "lot_id": "LOT_001",
    "equipment_id": "CLEAN_01"
  },
  {
    "event_type": "RECIPE_RECOMMENDED",
    "correlation_id": "CORR_001",
    "recommendation_id": "REC_L2_001",
    "parent_recommendation_id": "REC_L1_001",
    "layer_id": "L2",
    "recipe_id": "RCP_CLEAN_03"
  },
  {
    "event_type": "RULE_VALIDATION_PASSED",
    "correlation_id": "CORR_001",
    "payload": {
      "validated_recommendations": ["REC_L1_001", "REC_L2_001"]
    }
  },
  {
    "event_type": "COMMAND_EXECUTED",
    "correlation_id": "CORR_001",
    "payload": {
      "command_type": "RESERVE_AND_TRACK_IN",
      "command_id": "CMD_001"
    }
  }
]
```

이벤트를 통해 다음 질문에 답할 수 있어야 한다.

- 이 Track-In은 어떤 objective 때문에 실행되었는가?
- 어떤 stage priority가 dispatch에 영향을 주었는가?
- dispatch 추천과 recipe 추천은 같은 chain에 속하는가?
- Rule Engine은 어떤 추천을 통과 또는 거절했는가?
- AI 추천이 실제 KPI 개선으로 이어졌는가?

---

## 12. KPI 설계

### 12.1 Fab-Level KPI

| KPI | 설명 |
|---|---|
| Throughput | 단위 시간당 완료 Lot/Wafer |
| WIP | 공정별/제품별 재공 |
| Cycle Time | Release부터 완료까지 시간 |
| Lead Time | Arrival부터 completion까지 시간 |
| Tardiness | Due date 초과 시간 |
| Equipment Utilization | 장비 가동률 |
| Bottleneck Score | 병목 공정 지표 |
| OTD / OTIF | 납기 준수율 |

### 12.2 Process-Level KPI

| KPI | 설명 |
|---|---|
| First Pass Yield / FPR | 최초 통과율 |
| Rework Rate | 재작업 비율 |
| Spec Violation Rate | 품질 spec 위반율 |
| Queue Time Violation | queue time 위반 건수 |
| Recipe Change Count | recipe 변경 횟수 |
| Consumable Replacement Count | 소모품/solution 교체 횟수 |
| Pack Quality | pack 단위 품질 |
| Pack Compatibility | pack 조합 적합도 |

### 12.3 AI-Level KPI

| KPI | 설명 |
|---|---|
| Recommendation Acceptance Rate | AI 추천이 Rule Engine을 통과한 비율 |
| Recommendation Rejection Rate | Rule 위반으로 거절된 비율 |
| Override Rate | 운영자 override 비율 |
| Layer Chain Completion Rate | L4 -> L3 -> L1 -> L2 -> Command chain이 완성된 비율 |
| Parent Link Missing Rate | parent recommendation 연결 누락 비율 |
| Prediction Error | 예측 품질/소요시간과 실제 결과 차이 |
| Ranking Hit Rate | 추천 top-k가 실제 좋은 결과였는지 |
| Inference Latency | AI 응답 시간 |
| Safety Violation Count | AI 추천이 hard rule을 위반한 횟수 |
| Policy Uplift | baseline 대비 throughput/yield/tardiness 개선 |

---

## 13. 화면 목록

### 13.1 Fab Dashboard

- 전체 WIP
- 공정별 WIP
- 장비 상태
- throughput
- yield
- tardiness
- 현재 active objective
- AI 추천 승인/거절 현황

### 13.2 Process Detail

- 선택 공정
- 대기 Lot
- 예약 Lot
- RUN 중 Lot
- 사용 가능 장비
- 장비별 현재 recipe
- 장비별 잔여 시간
- queue time 위험 Lot
- stage priority
- AI 추천 투입 Lot

### 13.3 Dispatch Board

- Equipment별 후보 Lot
- AI ranking
- parent objective/stage priority
- Rule validation result
- operator approve/reject
- reservation/track-in 실행 상태

### 13.4 Lot Genealogy

- Lot/Wafer route history
- Operation 이력
- Recipe 이력
- Equipment 이력
- QA 결과
- Rework 이력
- AI recommendation chain
- Rule validation 및 command 이력

### 13.5 AI Recommendation Monitor

- `correlation_id`
- recommendation chain tree
- layer별 추천
- 입력 feature snapshot
- 추천 action
- score/confidence
- Rule validation 결과
- 실행 command
- 실제 결과 KPI

---

## 14. 기술 스택

Simulator-backed MVP 기본값:

| Layer | Stack |
|---|---|
| Backend API | FastAPI |
| Database | PostgreSQL |
| Cache / Lock / Reservation TTL | Redis |
| Event Streaming | Kafka 또는 Redpanda |
| AI Serving | Python FastAPI service |
| Optimization | OR-Tools |
| ML / RL | PyTorch |
| Simulator Adapter | 현재 `ManufacturingEnv` wrapper |
| Frontend | React 또는 Next.js |
| Observability | OpenTelemetry, Prometheus, Grafana |
| Experiment Tracking | MLflow 또는 lightweight DB table |

MVP에서는 Kafka/Redpanda를 생략하고 PostgreSQL event table로 시작할 수 있으나, schema는 event-driven 확장을 고려해 설계한다.

---

## 15. MVP 개발 순서

### 현재 구현 상태 스냅샷

2026-04-30 기준 현재 repository에는 production MES가 아니라
simulator-backed MES shell의 첫 실행 축이 구현되어 있다.

구현 완료 또는 골격 완료:

- `src/mes/domain.py`: Product, Lot, Wafer, Equipment, Recipe,
  FeatureSnapshot, AIRecommendation, Event, Genealogy, RuleValidation,
  MESCommand DTO
- `src/mes/adapters.py`: simulator `get_decision_state()`를 MES DTO로 변환하고
  validated command를 `ManufacturingEnv.step(actions)` payload로 변환
- `src/mes/rule_engine.py`: L1 dispatch/pack 추천과 L2 recipe 추천을 함께
  검증하고 `RESERVE_AND_TRACK_IN` command 생성
- `src/mes/harness.py`: `planner -> generator -> evaluator` 개발 하네스
  구현. 현재 rule-only baseline이지만 `L4 -> L3 -> L1 -> L2` parent chain을
  실제 recommendation envelope로 생성
- `src/mes/store.py`: in-memory audit store. FeatureSnapshot,
  AIRecommendation, RuleValidation, MESCommand, Event를 `correlation_id`로 기록
- `src/mes/sqlite_store.py`: local SQLite audit DB. 현재 MVP에서는
  `data/mes_mvp.sqlite3`에 recommendation, validation, command, event payload를
  저장하고, 이후 PostgreSQL schema로 확장한다.
- `MESDevelopmentHarness.run_and_step(env)`: Rule Engine과 evaluator를 통과한
  command만 simulator에 실행하고 `COMMAND_EXECUTED` 이벤트 기록
- `src/mes/api.py`: FastAPI MES MVP surface. `/api/v1/wip`,
  `/api/v1/equipment`, `/api/v1/kpis/fab`, `/api/v1/ai/recommendations`,
  `/api/v1/events`, `/api/v1/dispatch/candidates`, `/api/v1/rules/validate`,
  `/api/v1/commands/track-in/*`와 live simulation endpoint 제공
- `/mes`: `DESIGN.md` 기준 live control room. Browser polling을 통해
  simulator time, WIP, yield proxy, throughput, equipment state, active
  decision chain, event timeline을 갱신한다.
- `AUTO` run cycle: C -> B -> A 우선순위로 ready stage를 찾아 한 simulator
  tick 안에 validated action을 실행한다. 주기적으로 새 task/lot을 생성할 수
  있다.
- `DESIGN.md`, `sandox/mes_control_room_scrappy.html`: API 이전 운영 화면
  방향과 정적 control room prototype

아직 미구현:

- PostgreSQL/Redis persistence
- 실제 reservation TTL/lock
- event 기반 WIP/KPI 재구성
- full production-grade A -> B -> C multi-cycle command/event integration
- 실제 AI serving, OR-Tools/PyTorch policy
- 운영자 approve/override flow

따라서 다음 backend milestone은 local SQLite MVP를 PostgreSQL repository로
치환 가능한 schema로 정규화하고, reservation/lock/approval flow를 추가하는
것이다.

### Phase 0. Simulator Baseline 고정

산출물:

- `ManufacturingEnv` 실행 wrapper
- `get_decision_state()` 응답 확인
- baseline policy 실행
- event log 확인

검증 기준:

- A -> B -> C 흐름이 깨지지 않음
- duplicate assignment 없음
- 완료 수량과 event log가 일치
- 기존 test suite 통과

### Phase 1. MES Domain API Skeleton

산출물:

- `src/mes/` shell package
- simulator adapter: `get_decision_state()` -> MES DTO
- rule-only dispatch candidate service
- Product/Lot/Wafer/Equipment/Recipe/Event 테이블
- FeatureSnapshot 테이블
- AIRecommendation 테이블
- FastAPI CRUD
- simulator `Task` <-> Lot/Wafer mapping
- `/lots`, `/equipment`, `/recipes`, `/wip`, `/decision-state` API

검증 기준:

- simulator snapshot이 MES DTO로 변환됨
- Lot/Wafer 상태 조회 가능
- Equipment 상태 조회 가능
- 기존 `src/environment/*`와 기존 scheduler/tuner/packer 테스트가 그대로 통과함
- 향후 4-layer AI를 붙일 수 있도록 `layer_id`, `objective_id`, `policy_id`, `feature_snapshot_id`, `parent_recommendation_id`, `correlation_id`를 저장할 수 있음

### Phase 2. Dispatch Candidate + Rule Engine

산출물:

- `/dispatch/candidates` API
- Rule validation service
- Reservation model
- Track-In command model
- Rule validation event 저장

검증 기준:

- Hold Lot 제외
- 장비 capability 검증
- recipe approval 검증
- 동일 Lot 중복 예약 방지
- validation reject reason 저장
- 추천이 없어도 rule-only baseline dispatch 가능
- 추천이 있는 경우 `correlation_id`와 recommendation chain을 유지한 채 검증 가능

### Phase 3. AI Recommendation Gateway

산출물:

- recommendation envelope 표준화
- Layer 4 objective recommendation API
- Layer 3 stage priority recommendation API
- Layer 1 dispatch recommendation API
- Layer 2 recipe recommendation API
- `/kpis/ai` API
- ranked candidates 저장
- score/confidence 저장

검증 기준:

- AI 추천이 직접 실행되지 않음
- 모든 추천이 Rule Engine을 거침
- L4 -> L3 -> L1 -> L2 parent chain 저장 가능
- recommendation -> validation -> command -> event correlation 가능
- chain 단위 acceptance/rejection KPI 계산 가능

### Phase 4. Simulator-backed Command Execution

산출물:

- validated command를 `env.step(actions)`로 변환
- Track-In/Track-Out event 생성
- QA result event 생성
- completed/pack event 생성
- event 기반 WIP/KPI 업데이트

검증 기준:

- MES command와 simulator action이 일관됨
- event로 WIP 재구성이 가능함
- genealogy 생성 가능
- `COMMAND_EXECUTED`가 동일 `correlation_id`의 L4/L3/L1/L2 추천과 연결됨
- simulator 실행 결과가 AI recommendation history와 연결됨

### Phase 5. 4-Layer AI Policy 실험

산출물:

- Layer 1 dispatch ranker
- Layer 2 recipe/APC recommender
- Layer 3 WIP-aware meta scheduler
- Layer 4 objective weight config
- KPI 비교 report

검증 기준:

- FIFO/rule baseline 대비 KPI 비교 가능
- AI 추천 acceptance/rejection 측정 가능
- Layer chain completion rate 측정 가능
- throughput, yield, tardiness trade-off 분석 가능

### Phase 6. 운영 화면 MVP

산출물:

- Fab dashboard
- Process detail
- Dispatch board
- Lot genealogy
- AI recommendation monitor

검증 기준:

- operator가 AI 추천, rule 결과, 실행 이력을 한 화면에서 추적 가능
- 특정 Lot의 전체 genealogy를 event 기반으로 조회 가능
- 특정 command의 L4 -> L3 -> L1 -> L2 decision chain을 확인 가능

---

## 16. 한계와 확장 방향

현재 workspace는 연구용 제조 시뮬레이터이다. 다음 한계가 있다.

- 실제 반도체 장비 SECS/GEM 동작을 모델링하지 않는다.
- 실제 fab route의 수백/수천 step re-entry를 그대로 표현하지 않는다.
- 공정 물리 모델은 단순화되어 있다.
- 실제 sensor, metrology, chamber, reticle, carrier 제약은 축약되어 있다.
- production MES의 권한, recipe approval workflow, fault handling은 별도 구현이 필요하다.

확장 방향:

- 실제 route/operation master data 연결
- Lot/Wafer/Carrier 단위 상태 모델 강화
- Equipment adapter 추가
- Recipe approval/download/compare workflow 구현
- 공정별 surrogate model 또는 digital twin model 연결
- Queue time, chamber matching, setup, PM, reticle 제약 추가
- AI 추천을 decision-support로 먼저 운영한 뒤 제한적 auto-dispatch로 확장
- 실적 event 기반 offline learning 및 policy evaluation 구축

---

## 17. 결론

본 설계는 현재 다공정 제조 시뮬레이터의 `Task`, `Machine`, `get_decision_state()`, scheduler, tuner, packer, meta scheduler를 반도체 MES 용어와 운영 구조로 확장한다.

핵심은 AI가 장비를 직접 제어하는 것이 아니라, 4-layer 의사결정 구조 안에서 추천을 생성하고 MES Rule Engine이 이를 검증한 뒤 command를 실행하는 것이다.

특히 모든 추천은 `layer_id`, `objective_id`, `policy_id`, `feature_snapshot_id`, `parent_recommendation_id`, `correlation_id`를 통해 하나의 decision chain으로 추적된다. 이를 통해 Layer 4 objective가 Layer 3 stage priority, Layer 1 dispatch, Layer 2 recipe/APC 추천을 거쳐 실제 command와 KPI 결과로 이어지는 과정을 audit 가능하게 만든다.

따라서 MVP는 production MES를 한 번에 구현하는 것이 아니라, simulator-backed MES로 시작해 AI 추천, Rule 검증, event traceability, genealogy, KPI 비교를 먼저 완성하고 이후 실제 장비/공정 데이터와 연결하는 방향으로 개발한다.
