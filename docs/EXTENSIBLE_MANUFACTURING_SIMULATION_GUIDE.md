# Extensible Manufacturing Simulation Toolkit Guide

This document explains the current codebase as a modular research toolkit for manufacturing simulation.

Primary goal:
- Share a practical environment that other researchers can simulate immediately.
- Make it easy to extend to new processes, new scheduling algorithms, and new recipe tuning or advanced process control methods.

This guide is written against the current `src` implementation.

## 1. Vision and Design Principles

The project is organized as a modular "box" with clear boundaries:

- `Env` is for state transitions.
- `Scheduler` is for assignment decisions.
- `Tuner` is for recipe decisions.
- `Meta Scheduler` orchestrates all decisions and sends actions to the environment.

This separation helps research in:
- Pure scheduling studies.
- Process control and recipe optimization studies.
- Joint scheduling + control studies.
- Multi-objective packing/dispatch studies.

## 2. Process Flow and Runtime Loop

The system runs as `A -> B -> C` in a global discrete-time loop.

![Simulation Process Flow](figures/process_flow.png)

Recommended loop pattern:

```python
from src.environment.manufacturing_env import ManufacturingEnv
from src.agents.factory import build_meta_scheduler

config = {
    "num_machines_A": 2,
    "num_machines_B": 2,
    "num_machines_C": 1,
    "batch_size_A": 2,
    "batch_size_B": 1,
    "batch_size_C": 4,
    "scheduler_A": "fifo",
    "scheduler_B": "rule-based",
    "packing_C": "greedy",
    "max_steps": 100,
}

env = ManufacturingEnv(config)
meta = build_meta_scheduler(env.config)
obs = env.reset()

done = False
while not done:
    state = env.get_decision_state()
    actions = meta.decide(state)
    obs, reward, done, info = env.step(actions)
```

Strict external semantics:
- `env.step({})` means no assignment/packing action (no auto scheduling fallback).
- A/B/C transitions for already running tasks still occur.

## 3. Core Architecture

### 3.1 Env Layer (State Transition Only)

`src/environment/manufacturing_env.py`
- Integrates process A/B/C.
- Applies external actions.
- Executes A, then B, then C transition each step.
- Performs same-step handoff:
  - A success can enter B in the same global step.
  - B success can enter C in the same global step.
- Increments time and computes reward.

Important API:
- `reset(seed_initial_tasks=True, initial_tasks=None)`
- `get_decision_state()`
- `step(actions)`

### 3.2 Decision Layer

`src/agents/default_meta_scheduler.py`
- Reads decision state.
- Builds actions for A/B/C.
- A/B: assignment scheduler + recipe tuner.
- C: packing policy.

Factory:
- `src/agents/factory.py`
- Creates scheduler/tuner/packer stack from config.

### 3.3 Domain Layer

`src/objects.py`
- `Task` dataclass and machine models (`ProcessA_Machine`, `ProcessB_Machine`, `ProcessC_Machine`).

`src/data_generator.py`
- Generates synthetic arrivals (default: one job with 40 tasks).

## 4. Environment Methodology and Behavior

### 4.1 Time-step order and handoff

Within each `ManufacturingEnv.step(actions)`:
1. Process A step runs.
2. A passed tasks are handed to B immediately.
3. Process B step runs.
4. B passed tasks are handed to C immediately.
5. Process C step runs.
6. Optional periodic arrivals occur.
7. Time is incremented.

This ordering is useful for studies requiring tight flow synchronization.

### 4.2 Decision state contract

`get_decision_state()` returns:
- Top level:
  - `time`, `max_steps`, `num_completed`, `tasks`
- Per process:
  - `machines`
  - queue uid lists (`wait_pool_uids`, optional `rework_pool_uids`)
  - `queue_stats`
- Flow hints:
  - B gets `incoming_from_A_uids`
  - C gets `incoming_from_B_uids`

This contract is designed so external controllers can remain process-agnostic.

### 4.3 Action contract (V1)

Action payload:

