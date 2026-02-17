# C공정 문제 정의 (v2 - 최종)

본 문서는 C공정(팩킹)에서 발생하는 조합 최적화(Combinatorial Optimization) 문제와, 이를 해결하기 위한 평가 기준을 수학적으로 정의합니다.

## 1. 목표 함수 (Objective Function)

C공정의 목표는 `wait_pool`에 대기 중인 Task들 중에서, **정해진 제약 조건들을 만족하는 가장 가치 있는 Task 조합(Pack)을 찾아내는 것**입니다. 이는 다음과 같은 점수 함수 `Score(Pack)`를 최대화하는 문제로 공식화할 수 있습니다.

```
maximize Score(Pack)
subject to:
  1. |Pack| = N_pack (팩 크기 제약)
  2. Compatibility(Pack) >= min_compat (호환성 제약)
```

## 2. 문제 유형 (Problem Type)

-   본질적으로 **집합 포장 문제(Set Packing Problem)** 또는 **배낭 문제(Knapsack Problem)**의 변형입니다.
-   모든 가능한 조합을 탐색하는 것은 계산적으로 매우 비효율적이므로(NP-hard), 현재 시스템은 **탐욕(Greedy) 기반의 휴리스틱(Heuristic) 접근법**을 사용하여 근사 최적해를 찾습니다.

## 3. 의사결정 시점 (Decision Trigger)

`ProcessC_Env`는 `should_pack()` 함수를 통해 언제 팩킹을 시도할지 결정합니다. 다음 조건 중 하나라도 만족하면 팩킹을 시작합니다.

-   **큐 크기 기반 (하한):** `len(wait_pool) >= min_queue_size`
-   **시간 초과 기반 (Timeout):** 대기열에 `max_wait_time` 이상 머무른 Task가 존재할 경우.
-   **큐 크기 기반 (상한):** `len(wait_pool) >= N_pack * 2` (처리 용량의 2배 이상 쌓였을 경우)

## 4. 점수 함수 (Scoring Function)

`GreedyScorePacker`는 각 후보 팩(Pack)의 가치를 평가하기 위해 다음 점수 함수를 사용합니다.

`Score = α*Quality + β*Compatibility + γ*Margin - δ*TimePenalty`

---

### 4.1. 품질 점수 (`Quality`)

-   팩에 포함된 Task들의 B공정 결과 품질(`realized_qa_B`)의 평균값.
-   `Quality = mean([t.realized_qa_B for t in Pack])`
-   **의미:** 고품질 제품들로 구성된 팩을 선호합니다.

### 4.2. 호환성 점수 (`Compatibility`)

-   팩에 포함된 Task들 간의 **재질(material)**과 **색상(color)**이 얼마나 잘 어울리는지를 평가합니다.
-   `Compatibility = mean([Compat(t_i, t_j) for all pairs in Pack])`
-   `Compat(t_i, t_j)`는 `compatibility_matrix`에 사전 정의된 값(0~1)을 조회하여 계산됩니다.
-   **의미:** 동일한 재질과 색상을 가진 Task들로 구성된 팩을 선호합니다.

### 4.3. 마진 점수 (`Margin`)

-   팩에 포함된 Task들의 평균 수익성(`margin_value`).
-   `Margin = mean([t.margin_value for t in Pack])`
-   **의미:** 수익성이 높은 제품들로 구성된 팩을 선호합니다.

### 4.4. 시간 페널티 (`TimePenalty`)

-   팩에 포함된 Task 중, 가장 급한 납기(`due_date`)를 기준으로 현재 시간이 얼마나 지났는지를 평가합니다.
-   `TimePenalty = max(0, current_time - max([t.due_date for t in Pack]))`
-   **의미:** 납기가 임박했거나 이미 지난 Task를 포함한 팩에 페널티를 부여합니다.

### 4.5. 가중치 파라미터

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `alpha_quality` | 1.0 | 품질 점수의 가중치 |
| `beta_compat` | 0.5 | 호환성 점수의 가중치 |
| `gamma_margin` | 0.3 | 마진 점수의 가중치 |
| `delta_time` | 0.2 | 시간 페널티의 가중치 |

---

## 5. 제약 조건 (Constraints)

-   **팩 크기 (Pack Size):** 하나의 팩은 반드시 `N_pack`개의 Task로 구성되어야 합니다.
-   **후보군 제한 (Candidate Limit):** 계산 효율성을 위해, 전체 `wait_pool`이 아닌, 품질(`realized_qa_B`) 기준 상위 `K_candidates`개의 Task들 중에서만 최적 조합을 탐색합니다.
