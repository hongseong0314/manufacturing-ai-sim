# Batch Scheduling Toolkit

Extensible manufacturing simulation toolkit with three stages (`A -> B -> C`) and strict external decision control.

- `ManufacturingEnv` handles state transitions only.
- `Meta Scheduler` orchestrates assignments for A/B/C.
- A/B logic is split into assignment schedulers and recipe tuners.
- C logic is pack-policy driven (`should_pack`, `select_pack`).

![Simulation Process Flow](docs/figures/process_flow.png)

## Core Architecture
- `src/environment/manufacturing_env.py`: top-level environment orchestration and handoff.
- `src/environment/process_a_env.py`: process A transition + QA.
- `src/environment/process_b_env.py`: process B transition + QA.
- `src/environment/process_c_env.py`: process C packing/finalization.
- `src/agents/default_meta_scheduler.py`: baseline external orchestration policy.
- `src/agents/factory.py`: scheduler/tuner/packer stack builder from config.
- `src/schedulers/`: assignment schedulers and C packers.
- `src/tuners/`: recipe tuning policies for A/B.

## Runtime Loop (Recommended)
```python
from src.environment.manufacturing_env import ManufacturingEnv
from src.agents.factory import build_meta_scheduler

env = ManufacturingEnv(config)
meta = build_meta_scheduler(env.config)
obs = env.reset()

done = False
while not done:
    state = env.get_decision_state()
    actions = meta.decide(state)  # V1 action schema
    obs, reward, done, info = env.step(actions)
```

## Installation
Minimal runtime dependencies:
```bash
pip install -r requirements.txt
```

Exact locked environment (for strict reproduction):
```bash
pip install -r requirements.lock.txt
```

## Validation
```bash
conda run -n batch_env python -m tests.test_env_validation_matrix
conda run -n batch_env python -m tests.test_integration
conda run -n batch_env python -m tests.test_gantt_validation
conda run -n batch_env python -m tests.simple_debug_test
```

Generated figures are saved under `results/`.

## Documentation
- `docs/EXTENSIBLE_MANUFACTURING_SIMULATION_GUIDE.md`
- `docs/PROJECT_GUIDE.md`
- `docs/VALIDATION_GUIDE.md`
- `docs/model_a_problem_definition.md`
- `docs/model_b_problem_definition.md`
- `docs/model_c_problem_definition.md`