```python
{
  "A": {
    "A_0": {"task_uids": [1, 2], "recipe": [10.0, 2.0, 1.0], "task_type": "new"}
  },
  "B": {
    "B_0": {"task_uids": [3], "recipe": [50.0, 50.0, 30.0], "task_type": "rework"}
  },
  "C": {
    "C_0": {"task_uids": [4, 5, 6, 7], "reason": "batch_ready"}
  }
}
```

Validation/sanitization behavior:
- Invalid or duplicate UIDs are dropped.
- Only queue-visible UIDs are accepted.
- Missing process actions are treated as no-op.

### 4.4 Event logs for analysis

Each process records event logs used by gantt and validation scripts.

Main event types:
- A/B: `task_assigned`, `task_completed`
- C: `task_queued`, `pack_completed`

These logs are suitable for:
- Timing consistency checks.
- Flow order checks.
- Gantt visualization and overlap validation.

## 5. Physical Models and Where to Edit

### 5.1 Process A model (`src/environment/process_a_env.py`)

Key constants (module level):
- `W1_BASE`, `W2_BASE`, `W3_BASE`, `B_BASE`
- `W12_BASE`
- `BETA`, `BETA_K`
- `GAMMA`, `GAMMA_K`
- `DELTA_W1`, `DELTA_W12`, `DELTA_B`

Core equations:
- Age-adjusted parameters:
  - `w1 = W1_BASE * (1 - DELTA_W1 * m_age)`
  - `w12 = W12_BASE * (1 - DELTA_W12 * m_age)`
  - `b = B_BASE - DELTA_B * m_age`
- Process signal:
  - `g_s = (w1*s1 + W2_BASE*s2 + W3_BASE*s3 + b) + (w12*s1*s2)`
- Effectiveness:
  - `effectiveness = 1 - BETA * tanh(BETA_K * u)`
- Mean QA:
  - `mean_qa = g_s * effectiveness`
- Noise scale:
  - `std = GAMMA * tanh(GAMMA_K * u)`

Pass criterion:
- Inclusive boundary: `spec_a_min <= realized_qa <= spec_a_max`

Edit here if you want:
- New degradation models.
- Different nonlinear terms.
- Different stochastic process.

### 5.2 Process B model (`src/environment/process_b_env.py`)

Key constants (module level):
- `ALPHA`, `BETA`, `MIN_QA`, `MAX_QA`

Current simplified QA logic:
- Recipe average creates `base_quality`.
- Machine state `v` impacts effectiveness.
- `b_age` applies extra degradation.
- Output is clipped to `[MIN_QA, MAX_QA]`.

Pass criterion:
- Strict boundary: `spec_b_min < realized_qa < spec_b_max`

Edit here if you want:
- Full physical chemistry model.
- Multi-sensor measurement model.
- Time-varying quality drift.

### 5.3 Process C scoring/compatibility (`src/environment/process_c_env.py`)

Core methods:
- `_init_compatibility_matrix`
- `_compute_compatibility`
- `_create_pack_info`

Edit here if you want:
- New compatibility definitions.
- New pack quality objectives.
- Additional constraints (customer-level, due-date, thermal, etc.).

## 6. Scheduler Layer

### 6.1 What scheduler means in this code

Schedulers in `src/schedulers/schedulers_a.py` and `src/schedulers/schedulers_b.py` are assignment-only.

They decide:
- Which UIDs to assign now.
- Rework vs new priority.
- Batch content by machine batch size.

They do not decide recipe values (that is handled by tuners).

### 6.2 Existing schedulers

Process A:
- `FIFOScheduler`
- `AdaptiveScheduler` (assignment behavior currently rework-priority FIFO)
- `RLBasedScheduler` (placeholder with FIFO fallback)

Process B:
- `FIFOBaseline`
- `RuleBasedScheduler` (assignment behavior currently rework-priority FIFO)
- `RLBasedScheduler` (placeholder with rule-based fallback)

### 6.3 Batch scheduling and general scheduling

Batch behavior is controlled by machine `batch_size`.

Examples:
- Single-item dispatch:
  - `batch_size_A=1`, `batch_size_B=1`, `batch_size_C=1`
