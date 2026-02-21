# 배치 스케줄링 코드 구현 상세 가이드 (Korean)

이 문서는 현재 저장소의 **실제 구현 코드 기준**으로, 시스템이 어떻게 동작하는지와 각 파일이 어떤 책임을 가지는지 한국어로 상세히 설명합니다.

---

## 1. 문서 목적

이 프로젝트는 `A -> B -> C` 3개 공정을 가진 제조 시뮬레이션 프레임워크입니다.
핵심 목표는 다음과 같습니다.

- 환경(`Env`)은 상태 전이(state transition)만 담당
- 의사결정은 외부(`Meta Scheduler`)에서 수행
- A/B는 **할당(Scheduler)** 과 **레시피 튜닝(Tuner)** 을 분리
- C는 **패킹(Packer)** 정책으로 운영
- 연구자가 정책만 교체해서 실험 가능한 구조

---

## 2. 아키텍처 한눈에 보기

실행 레이어는 다음 순서로 연결됩니다.

1. `ManufacturingEnv.get_decision_state()`로 현재 상태 스냅샷 생성
2. `Meta Scheduler.decide(state)`가 A/B/C action 생성
3. `ManufacturingEnv.step(actions)`가 action 적용 및 A->B->C 전이 수행
4. 관측/보상/종료 여부 반환

핵심 파일:

- `src/environment/manufacturing_env.py`
- `src/environment/process_a_env.py`
- `src/environment/process_b_env.py`
- `src/environment/process_c_env.py`
- `src/agents/default_meta_scheduler.py`
- `src/agents/factory.py`
- `src/schedulers/*.py`
- `src/tuners/*.py`

---

## 3. 실행 루프 (표준 패턴)

```python
from src.environment.manufacturing_env import ManufacturingEnv
from src.agents.factory import build_meta_scheduler

env = ManufacturingEnv(config)
meta = build_meta_scheduler(env.config)
obs = env.reset()

done = False
while not done:
    state = env.get_decision_state()
    actions = meta.decide(state)
    obs, reward, done, info = env.step(actions)
```

이 패턴이 현재 코드의 기준 실행 방식입니다.

---

## 4. 도메인 객체 (`src/objects.py`)

### 4.1 Task

`Task`는 공정 전체를 흐르는 단위 객체입니다.

주요 필드:

- 식별/계획: `uid`, `job_id`, `due_date`
- 품질 규격: `spec_a`, `spec_b`
- 런타임 상태: `location`, `arrival_time`, `rework_count`, `history`
- 품질 결과: `realized_qa_A`, `realized_qa_B`
- 패킹 속성: `material_type`, `color`, `margin_value`, `pack_id`

### 4.2 Machine 계층

- `BaseMachine`: 공통 상태(`idle/busy`, `current_batch`, `finish_time`)
- `ProcessA_Machine`: `m_age`, `u`(소모품 사용량)
- `ProcessB_Machine`: `b_age`, `v`(용액 사용량)
- `ProcessC_Machine`: C 공정 머신 식별자(`C_0`, `C_1`, ...)

---

## 5. 데이터 생성기 (`src/data_generator.py`)

`DataGenerator.generate_new_jobs(current_time)`는 기본적으로 **40개 task**를 생성합니다.

- 4개 포지션 × 10개씩
- `spec_a`, `spec_b`, `due_date`, 재료/색상 등을 랜덤 생성
- `ManufacturingEnv.reset()` 및 주기적 유입(기본 30 step마다)에서 사용

---

## 6. 최상위 환경 (`src/environment/manufacturing_env.py`)

`ManufacturingEnv`는 **Strict External 제어**를 따릅니다.
즉, 내부 자동 스케줄링 없이 외부 action만 적용합니다.

### 6.1 초기화와 config 정규화

`_normalize_config()`에서 교차 공정 파라미터를 정리합니다.

- `batch_size_C` / `N_pack` 정합
- `min_queue_size`를 `<= batch_size_C`로 클램프
- `max_packs_per_step` 기본값 1 보정

### 6.2 내부 stage registry

`_build_stage_registry()`는 내부 구조용 descriptor입니다.

- `A -> B -> C` 연결 정보를 내부적으로 보관
- 외부 API는 기존 A/B/C 형태 유지

### 6.3 step(actions) 동작 순서

