# Extensible Manufacturing Simulation Toolkit

A modular research sandbox for multi-stage manufacturing simulation and decision-making.
Models a three-stage production line (`A → B → C`) where scheduling, recipe control, and
packing decisions are fully decoupled from the environment physics.

---

## Design Philosophy

| Layer | Responsibility | Location |
|---|---|---|
| **Environment** | State transitions, QA physics, event logging | `src/environment/` |
| **Meta Scheduler** | Orchestrates decisions across all three stages | `src/agents/` |
| **Schedulers** | Select which tasks to process next (per stage) | `src/schedulers/` |
| **Tuners** | Select recipes and maintenance timing (A/B) | `src/tuners/` |
| **Packers** | Select pack composition (C) | `src/schedulers/packers_c.py` |

The environment never makes decisions — it only applies them.
Policies interact with the environment exclusively through the state/action contract.

---

## Process Overview

```
[Task Arrivals] → [Process A] → [Process B] → [Process C] → [Completed Packs]
                   Machining    Wet Cleaning   Bin Packing
```

**Process A — Machining / Processing step**
- QA model: `mean_qa = g(s1, s2, s3) × effectiveness(u)`, degraded by machine age `m_age`
- State variables: `u` (consumable wear), `m_age` (machine aging)
- Control: recipe `[s1, s2, s3]` + consumable replacement timing

**Process B — Chemical Cleaning / Wet process step**
- QA model: `mean_qa = 50 + (base_quality − 40) × 0.5 × effectiveness(v)`, degraded by `b_age`
- State variables: `v` (solution usage), `b_age` (machine aging)
- Control: recipe `[r1, r2, r3]` + solution replacement timing

**Process C — Packaging / Bin-packing step**
- No physical QA model — aggregates upstream quality
- Control: pack composition policy (`should_pack`, `select_pack`)
- Default scorer: `Score = α·Quality + β·Compatibility + γ·Margin − δ·TimePenalty`

---

## Project Structure

```
src/
  objects.py                        # Task, Machine dataclasses
  data_generator.py                 # Synthetic job generation
  environment/
    manufacturing_env.py            # Top-level A→B→C orchestration
    process_a_env.py                # Process A physics and QA
    process_b_env.py                # Process B physics and QA
    process_c_env.py                # Process C packing/finalization
  agents/
    meta_scheduler.py               # BaseMetaScheduler interface
    default_meta_scheduler.py       # Reference implementation
    factory.py                      # Build scheduler/tuner/packer stack from config
  schedulers/
    schedulers_a.py                 # A assignment policies (FIFO, Adaptive, RL)
    schedulers_b.py                 # B assignment policies (FIFO, RuleBased, RL)
    packers_c.py                    # C packing policies (FIFO, Random, GreedyScore)
  tuners/
    tuners_a.py                     # A recipe/maintenance policies
    tuners_b.py                     # B recipe/maintenance policies
notebooks/
  01_Process_A_example.ipynb        # Physics model analysis + tuner simulation
tests/
  test_env_validation_matrix.py     # Integrity invariants and regression checks
  test_integration.py               # End-to-end integration test
  test_gantt_validation.py          # Multi-scenario Gantt validation
  simple_debug_test.py              # Lightweight smoke test
docs/
  EXTENSIBLE_MANUFACTURING_SIMULATION_GUIDE.md   # Full handbook
  AI_DEVELOPER_GUIDE.md                          # AI/algorithm developer reference
  VALIDATION_GUIDE.md                            # Validation protocol
results/                            # Generated plots and Gantt charts
```

---

## Installation

```bash
pip install -r requirements.txt
```

For a reproducible locked environment:

```bash
pip install -r requirements.lock.txt
```

Dependencies: `numpy`, `matplotlib`, `seaborn`, `pytest`

---

## Quick Start