- Small batch flow:
  - `batch_size_A=2`, `batch_size_B=1`, `batch_size_C=4`
- Large batch stress test:
  - `batch_size_A=5`, `batch_size_B=3`, `batch_size_C=5`

This means the same scheduler interface supports:
- Classic single-task dispatching.
- Batch dispatching.
- Rework-priority dispatching.

### 6.4 Research extensions possible now

Scheduler extensions can implement:
- Due-date-first dispatch.
- Slack-time dispatch.
- Margin-aware dispatch.
- Rework debt balancing.
- Machine-health-aware dispatch using `u`, `m_age`, `v`, `b_age`.
- Multi-objective queue selection.
- Learned dispatch policy (RL, imitation, LLM policy).

## 7. Tuner Layer (Recipe / APC Layer)

### 7.1 What tuner means in this code

Tuners in `src/tuners` produce recipe vectors for selected batches:
- A tuner: `get_recipe(task_rows, machine_state, queue_info, current_time)`
- B tuner: same signature

Tuners can use:
- Machine state (`u`, `m_age`, `v`, `b_age`)
- Queue pressure (`rework_pool_size`, etc.)
- Task specs (`spec_a`, `spec_b`)

### 7.2 Existing tuners

Process A:
- `FIFOTuner`: fixed recipe.
- `AdaptiveTuner`: recipe by machine usage state.
- `RLBasedTuner`: placeholder (fallback to FIFO).

Process B:
- `FIFOTuner`: fixed recipe.
- `RuleBasedTuner`: recipe by solution state and machine age, with spec-dependent scaling.
- `RLBasedTuner`: placeholder (fallback to rule-based).

### 7.3 APC and advanced control opportunities

This layer is a natural place to add APC-style methods:
- Run-to-run control.
- Model predictive control (MPC).
- Robust control with uncertainty bounds.
- Bayesian optimization for recipe setpoints.
- Contextual bandits for recipe adaptation.
- Constrained RL for quality/spec guarantees.
- Digital twin parameter adaptation.

Because assignment and tuning are separated, you can test:
- "same scheduler + different controller"
- "same controller + different scheduler"
- "joint policies" inside a custom meta scheduler

## 8. C Packing Policies

Packers live in `src/schedulers/packers_c.py`:
- `FIFOPacker`
- `RandomPacker`
- `GreedyScorePacker`

Common pack trigger logic:
- Minimum queue requirement (`min_queue_size`)
- Timeout trigger (`max_wait_time`)
- Full batch trigger (`batch_size_C`)

`GreedyScorePacker` score uses:
- quality, compatibility, margin, and due-time penalty weights.

## 9. Configuration Parameter Tables

### 9.1 Core simulation parameters

| Parameter | Type | Default | Where used | Description |
|---|---:|---:|---|---|
| `num_machines_A` | int | 10 | `ProcessA_Env` | Number of A machines |
| `num_machines_B` | int | 5 | `ProcessB_Env` | Number of B machines |
| `num_machines_C` | int | 1 | `ProcessC_Env` | Number of C machines (current default meta uses first machine key for packing action) |
| `process_time_A` | int | 15 | `ProcessA_Env` | A processing duration in steps |
| `process_time_B` | int | 4 | `ProcessB_Env` | B processing duration in steps |
| `process_time_C` | int | n/a | not used in core C env | Reserved/legacy field in some scripts/tests |
| `batch_size_A` | int | 1 | `ProcessA_Env` | Max tasks per A machine assignment |
| `batch_size_B` | int | 1 | `ProcessB_Env` | Max tasks per B machine assignment |
| `batch_size_C` | int | 4 | `ProcessC_Env`, packers, config normalization | Pack size target for C |
| `N_pack` | int | alias | normalization | Alias to `batch_size_C` |
| `max_steps` | int | 1000 | `ManufacturingEnv` | Termination horizon |
| `deterministic_mode` | bool | False | A/B/C envs | If true, disables random QA noise paths |

### 9.2 Meta policy selection parameters