1. A step 실행
2. A 성공 task를 B wait pool로 handoff
3. B action sanitize 후 B step 실행
4. B 성공 task를 C wait pool로 handoff
5. C action sanitize 후 C step 실행
6. C 완료분을 `completed_tasks`에 반영
7. (옵션) 주기적 신규 task 생성
8. 시간 증가, obs/reward/done 반환

### 6.4 action sanitize

`_sanitize_actions_for_process()`는 B/C action에 대해 다음을 보장합니다.

- 현재 queue에 존재하는 UID만 허용
- 머신 간 중복 UID 제거
- 잘못된 payload 무시

참고: A action은 현재 process A 내부 검증 로직으로 처리됩니다.

### 6.5 reset(seed=...)

`reset()`에 `seed` 인자가 추가되어 재현성이 중앙에서 제어됩니다.

- `random.seed(seed)`
- `numpy.random.seed(seed)`

### 6.6 get_decision_state()

외부 의사결정용 스냅샷을 반환합니다.

최상위 키:

- `time`, `max_steps`, `num_completed`, `tasks`, `A`, `B`, `C`

`tasks`는 uid 기반 task snapshot dict이고,
A/B/C에는 머신 상태, queue UID, queue 통계가 포함됩니다.

C에는 추가 capability 정보가 포함됩니다.

- `C.capabilities.single_pack_per_step`
- `C.capabilities.multi_machine_active`
- `C.capabilities.max_packs_per_step`

---

## 7. 공정 A (`src/environment/process_a_env.py`)

### 7.1 역할

- 외부 action으로 배치 할당
- 처리 완료 시 QA 판정
- 실패 task는 rework queue로 이동

### 7.2 A QA 모델

코드 상 핵심 식:

- 물리 신호:
  - `g_s = (w1*s1 + W2*s2 + W3*s3 + b) + (w12*s1*s2)`
- 효과 저하:
  - `effectiveness = 1 - BETA * tanh(BETA_K * u)`
- 평균 품질:
  - `mean_qa = g_s * effectiveness`
- 노이즈:
  - `std = GAMMA * tanh(GAMMA_K * u)`

`deterministic_mode=True`면 평균값을 그대로 사용합니다.

### 7.3 통과 규칙

A는 inclusive 경계입니다.

- `spec_a_min <= qa <= spec_a_max`

### 7.4 할당 처리 개선

UID 조회는 step 내에서 `uid -> task` 맵을 만들어 사용하므로,
대기열이 길어져도 반복 선형탐색 부담이 줄어듭니다.

---

## 8. 공정 B (`src/environment/process_b_env.py`)

### 8.1 역할

- 외부 action으로 배치 할당
- 검사 완료 후 QA 판정
- 실패 task는 B rework queue로 이동

### 8.2 B QA 모델 (단순화)

A보다 단순화된 품질 계산을 사용합니다.

- recipe 평균 기반 `base_quality`
- 용액 사용량 `v`, 머신 나이 `b_age` 반영
- `MIN_QA ~ MAX_QA` 범위 클리핑

### 8.3 통과 규칙

B는 strict 경계입니다.

- `spec_b_min < qa < spec_b_max`

### 8.4 할당 처리 개선

A와 동일하게 step 내 `uid -> task` 맵을 사용하여 조회 비용을 줄였습니다.

---

## 9. 공정 C (`src/environment/process_c_env.py`)

### 9.1 역할

- 패킹/최종완료 처리
- task queue 이벤트(`task_queued`)와 pack 이벤트(`pack_completed`) 기록

### 9.2 capability 개념

초기화 시 `capabilities`를 계산해 외부에 노출합니다.

- `single_pack_per_step`: 현재 step당 1팩 모드 여부
- `multi_machine_active`: 다중 C 머신이 실제 활성인지 여부
- `max_packs_per_step`: step당 최대 pack 수

### 9.3 경고 정책

아래 경우 `RuntimeWarning`을 발생시켜 semantics 혼동을 줄입니다.

- `num_machines_C > 1`인데 `max_packs_per_step == 1`
- `process_time_C != 0`인데 현재 instant-pack 모델(시간 소모 미반영)

### 9.4 multi-pack 동작

기본값은 `max_packs_per_step=1`이라 기존 동작과 동일합니다.
옵션으로 `>1`이면 한 step에서 여러 machine action을 처리합니다.

처리 규칙:

- action에서 요청된 pack들을 순서대로 확인
- 중복 UID/유효하지 않은 UID는 제외
- step 내 예산 `min(max_packs_per_step, num_machines)`만큼만 실행