```python
from src.environment.manufacturing_env import ManufacturingEnv
from src.agents.factory import build_meta_scheduler

cfg = {
    "num_machines_A": 10,
    "num_machines_B": 5,
    "num_machines_C": 1,
    "batch_size_A": 1,
    "batch_size_B": 1,
    "batch_size_C": 4,
    "scheduler_A": "fifo",        # "fifo" | "adaptive" | "rl"
    "scheduler_B": "rule-based",  # "fifo" | "rule-based" | "rl"
    "packing_C": "greedy",        # "fifo" | "random" | "greedy"
    "max_steps": 100,
}

env = ManufacturingEnv(cfg)
meta = build_meta_scheduler(env.config)
obs = env.reset()

done = False
while not done:
    state = env.get_decision_state()
    actions = meta.decide(state)
    obs, reward, done, info = env.step(actions)

print(f"Completed tasks: {obs['num_completed']}")
```

---

## Key Config Parameters

| Key | Default | Description |
|---|---|---|
| `num_machines_A` | 10 | Number of A machines |
| `num_machines_B` | 5 | Number of B machines |
| `batch_size_A / B / C` | 1 / 1 / 4 | Per-machine batch sizes |
| `process_time_A` | 15 | Steps to complete one A batch |
| `process_time_B` | 4 | Steps to complete one B batch |
| `max_wait_time` | 30 | Max queue wait before forced C pack |
| `max_steps` | 1000 | Simulation horizon |
| `deterministic_mode` | False | Disable stochastic QA noise |
| `scheduler_A` | `fifo` | A assignment policy key |
| `scheduler_B` | `rule-based` | B assignment policy key |
| `packing_C` | `greedy` | C packing policy key |
| `consumable_replace_threshold` | 10 | A consumable replacement threshold (`u`) |
| `solution_replace_threshold` | 20 | B solution replacement threshold (`v`) |

---

## Extending the Toolkit

**Add a new scheduler** — implement `select_batch(...)` in `src/schedulers/schedulers_a.py` or `schedulers_b.py`, then wire the key in `src/agents/factory.py`.

**Add a new tuner/APC method** — implement `get_recipe(...)` and optionally `should_replace_consumable(...)` in `src/tuners/tuners_a.py` or `tuners_b.py`.

**Add a new packer** — implement `should_pack(...)` and `select_pack(...)` in `src/schedulers/packers_c.py`.

**Modify process physics** — edit `_run_qa_check(...)` and `_get_physical_model_params(...)` in the relevant process env module. Keep method signatures and return semantics stable.

See `docs/AI_DEVELOPER_GUIDE.md` for interface contracts and copy-paste templates.
See `docs/EXTENSIBLE_MANUFACTURING_SIMULATION_GUIDE.md` for playbooks, case studies, and parameter reference.

---

## Notebooks

[`notebooks/01_Process_A_example.ipynb`](notebooks/01_Process_A_example.ipynb) — Process A physics analysis:
- Machine age degradation curves
- Consumable wear effect on effectiveness and noise
- Recipe sensitivity (s1, s2, s3 sweeps)
- Joint (m\_age × u) pass/fail heatmap
- Comparative simulation: fixed recipe vs. adaptive tuning + replacement

Output figures are saved to `results/p_a_0*.png`.

---

## Validation

```bash
python -m tests.test_env_validation_matrix   # integrity invariants
python -m tests.test_integration             # end-to-end flow
python -m tests.test_gantt_validation        # scenario Gantt generation
python -m tests.simple_debug_test            # smoke test
```

Expected output: no assertion errors; `results/scenario*_gantt_direct.png` generated.

---

## Documentation

| File | Audience | Contents |
|---|---|---|
| [`docs/EXTENSIBLE_MANUFACTURING_SIMULATION_GUIDE.md`](docs/EXTENSIBLE_MANUFACTURING_SIMULATION_GUIDE.md) | Everyone | Full handbook — architecture, physical models, extension playbooks, parameter reference, case studies, research roadmap |
| [`docs/AI_DEVELOPER_GUIDE.md`](docs/AI_DEVELOPER_GUIDE.md) | Algorithm developers / AI agents | Interface contracts, implementation templates, optimization objectives |
| [`docs/VALIDATION_GUIDE.md`](docs/VALIDATION_GUIDE.md) | Developers | Validation scenario policy and Gantt generation protocol |
