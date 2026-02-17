# C공정 알고리즘 설계 (v2 - 최종)

본 문서는 C공정(팩킹)에서 대기 중인 Task들로부터 최적의 조합(Pack)을 선택하는 알고리즘들을 정의합니다. 각 알고리즘은 `src/environment/packers_c.py`에 구현된 클래스에 해당합니다.

---

## 1. `FIFOPacker` (Baseline)

가장 간단한 패커로, 다른 모든 지능형 패커의 성능을 비교하기 위한 **성능 최저선(Baseline)** 역할을 합니다.

-   **팩킹 결정 (`should_pack`):**
    -   대기열(`wait_pool`)의 크기가 특정 기준(`min_queue_size`) 이상이거나, 가장 오래 대기한 Task의 대기 시간이 임계값(`max_wait_time`)을 초과하면 팩킹을 시도합니다.
-   **Task 선택 정책 (`select_pack`):**
    -   **선택 방식:** 대기열에 가장 먼저 들어온 순서대로 `N_pack`개의 Task를 선택합니다.
    -   **특징:** 공정의 효율성(처리량)은 높일 수 있으나, 팩의 가치(품질, 호환성 등)는 전혀 고려하지 않습니다. 공평하지만, 비즈니스 가치는 낮을 수 있습니다.

---

## 2. `RandomPacker` (Baseline)

지능형 알고리즘이 최소한 무작위 선택보다는 나아야 함을 증명하기 위한 **통계적 비교 기준선** 역할을 합니다.

-   **팩킹 결정 (`should_pack`):**
    -   `FIFOPacker`와 동일한 규칙을 사용합니다.
-   **Task 선택 정책 (`select_pack`):**
    -   **선택 방식:** 대기열에 있는 전체 Task 중에서 무작위로 `N_pack`개를 선택합니다.
    -   **특징:** 다양한 조합을 시도해볼 수 있으나, 일관된 고품질 팩을 보장할 수 없습니다.

---

## 3. `GreedyScorePacker` (Heuristic Algorithm)

단순한 규칙을 넘어, 정의된 **점수 함수(Scoring Function)**를 기반으로 현재 시점에서 가장 가치 있는 팩을 선택하는 **탐욕(Greedy) 기반의 휴리스틱 알고리즘**입니다.

-   **팩킹 결정 (`should_pack`):**
    -   `FIFOPacker`와 동일한 규칙을 사용합니다.
-   **Task 선택 정책 (`select_pack`):**
    -   **1단계: 후보군 필터링 (Candidate Filtering):**
        -   전체 대기열을 모두 탐색하는 것은 계산량이 많으므로, 먼저 B공정 통과 품질(`realized_qa_B`)이 높은 순으로 상위 `K_candidates`개의 Task를 선별합니다.
    -   **2단계: 모든 조합 탐색 (Combinatorial Search):**
        -   선별된 `K`개의 후보군 내에서, `N_pack` 크기의 모든 가능한 조합(Combination)을 생성합니다.
    -   **3단계: 점수 계산 및 최적 조합 선택 (Scoring & Selection):**
        -   생성된 모든 조합에 대해, `model_c_problem_definition.md`에 정의된 점수 함수 `Score(Pack)`를 사용하여 점수를 계산합니다.
        -   가장 높은 점수를 받은 조합을 최종 팩으로 선택합니다.

-   **기대 동작 및 한계:**
    -   **기대 동작:** FIFO나 Random 방식에 비해 월등히 높은 평균 품질과 가치를 가진 팩을 지속적으로 생성할 것으로 기대됩니다.
    -   **한계:** '현재' 시점의 최적해가 '전체' 시뮬레이션의 최적해를 보장하지는 않습니다. (Greedy 알고리즘의 본질적 한계). 또한, `K_candidates`의 크기에 따라 계산 시간과 성능 간의 트레이드오프가 존재합니다.

---

## 4. 향후 확장 방향 (`Extensions`)

-   **빔 탐색 (Beam Search):** `Greedy` 방식이 놓칠 수 있는 더 나은 조합을 찾기 위해, 상위 N개의 후보 조합을 계속해서 탐색하는 방식을 도입할 수 있습니다.
-   **수학적 최적화 (MIP/CP-SAT):** Task 수가 적은 경우, OR-Tools와 같은 CP-SAT 솔버를 사용하여 전역 최적해(Globally Optimal Solution)를 찾고, 이를 휴리스틱 알고리즘의 성능 상한선으로 활용할 수 있습니다.
-   **강화학습 (Reinforcement Learning):** `should_pack` 결정 자체를 학습하거나, 현재 대기열 상태에 따라 동적으로 점수 함수의 가중치를 변경하는 에이전트를 개발할 수 있습니다.