---

## 10. 메타 스케줄러 (`src/agents/default_meta_scheduler.py`)

`DefaultMetaScheduler`는 state를 action으로 변환합니다.

### 10.1 A/B 계획 `_plan_ab_process`

머신별로 다음 절차를 수행합니다.

1. idle(또는 finish_time 경과) 머신 탐색
2. wait/rework 후보 구성
3. scheduler 호출로 batch 선택
4. tuner 호출로 recipe 계산
5. V1 action 생성

### 10.2 scheduler context hook

새 확장 포인트:

- `select_batch_with_context(...)`가 있으면 우선 호출
- 없으면 기존 `select_batch(...)` 호출

context에는 아래가 포함됩니다.

- 후보 task snapshot (`wait_pool_tasks`, `rework_pool_tasks`, `tasks_by_uid`)
- `machine_state`, `queue_info`, `current_time`

### 10.3 C 계획 `_plan_c_process`

- C queue + B에서 finishing_now 유입을 합쳐 후보 구성
- packer의 `should_pack/select_pack`로 pack 결정
- capability 기반 예산(`max_packs_per_step`) 내에서 multi C action 생성

---

## 11. Factory (`src/agents/factory.py`)

`build_meta_scheduler(config)`가 config 키를 읽어 조합합니다.

- A scheduler: `scheduler_A` (`fifo`, `adaptive`, `rl`)
- B scheduler: `scheduler_B` (`fifo`, `rule-based`, `rl`)
- A tuner: `tuner_A` (미지정 시 `scheduler_A` 기반 fallback)
- B tuner: `tuner_B` (미지정 시 `scheduler_B` 기반 fallback)
- C packer: `packing_C` (`fifo`, `random`, `greedy`)

---

## 12. Scheduler/Tuner/Packer 구현 포인트

### 12.1 A/B Scheduler (`src/schedulers/schedulers_a.py`, `src/schedulers/schedulers_b.py`)

기본 정책은 `rework` 우선 + FIFO입니다.

신규 확장 포인트:

- `select_batch_with_context(...)` 오버라이드 가능
- 기본 구현은 기존 `select_batch(...)`로 위임

### 12.2 A/B Tuner (`src/tuners/tuners_a.py`, `src/tuners/tuners_b.py`)

- A: `FIFOTuner`, `AdaptiveTuner`, `RLBasedTuner`
- B: `FIFOTuner`, `RuleBasedTuner`, `RLBasedTuner`

입력 인터페이스는 동일합니다.

- `task_rows`, `machine_state`, `queue_info`, `current_time`

### 12.3 C Packer (`src/schedulers/packers_c.py`)

- `FIFOPacker`: 앞에서부터 배치
- `RandomPacker`: 무작위 선택
- `GreedyScorePacker`: 품질/호환성/마진/시간 페널티 종합 점수

공통 인터페이스:

- `should_pack(wait_pool, current_time, last_pack_time)`
- `select_pack(wait_pool, current_time)`

---

## 13. Action / State 계약

### 13.1 Action (V1)

```python
{
  "A": {
    "A_0": {"task_uids": [1,2], "recipe": [10.0, 2.0, 1.0], "task_type": "new|rework"}
  },
  "B": {
    "B_0": {"task_uids": [3], "recipe": [50.0, 50.0, 30.0], "task_type": "new|rework"}
  },
  "C": {
    "C_0": {"task_uids": [4,5], "reason": "batch_ready|timeout|..."},
    "C_1": {"task_uids": [6,7], "reason": "batch_ready|timeout|..."}
  }
}
```

### 13.2 Decision State

`get_decision_state()` 반환 구조 핵심:

- top: `time`, `max_steps`, `num_completed`, `tasks`
- A/B/C: `machines`, `wait_pool_uids`, `queue_stats`
- A/B: `rework_pool_uids`
- B: `incoming_from_A_uids`
- C: `incoming_from_B_uids`, `last_pack_time`, `pack_count`, `capabilities`

---

## 14. 테스트 구조 요약

### 14.1 `tests/test_env_validation_matrix.py`

계약/회귀 테스트를 폭넓게 검증합니다.

- strict external 모드 보장
- same-step handoff (A->B, B->C)
- 중복 할당/오버랩 방지
- rework count 단조성
- decision_state schema
- C semantics warning
- seed 재현성
- context hook backward compatibility
- C multi-pack opt-in 동작

