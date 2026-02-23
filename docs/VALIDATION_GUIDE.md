# Validation Guide

## 1. 대상
- `tests/test_gantt_validation.py`
- `scripts/generate_gantt_chart_v3.py`

## 2. 시나리오 정책
- Scenario 1 (deterministic): `expect_rework=False`
- Scenario 2 (stochastic): `expect_rework=True`
- Scenario 3 (deterministic): `expect_rework=False`

## 3. ValidationReport 정책
`validate_sync(..., expect_rework=False)`
- `expect_rework=False`: rework 미발생을 실패로 보지 않음
- `expect_rework=True`: rework가 전혀 없으면 이슈로 기록

## 4. Gantt 생성
- 테스트 파일에서 이벤트 로그 기반으로 직접 생성
- 축 정의:
  - X축: time step
  - Y축: 공정 순서별 머신(`A_*`, `B_*`, `C_*`)
- 박스:
  - 시작: task assigned 시각
  - 종료: task finished 시각
  - 라벨: `task_uid`, A rework는 `task_uid(Rn)`

## 5. 실행 명령
```bash
python -m py_compile src/environment/manufacturing_env.py
python -m py_compile scripts/generate_gantt_chart_v3.py
python -m py_compile tests/test_gantt_validation.py
python -m tests.test_gantt_validation
```

## 6. 기대 결과
- 인코딩 오류 없이 완료
- 시나리오별 rework 정책 반영
- `results/scenario*_gantt_direct.png` 생성