| Parameter | Type | Default | Valid values | Description |
|---|---:|---|---|---|
| `scheduler_A` | str | `fifo` | `fifo`, `adaptive`, `rl` | Assignment scheduler for A |
| `scheduler_B` | str | `rule-based` | `fifo`, `rule-based`, `rl` | Assignment scheduler for B |
| `tuner_A` | str | fallback to `scheduler_A` | `fifo`, `adaptive`, `rl` | Recipe tuner for A |
| `tuner_B` | str | fallback to `scheduler_B` | `fifo`, `rule-based`, `rl` | Recipe tuner for B |
| `packing_C` | str | `greedy` | `fifo`, `random`, `greedy` | Packing policy for C |

### 9.3 A/B tuner parameters

| Parameter | Type | Default | Where used | Description |
|---|---:|---|---|---|
| `default_recipe_A` | list[float] | `[10.0, 2.0, 1.0]` | A FIFO tuner | Fixed A recipe |
| `u_fresh_threshold` | int | 3 | A adaptive tuner | A usage threshold for recipe state |
| `u_medium_threshold` | int | 7 | A adaptive tuner | A usage threshold for recipe state |
| `recipe_a_fresh` | list[float] | `[10.0, 2.0, 1.0]` | A adaptive tuner | Recipe for fresh state |
| `recipe_a_medium` | list[float] | `[12.0, 2.5, 1.2]` | A adaptive tuner | Recipe for medium state |
| `recipe_a_old` | list[float] | `[15.0, 3.0, 1.5]` | A adaptive tuner | Recipe for old state |
| `default_recipe_B` | list[float] | `[50.0, 50.0, 30.0]` | B FIFO tuner | Fixed B recipe |
| `v_fresh_threshold` | int | 5 | B rule-based tuner | B solution usage threshold |
| `v_medium_threshold` | int | 15 | B rule-based tuner | B solution usage threshold |
| `b_age_new_threshold` | int | 10 | B rule-based tuner | B machine-age threshold |
| `b_age_medium_threshold` | int | 50 | B rule-based tuner | B machine-age threshold |

### 9.4 C packer parameters

| Parameter | Type | Default | Where used | Description |
|---|---:|---|---|---|
| `min_queue_size` | int | normalized to `<= batch_size_C` | C env + packers | Minimum queue before pack is considered |
| `max_wait_time` | int | 30 | C env + packers | Timeout threshold for forced packing |
| `random_seed` | int or null | `None` | random packer | Optional deterministic random packing |
| `alpha_quality` | float | 1.0 | greedy packer | Weight for quality term |
| `beta_compat` | float | 0.5 | greedy packer | Weight for compatibility term |
| `gamma_margin` | float | 0.3 | greedy packer | Weight for margin term |
| `delta_time` | float | 0.2 | greedy packer | Weight for due-time penalty |
| `K_candidates` | int | 15 | greedy packer | Top-K candidate pool for combinational search |

### 9.5 Reset-time controls (scenario design)

| Reset argument | Type | Default | Description |
|---|---:|---|---|
| `seed_initial_tasks` | bool | `True` | If true, auto-seeds initial job and enables periodic arrivals |
| `initial_tasks` | list[Task] or `None` | `None` | Explicit initial task set for fully controlled experiments |

## 10. How to Add New Algorithms

### 10.1 Add a new A/B scheduler

Implement `select_batch(wait_pool_uids, rework_pool_uids, batch_size)` in a new class in:
- `src/schedulers/schedulers_a.py` or `src/schedulers/schedulers_b.py`

Example skeleton:

```python
class DueDateScheduler(BaseScheduler):
    def should_schedule(self) -> bool:
        return True

    def select_batch(self, wait_pool_uids, rework_pool_uids, batch_size):
        # You can still keep rework-first semantics if needed.
        # Replace with your own ordering logic.
        return self._select_with_rework_priority(wait_pool_uids, rework_pool_uids, batch_size)
```

Then wire it in `src/agents/factory.py`.

### 10.2 Add a new A/B tuner

Implement `get_recipe(...)` in:
- `src/tuners/tuners_a.py` or `src/tuners/tuners_b.py`

