# B공정 문제 정의 (v2 - 최종)

본 문서는 B공정(세정 및 검사)의 수학적 문제 정의를 최종 확정합니다.

## 1. 목표 함수 (Objective Function)

B공정의 목표는 **양품(Good Part)의 통과율을 최대화**하는 동시에, **불량품(Bad Part)이 C공정으로 넘어가는 것을 최소화**하고, **재세정(Rework)으로 인한 부하를 최소화**하는 것입니다.

```
maximize J = w_p * PassRate - w_fp * FalsePassRate - w_r * ReworkLoad
```

- `w_p, w_fp, w_r`: 각 목표의 중요도를 나타내는 가중치.

## 2. 프로세스 흐름 (Process Flow)

B공정은 A공정을 통과한 Task를 받아 2단계 검사를 순차적으로 수행합니다.

1.  **세정 (Cleaning):** 스케줄러에 의해 선택된 레시피로 세정 작업을 수행합니다. 이 결과로 `realized_qa_B`가 결정됩니다.
2.  **품질 검증 (QA):** `realized_qa_B`가 Task의 `spec_b` 범위를 만족하는지 검사합니다.
    - **성공 시:** Task는 C공정 대기열로 이동합니다.
    - **실패 시:** Task는 B공정 재세정 대기열(`rework_pool`)로 이동합니다.
    - `process_b_env.py`의 이전 버전에서는 2단계 확률적 불량 판정을 했으나, 현재는 A공정과 유사한 물리 모델 기반 QA로 통합되었습니다.

## 3. 상태 및 행동 공간 (State & Action Space)

-   **상태 공간 `S_t`:** `len(wait_pool)`, `len(rework_pool)`, 각 장비의 상태(`b_age`, `v`, `status`) 등.
-   **행동 공간 `A_t`:** 스케줄러는 각 유휴 장비에 대해 **어떤 Task를 처리할지**와 **어떤 레시피 `[r1, r2, r3]`를 적용할지** 결정합니다.

## 4. B공정 물리 모델 (v1)

B공정의 품질 `realized_qa_B`는 A공정과 유사하게, 레시피, 장비 나이(`b_age`), 용액 사용량(`v`)에 의해 결정됩니다.

### 4.1. 품질 계산 함수

`realized_qa_B`는 `process_b_env.py`의 `_run_qa_check` 함수에 의해 계산됩니다.

1.  **기본 품질:** `base_quality = (r1 + r2 + r3) / 3.0`
2.  **용액 효율:** `effectiveness = max(0.1, 1.0 - ALPHA * (machine.v / 30.0))`
3.  **평균 기대 품질:** `mean_qa = 50.0 + (base_quality - 40.0) * 0.5 * effectiveness`
4.  **장비 노후화:** `degradation = 1.0 - (machine.b_age / 1000.0) * 0.1`
5.  **노이즈:** `deterministic_mode`가 `False`일 경우, 정규분포 노이즈가 추가됩니다.
6.  **최종 품질:** `realized_qa = (mean_qa * degradation) + Noise` (50~100 범위로 제한)

### 4.2. 파라미터 테이블

| 파라미터 | 현재 값 | 설명 |
|---|---|---|
| `ALPHA` | 0.15 | 용액(`v`) 사용량에 따른 효율 감소율 |
| `BETA` | 1.5 | 품질 노이즈의 표준편차에 영향을 주는 상수 |
| `solution_replacement`| `v >= 20` | 용액 교체 규칙 (하드코딩) |

## 5. 제약 조건 및 규칙

- **재작업 (Rework):** QA 실패 시, 해당 Task는 `rework_pool`로 이동하여 다음 스케줄링에서 우선적으로 고려됩니다.
- **용액 교체 (Solution Replacement):** 현재 `process_b_env.py`에는 `v >= 20`일 경우, 작업 완료 후 자동으로 용액을 교체하는 규칙이 하드코딩되어 있습니다.
