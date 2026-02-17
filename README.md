# Batch Scheduling

다중 공정(`A -> B -> C`) 배치 스케줄링 시뮬레이터입니다.  
현재 기준으로 이벤트 로그 기반 검증과 Gantt 시각화가 정리되어 있습니다.

## 현재 핵심 동작
- 공정 오케스트레이션: `A -> B -> C` same-step handoff
- 환경 리셋 옵션:
  - `env.reset()` : 기존 기본 동작 유지(초기 Task 자동 주입)
  - `env.reset(seed_initial_tasks=False)` : 빈 큐로 시작
  - `env.reset(initial_tasks=[...])` : 지정 Task만 주입
- 검증: 이벤트 로그 기반 동기/흐름 검증
- 시각화: 테스트 실행 결과로 direct Gantt PNG 생성

## 주요 파일
- `src/environment/manufacturing_env.py` : 상위 환경 오케스트레이션
- `src/environment/process_a_env.py` : A 공정
- `src/environment/process_b_env.py` : B 공정
- `src/environment/process_c_env.py` : C 공정
- `tests/test_gantt_validation.py` : 시나리오 검증 + direct Gantt 생성
- `scripts/generate_gantt_chart_v3.py` : 이벤트 검증 리포트 유틸

## 실행
```bash
conda run -n batch_env python tests/test_gantt_validation.py
```

## 결과물
테스트 실행 후 `results/` 경로에 아래 파일이 생성됩니다.
- `scenario1_gantt_direct.png`
- `scenario2_gantt_direct.png`
- `scenario3_gantt_direct.png`

## 문제 정의/설계 문서
- [A Problem](docs/model_a_problem_definition.md)
- [A Algorithm](docs/model_a_algorithm_design.md)
- [B Problem](docs/model_b_problem_definition.md)
- [B Algorithm](docs/model_b_algorithm_design.md)
- [C Problem](docs/model_c_problem_definition.md)
- [C Algorithm](docs/model_c_algorithm_design.md)
- [System Event Generation](docs/system_event_generation.md)

## 운영 가이드 문서
- `docs/PROJECT_GUIDE.md` : 아키텍처/동작/설계 요약
- `docs/VALIDATION_GUIDE.md` : 검증 정책, 시나리오, Gantt 해석