Example skeleton:

```python
class MPCStyleTuner(BaseRecipeTuner):
    def get_recipe(self, task_rows, machine_state, queue_info, current_time):
        # Insert your model/control logic.
        return [11.0, 2.2, 1.1]
```

Then map config key in `src/agents/factory.py`.

### 10.3 Add a new C packer

Implement `should_pack(...)` and `select_pack(...)` in `src/schedulers/packers_c.py`, then map in factory.

### 10.4 Add a fully custom meta scheduler

Subclass `BaseMetaScheduler` (`src/agents/meta_scheduler.py`) and implement:
- `decide(state) -> {"A": ..., "B": ..., "C": ...}`

Use this if you want:
- Joint optimization across A/B/C.
- End-to-end RL policy that bypasses local heuristics.
- Hierarchical controller experiments.

## 11. How to Add a New Process (Example: Process D)

This is the recommended pattern for extending from 3 processes to N processes.

1. Add machine/domain object if needed:
- `src/objects.py` -> `ProcessD_Machine` (if D needs machine-specific state)

2. Add new environment module:
- `src/environment/process_d_env.py`
- Implement at least:
  - `__init__(config)`
  - `reset()`
  - `add_tasks(tasks, current_time=None)`
  - `step(current_time, actions)`
  - `get_state()`
  - `event_log` updates

3. Integrate into top-level orchestrator:
- `src/environment/manufacturing_env.py`
- Add `self.env_D`
- Add transition order and handoff logic in `step(...)`
- Add D snapshots in `get_decision_state()`
- Optionally extend observation schema with `D_state`

4. Add D-level policy modules:
- Scheduler: `src/schedulers/schedulers_d.py` (if assignment needed)
- Tuner: `src/tuners/tuners_d.py` (if recipe/control needed)
- Packer/finalizer policy if D is a final stage

5. Extend meta scheduler:
- Update `decide(...)` to produce `actions["D"]`
- Handle D incoming handoff state fields

6. Extend factory:
- Add config keys and builder paths for D algorithms

7. Add tests:
- Flow consistency (upstream to D)
- No overlap
- Rework semantics (if applicable)
- Gantt/event integrity

## 12. Suggested Experimental Methodologies

The current design supports many experiment styles without changing the environment core:

- Baseline benchmarking:
  - Compare scheduler variants with fixed tuners.
- Controller benchmarking:
  - Compare tuner/APC variants with fixed scheduler.
- Joint optimization:
  - Custom meta scheduler coordinating all stages.
- Robustness tests:
  - deterministic vs stochastic mode.
- Queue stress tests:
  - small batch vs large batch.
- Rework studies:
  - tighten task specs to force rework.
- Packing tradeoff studies:
  - vary greedy weights (`alpha/beta/gamma/delta`) for quality-margin-lateness tradeoffs.
- Domain randomization:
  - vary generator specs, due windows, and arrivals.

## 13. Validation and Regression Commands

Recommended checks:

```bash
conda run -n batch_env python -m tests.test_env_validation_matrix
conda run -n batch_env python -m tests.test_integration
conda run -n batch_env python -m tests.test_gantt_validation
conda run -n batch_env python -m tests.simple_debug_test
```

Useful outputs:
- `results/scenario*_gantt_direct.png`

## 14. Important Current Semantics

- Strict external mode:
  - no action means no new assignment.
- Same-step handoff is enabled by execution order.
- A QA uses inclusive bounds; B QA uses strict bounds.
- C packing is event-based in current implementation.
- `min_queue_size` is normalized to not exceed `batch_size_C`.

## 15. Practical Collaboration Guidance

When sharing this toolkit with other researchers:
- Keep environment API stable (`reset`, `get_decision_state`, `step`).
- Add new logic as pluggable modules first (scheduler/tuner/packer).
- Keep tests close to each new extension.
- Prefer explicit config and factory wiring for reproducibility.
- Record scenario configs in scripts/tests for repeatable experiments.

This structure is intended to be a reusable modular platform for manufacturing research, not a fixed single-use simulator.