### 14.2 `tests/test_gantt_validation.py`

시나리오 기반 통합 검증 + Gantt 그림 생성.

현재 시나리오:

1. 기본 배치 처리
2. rework 포함 처리
3. 대배치 스트레스
4. 강제 rework
5. C 장비 2대 병렬 패킹

결과 이미지는 `results/scenario*_gantt_direct.png`로 생성됩니다.

### 14.3 `tests/test_integration.py`

결정론/확률론, 스케줄러 비교, packer 비교를 한 번에 실행하는 통합 테스트입니다.

---

## 15. 주요 파라미터 정리

| 키 | 기본/예시 | 설명 |
|---|---|---|
| `num_machines_A` | 1~N | A 장비 수 |
| `num_machines_B` | 1~N | B 장비 수 |
| `num_machines_C` | 1~N | C 장비 수 |
| `process_time_A` | 예: 8, 15 | A 처리 시간 |
| `process_time_B` | 예: 4, 10 | B 처리 시간 |
| `process_time_C` | 현재 비활성 | C는 기본적으로 instant-pack 모델 |
| `batch_size_A` | 예: 1,2,5 | A 머신 배치 크기 |
| `batch_size_B` | 예: 1,2,3 | B 머신 배치 크기 |
| `batch_size_C` | 예: 2,4,5 | C pack 크기 |
| `min_queue_size` | 1~`batch_size_C` | C pack 최소 큐 임계값 |
| `max_wait_time` | 예: 30 | C timeout 트리거 임계 시간 |
| `max_packs_per_step` | 기본 1 | C step당 pack 최대 수(옵션) |
| `scheduler_A` | `fifo/adaptive/rl` | A 할당 정책 |
| `scheduler_B` | `fifo/rule-based/rl` | B 할당 정책 |
| `tuner_A` | `fifo/adaptive/rl` | A recipe 튜너 |
| `tuner_B` | `fifo/rule-based/rl` | B recipe 튜너 |
| `packing_C` | `fifo/random/greedy` | C 패킹 정책 |
| `deterministic_mode` | `True/False` | QA 난수 제거 여부 |
| `max_steps` | 예: 50~150 | 시뮬레이션 종료 step |

---

## 16. 확장 가이드 (실무 체크리스트)

### 16.1 새 Scheduler 추가

1. `src/schedulers/`에 클래스 추가
2. `select_batch()` 구현
3. 필요하면 `select_batch_with_context()` 오버라이드
4. `src/agents/factory.py`에 매핑 추가
5. 테스트에 케이스 추가

### 16.2 새 Tuner 추가

1. `src/tuners/`에 클래스 추가
2. `get_recipe(...)` 구현
3. `factory.py`에 매핑 추가
4. recipe 범위/형식 테스트 추가

### 16.3 새 Packer 추가

1. `src/schedulers/packers_c.py`에 클래스 추가
2. `should_pack()/select_pack()` 구현
3. `factory.py`에 매핑 추가
4. Gantt/validation 시나리오로 검증

### 16.4 C 병렬 패킹 실험

- `num_machines_C > 1`
- `max_packs_per_step > 1`
- `batch_size_C`, `min_queue_size`를 목적에 맞게 조정

---

## 17. 현재 제약과 주의사항

- C는 기본적으로 `process_time_C`를 처리시간으로 사용하지 않습니다(instant-pack).
- `process_time_C != 0`일 때 warning은 의도된 알림입니다.
- A/B는 외부 action이 없으면 자동할당하지 않습니다(Strict External).
- B/C action은 환경에서 sanitize되며, 유효하지 않은 UID는 자동 제거됩니다.

---

## 18. 빠른 실행 명령

```bash
conda run -n batch_env python -m tests.test_env_validation_matrix
conda run -n batch_env python -m tests.test_integration
conda run -n batch_env python -m tests.test_gantt_validation
conda run -n batch_env python -m tests.simple_debug_test
```

---

## 19. 마무리

현재 코드베이스는 다음 원칙을 만족하도록 정리되어 있습니다.

- 환경 전이와 의사결정 분리
- A/B 할당과 튜닝 분리
- C 패킹 정책 모듈화
- backward-compatible 확장 포인트(context hook, multi-pack opt-in)
- 테스트 기반 회귀 검증 체계

즉, 연구자가 정책/알고리즘만 빠르게 교체해서 실험하기 좋은 형태의 제조 시뮬레이션 프레임워크입니다.
