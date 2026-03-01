# Extensible Manufacturing Simulation Toolkit

A researcher's handbook and engineering guide for modular manufacturing simulation, algorithm development, and factory adaptation.

## Preface

Modern manufacturing AI is no longer confined to isolated scheduling heuristics or standalone process control models.
In practice, optimization researchers working in manufacturing environments must design algorithms, validate them through controlled experimentation, and ultimately adapt them to real production systems.

Manufacturing systems can be structurally decomposed into three tightly coupled decision layers:
1. State transition and process physics.
2. Scheduling and dispatching.
3. Process control and recipe adaptation.

These layers interact continuously. Scheduling decisions influence machine degradation and quality outcomes. Process control policies affect throughput and rework. Production planning decisions propagate constraints across multiple stages.
Yet many existing simulators tightly couple these components into a monolithic system, making it difficult to experiment with new optimization strategies without modifying the environment core.

This toolkit is designed specifically for manufacturing AI optimization practitioners — researchers and engineers who both develop algorithms and consider their eventual deployment.
Its primary objective is to separate these decision layers into modular, composable components so that users can:
- Configure a manufacturing environment that reflects their own process structure
- Experiment with scheduling, dispatching, or control algorithms independently
- Study integrated production planning across multiple stages
- Compare policies under controlled and reproducible conditions
- Transition from research prototypes to structured system-level evaluation


The framework does not aim to be a high-fidelity digital twin.
Instead, it provides calibrated process models that exhibit realistic research dynamics — degradation, stochastic variation, rework, quality-throughput tradeoffs — while remaining computationally tractable and modular.


The default production path is `A -> B -> C`, but the architecture is intentionally extensible. New processes, alternative state dynamics, additional control paradigms, and custom objective formulations can be integrated without rewriting the environment core.

This handbook serves both as a research guide and an engineering manual.
It explains the architectural principles, the current implementation, and the extension points necessary for adapting the framework to new optimization problems and manufacturing contexts.

The core philosophy is simple:

Manufacturing AI should not require rebuilding the environment each time a new algorithm is tested.
It should provide a structured decision space where optimization methods can be inserted, evaluated, and compared systematically.
![Simulation Process Flow](figures/process_flow.png)

## Table of Contents

**PART I: Platform Foundation**

1. [Chapter 1. Manufacturing AI as a Multi-Layer Decision System](#chapter-1-manufacturing-ai-as-a-multi-layer-decision-system)
2. [Chapter 2. Runtime Execution Model](#chapter-2-runtime-execution-model)

**PART II: Process Models and Research Surfaces**

3. [Chapter 3. Environment Internals and Physical-Model Customization](#chapter-3-environment-internals-and-physical-model-customization)

**PART III: Connecting Your Factory**

4. [Chapter 4. Factory-to-Simulator Mapping](#chapter-4-factory-to-simulator-mapping)
5. [Chapter 5. KPI Design and Tracking](#chapter-5-kpi-design-and-tracking)

**PART IV: Research Scenarios**

6. [Chapter 6. Research Scenarios](#chapter-6-research-scenarios)

**PART V: Algorithm Extension Space**

7. [Chapter 7. Scheduling Research Extension Space](#chapter-7-scheduling-research-extension-space)
8. [Chapter 8. Tuner, APC, and RL Research Extension Space](#chapter-8-tuner-apc-and-rl-research-extension-space)
9. [Chapter 9. Packing and Multi-Objective Design in Process C](#chapter-9-packing-and-multi-objective-design-in-process-c)

**PART VI: Implementation Guides**

10. [Chapter 10. Extension Playbooks (Engineering Procedures)](#chapter-10-extension-playbooks-engineering-procedures)
11. [Chapter 11. Case Study Pack (Implementation-Ready Experiments)](#chapter-11-case-study-pack-implementation-ready-experiments)

**PART VII: Reference and Roadmap**

12. [Chapter 12. Full Parameter and Contract Reference](#chapter-12-full-parameter-and-contract-reference)
13. [Chapter 13. Validation and Reproducible Experiment Protocol](#chapter-13-validation-and-reproducible-experiment-protocol)
14. [Chapter 14. Open Research Problems and Near-Term Roadmap](#chapter-14-open-research-problems-and-near-term-roadmap)
15. [Chapter 15. Practical Adoption Path](#chapter-15-practical-adoption-path)

**Appendices**

16. [Appendix A. Glossary](#appendix-a-glossary)
17. [Appendix B. Terminology Map](#appendix-b-terminology-map)
18. [Appendix C. Quick-Start Checklists](#appendix-c-quick-start-checklists)

---

## 5-Minute Quick Start

This section is a minimal path for first-time users to run the toolkit and verify that the environment-control loop works end to end.

### Goal
In five minutes, you should be able to:
1. Run the sanity check suite.
2. Run one integrated simulation.
3. Generate and inspect Gantt chart outputs.

### Step 1. Environment check

Activate your Python environment (conda, venv, or system Python), then run:

```bash
python --version
python -m tests.test_env_validation_matrix
```

Expected outcome:
- The test module exits without assertion failures.

### Step 2. Run a scenario-level integration

```bash
python -m tests.test_gantt_validation
```

Expected outcome:
- Scenario output logs appear.
- `results/scenario*_gantt_direct.png` files are generated.

### Step 3. Run a minimal custom loop

```python
from src.environment.manufacturing_env import ManufacturingEnv
from src.agents.factory import build_meta_scheduler

cfg = {
    "num_machines_A": 2,
    "num_machines_B": 2,
    "num_machines_C": 1,
    "batch_size_A": 2,
    "batch_size_B": 1,
    "batch_size_C": 4,
    "scheduler_A": "fifo",
    "scheduler_B": "rule-based",
    "packing_C": "greedy",
    "max_steps": 30,
}

env = ManufacturingEnv(cfg)
meta = build_meta_scheduler(env.config)
obs = env.reset()

done = False
while not done:
    state = env.get_decision_state()
    actions = meta.decide(state)
    obs, reward, done, _ = env.step(actions)

print(obs["num_completed"])
```

Expected outcome:
- The loop terminates at `max_steps`.
- `num_completed` is typically > 0 after a 30-step run.

---

## PART I: Platform Foundation

---

## Chapter 1. Manufacturing AI as a Multi-Layer Decision System

Manufacturing AI is the structured interaction of multi-stage decision layers — and that interaction is what this toolkit is designed to expose.

### 1.1 The multi-layer problem structure

Real manufacturing systems involve four nested decision layers, each with its own objectives and time horizon:

| Layer | Decision type | Time horizon | Key challenge |
|---|---|---|---|
| **Layer 1: Task Allocation** | Which tasks to which machines, when | Per step | Bottleneck avoidance, priority, queue balance |
| **Layer 2: Process-Level Dynamics** | Recipe parameters, consumable management | Per batch | Quality drift, degradation compensation, yield maintenance |
| **Layer 3: Cross-Stage Coupling** | WIP flow, rework re-injection, deadline propagation | Per episode | Starvation, blocking, tardiness cascade |
| **Layer 4: System-Level Objective** | Throughput, yield, cost, robustness | Aggregate | Trade-off balancing, disturbance recovery |

Setting higher-level objectives requires considering multi-process coupling, not just individual process optimization. The interesting and hard problems emerge at the interfaces between layers.
This toolkit is designed to expose those interfaces.

### 1.2 Why existing simulators fall short

Standard manufacturing simulators make assumptions that prevent multi-layer research:

- **Single-stage focus**: most simulators optimize one process independently.
  Cross-stage coupling (WIP propagation, tardiness escalation, bottleneck transfer) cannot be studied.
- **No process-level dynamics**: scheduling simulators assume perfect machines.
  There is no consumable degradation, quality drift, or recipe dependency.
- **No rework modeling**: failed tasks either disappear or trivially retry.
  The quality-scheduling interaction — where rework load from poor recipes causes scheduling pressure — is invisible.
- **Tight coupling**: environment physics and decision logic live in the same module.
  Comparing two scheduling algorithms under identical physical conditions requires duplicating the entire system.

### 1.3 Design philosophy

Three principles govern every design decision in this toolkit:

1. **Separation first**: the environment is restricted to state transitions and process physics.
   No decision logic lives inside it.
2. **Modular at every layer**: scheduler, tuner, packer, and meta scheduler are each
   independently replaceable without touching the others.
3. **Reproducibility as contract**: fixed seeds, deterministic modes, and event-log
   traceability are first-class requirements, not afterthoughts.

### 1.4 Module architecture

The environment executes state transitions; decision modules decide assignments and control actions.

When scheduling policy and state transition share the same code, it becomes impossible to swap one without risking regressions in the other — and impossible to replicate results without re-running the entire system.

This framework enforces a strict separation: the environment is intentionally restricted to state transitions and process physics.
No scheduling logic, no recipe selection, no maintenance decisions live inside the environment core.
All decision-making is delegated to external modules:
- `src/environment/*`: process semantics and state transition.
- `src/agents/*`: orchestration and action generation.
- `src/schedulers/*`: assignment policy.
- `src/tuners/*`: recipe/control policy.

This separation supports controlled ablation studies such as:
- Same scheduler, different tuner.
- Same tuner, different scheduler.
- Same local policies, different meta-orchestration.

### 1.5 Core execution loop

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

### 1.6 Scope and known limitations

**What this framework is:**
- A research platform for evaluating scheduling, APC, and hybrid AI algorithms under controlled multi-stage manufacturing conditions.
- A modular environment where any policy can be swapped without touching the core.
- A reproducibility-first tool with event traceability and fixed-seed support.

**What this framework is not:**
- A high-fidelity digital twin of any real manufacturing line.
- A replacement for industrial simulation tools (SimPy, FlexSim, AnyLogic).
- A production-ready process control system.

The physical models in Process A, B, and C are intentional simplifications calibrated for research dynamics.
They exhibit realistic degradation, rework, and quality-throughput tradeoffs, but they do not represent any specific real-world process.
Researchers extending this framework to real processes should incorporate domain knowledge into the environment and replace the physical equations in full (see Section 3.5).

---

## Chapter 2. Runtime Execution Model

### Purpose
This chapter defines the runtime contracts for state snapshots, action payloads, event logs, and same-step handoff timing.

### 2.1 Global step semantics
At each `env.step(actions)`:
1. A executes and may produce passed tasks.
2. Passed tasks are handed to B in the same step.
3. B executes and may produce passed tasks.
4. Passed tasks are handed to C in the same step.
5. C executes packing/finalization.
6. Optional periodic arrivals are injected.
7. Time increments.

### 2.2 Decision state schema (high-level)

| Section | Key fields | Notes |
|---|---|---|
| Top level | `time`, `max_steps`, `num_completed`, `tasks` | `tasks` is de-duplicated snapshot map keyed by UID |
| A | `machines`, `wait_pool_uids`, `rework_pool_uids`, `finishing_now_uids`, `queue_stats` | Includes machine health signals like `u`, `m_age` |
| B | `machines`, `wait_pool_uids`, `rework_pool_uids`, `finishing_now_uids`, `incoming_from_A_uids`, `queue_stats` | Includes machine health signals like `v`, `b_age` |
| C | `machines`, `wait_pool_uids`, `incoming_from_B_uids`, `queue_stats`, `last_pack_time`, `pack_count` | Used by packers and C policies |

> **Naming note:** `wait_pool` (internal to the process environment) is a list of `Task` objects.
> `wait_pool_uids` (exposed in the decision state) is a list of integer UIDs drawn from that pool.
> Schedulers and packers receive UIDs — they look up task attributes from the `tasks` snapshot map, not from `wait_pool` directly.

### 2.3 Action schema

```python
{
  "A": {
    "A_0": {
      "task_uids": [1, 2],
      "recipe": [10.0, 2.0, 1.0],     # [s1, s2, s3]
      "task_type": "new",              # "new" or "rework"
      "replace_consumable": False,     # True → replace consumable before this batch
    }
  },
  "B": {
    "B_0": {
      "task_uids": [3],
      "recipe": [50.0, 50.0, 30.0],   # [r1, r2, r3]
      "task_type": "rework",
      "replace_solution": False,       # True → replace solution before this batch
    }
  },
  "C": {
    "C_0": {"task_uids": [4, 5, 6, 7], "reason": "batch_ready"}
  }
}
```

### 2.4 Event schema (analysis contract)

| Process | Event types | Typical fields |
|---|---|---|
| A | `task_assigned`, `task_completed` | `timestamp`, `machine_id`, `task_uids`, `start_time`, `end_time`, `task_type` |
| B | `task_assigned`, `task_completed` | same as A |
| C | `task_queued`, `pack_completed` | queue and pack lifecycle fields, `pack_id` |

### 2.5 Integrity invariants used by tests
- No duplicate assignment of the same task UID in one decision cycle.
- No machine overlap in assignment intervals.
- Tasks always flow in order: A → B → C. No backward routing.
- Rework count is non-decreasing.
- Strict external control: no action means no new dispatching.

### 2.6 Job arrival and periodic generation

Periodic task generation is controlled inside `ManufacturingEnv.step()` in
`src/environment/manufacturing_env.py`. The relevant code segment:

```python
# src/environment/manufacturing_env.py — step(), periodic injection
if getattr(self, "_periodic_enabled", True) and self.time > 0 and self.time % 30 == 0:
    new_tasks = self.data_generator.generate_new_jobs(self.time)
    self.env_A.add_tasks(new_tasks)
```

**To change the arrival period:**
Edit `self.time % 30 == 0` directly in `manufacturing_env.py`.
For a config-driven period, add `arrival_period = config.get("arrival_period", 30)` to
`__init__` and replace the hardcoded `30` with `self.arrival_period`.

**Arrival patterns you can model:**

| Pattern | Implementation hint |
|---|---|
| Fixed period (default) | `self.time % N == 0` |
| Poisson arrivals | `np.random.poisson(lam=1) > 0` per step with variable batch sizes |
| Burst arrivals | inject large batches at specific time windows |
| Demand-driven | trigger on queue length falling below threshold |

**To disable periodic arrivals entirely:**
Call `env.reset(seed_initial_tasks=False)` and inject tasks manually via
`env.env_A.add_tasks(tasks)` at any time. The `_periodic_enabled` flag controls
whether automatic injection runs during `step()`.

### 2.7 Environment reset and initial task injection

`ManufacturingEnv.reset()` accepts two optional parameters that control how the
environment is initialized at the start of each episode:

```python
reset(
    seed_initial_tasks: bool = True,
    initial_tasks: Optional[List[Task]] = None,
    seed: Optional[int] = None,
)
```

| Parameter combination | Behavior |
|---|---|
| `seed_initial_tasks=True, initial_tasks=None` | Auto-generate and inject initial tasks (default) |
| `initial_tasks=[task1, task2, ...]` | Inject only the specified tasks into the A queue (scenario control) |
| `seed_initial_tasks=False, initial_tasks=None` | Start with an empty queue; inject tasks manually |
| `seed=<int>` | Sets `random.seed()` and `np.random.seed()` for reproducible stochastic runs |

**Use cases:**

- **Reproducible benchmarks:** pass a fixed `initial_tasks` list to guarantee identical starting conditions across runs.
- **Curriculum learning:** gradually increase task difficulty by controlling the initial batch.
- **Scenario testing:** construct corner-case task sets (e.g., all high-priority, all near-deadline) and inject them directly.
- **Manual injection after reset:** call `env.env_A.add_tasks(tasks)` at any step after `reset()` to supplement the periodic arrival schedule.

---

## PART II: Process Models and Research Surfaces

---

## Chapter 3. Environment Internals and Physical-Model Customization

### Overview

This simulator abstracts three process types commonly found in real manufacturing lines:

| Process | Real-world manufacturing type | Implementation |
|---|---|---|
| **Process A** | Machining / processing step | `src/environment/process_a_env.py` |
| **Process B** | Chemical cleaning / wet process step | `src/environment/process_b_env.py` |
| **Process C** | Packaging / bin-packing step | `src/environment/process_c_env.py` |

Each process has its own independent physical model and state variables. The environment is responsible only for state transitions; all decision-making (recipe selection, consumable replacement, batch composition) is delegated to external agents (tuner, scheduler, packer).

### 3.1 Process A (`src/environment/process_a_env.py`)

#### Model Design Rationale

In a typical machining process, output quality is determined by four factors:

```
quality = f(equipment recipe,  consumable condition,  machine aging,  input material)
```

For simplicity, **input material is excluded** from this model. The remaining three factors are represented as:

| Real-world factor | Model variable | Role |
|---|---|---|
| Equipment recipe | `s1, s2, s3` | Process parameters (decided by tuner) |
| Consumable wear | `u` (consumable usage) | Accumulated usage degrades effectiveness |
| Machine aging | `m_age` (machine age) | Linearly degrades model coefficients |

These three variables determine the QA output:

#### 3.1.1 Model Equations

```
g_s           = (w1·s1 + W2_BASE·s2 + W3_BASE·s3 + b) + (w12 · s1 · s2)  # process signal
effectiveness  = 1 − BETA · tanh(BETA_K · u)                               # consumable decay
std_dev        = GAMMA · tanh(GAMMA_K · u)                                  # noise growth
mean_qa        = g_s × effectiveness
realized_qa    = mean_qa  [deterministic]  or  Normal(mean_qa, std_dev)     [stochastic]
passed         = spec_a[0] ≤ realized_qa ≤ spec_a[1]
```

**Physical constants (module-level, `src/environment/process_a_env.py`):**

| Constant | Value | Role |
|---|---|---|
| `W1_BASE` | 0.5 | Linear s1 weight |
| `W2_BASE` | 0.3 | Linear s2 weight |
| `W3_BASE` | 0.2 | Linear s3 weight |
| `B_BASE` | 45.0 | Baseline QA offset |
| `W12_BASE` | 0.01 | s1×s2 interaction strength |
| `BETA` | 0.2 | Consumable effectiveness decay amplitude |
| `BETA_K` | 0.1 | Consumable effectiveness decay rate (tanh) |
| `GAMMA` | 1.5 | Noise amplitude at max usage |
| `GAMMA_K` | 0.1 | Noise growth rate (tanh) |
| `DELTA_W1` | 0.001 | w1 degradation rate per unit m_age |
| `DELTA_W12` | 0.0001 | w12 degradation rate per unit m_age |
| `DELTA_B` | 0.02 | Baseline shift rate per unit m_age |

Machine-age degradation (`_get_physical_model_params()`):
- `w1 = W1_BASE × (1 − DELTA_W1 × m_age)`
- `w12 = W12_BASE × (1 − DELTA_W12 × m_age)`
- `b = B_BASE − DELTA_B × m_age`

For full model exploration and validation, see `notebooks/01_Process_A_example.ipynb`.

#### 3.1.2 Machine Age Effect

As `m_age` increases all key coefficients degrade (w1↓, w12↓, b↓), lowering the achievable QA ceiling.

![Machine Age Effect](../results/p_a_01_machine_age_effect.png)

*Left: mean QA drops linearly with m_age under fixed recipe and u=5. Right: QA distributions at m_age=0/100/200 show progressive left-shift and eventual spec violation.*

**Takeaway for tuners:** Machine age is an exogenous state that the tuner cannot control. Use the (m_age × u) joint heatmap (Section 3.1.5) to calibrate compensation across both degradation axes simultaneously.

#### 3.1.3 Consumable Usage (u) Effect

Consumable usage degrades `effectiveness` via tanh and amplifies stochastic noise via the same functional form.

![Consumable Usage Effect](../results/p_a_02_consumable_effect.png)

*Left: effectiveness (blue) and std_dev (red) curves vs. u — both saturate toward asymptotes. Center: mean QA decline at fixed recipe [10, 2, 1]. Right: first-pass rate (FPR) distribution at u=1/10/20 — FPR drops sharply as u grows.*

**Key numbers (default recipe `[10, 2, 1]`, m_age=0):**
- `u=0` → mean QA ≈ 51.0, FPR ≈ 100%
- `u=10` → mean QA drops, FPR begins to fall
- `u=20` → mean QA ≈ 44.2, spec violation risk increases significantly

**Takeaway for tuners:** `u` is the primary short-term degradation variable. The tuner cannot control it directly but can reset it to 0 via consumable replacement (`should_replace_consumable()`), fully restoring effectiveness. See Section 3.6 for the replacement interface.

#### 3.1.4 Recipe Sensitivity

s1 is the dominant control variable; s2 and s3 have minor and roughly equal influence.

![Recipe Sensitivity](../results/p_a_03_recipe_sensitivity.png)

*Sensitivity sweeps at m_age=50, u=10. s1 drives ΔQA ≈ 25.5 over its range; s2 ΔQA ≈ 2.5; s3 ΔQA ≈ 1.5. Green PASS region shown per variable.*

**Takeaway for tuners:** Adaptive tuners should focus compensation on s1 first. The s1 passing range narrows as u increases — this is the core dynamic that tuner design must address.

#### 3.1.5 Joint (m_age × u) State Space

The combined effect of machine age and consumable usage determines whether any recipe can hit spec.

![m_age × u Joint Heatmap](../results/p_a_04_joint_heatmap.png)

*Left: continuous mean QA heatmap — blue contour lines mark spec boundaries [45, 55]. Right: binary PASS/FAIL map under default recipe. Red = consumable replacement or recipe compensation required.*

**Takeaway for tuner design:** The FAIL region in the binary map defines the safety boundary for `should_replace_consumable()`. The default threshold (u ≥ 10) marks the onset of FPR degradation under the default recipe. Adjust it per equipment or make it adaptive via the `consumable_replace_threshold` config key.

#### 3.1.6 Control Loop Simulation — Tuner Role Visualization

The following experiment contrasts two control policies over 60 steps (m_age=50 fixed):

- **[Sim A]** Fixed recipe (s1=10, no tuning) — u accumulates, quality drifts below spec
- **[Sim B]** Recipe tuning (s1 analytically optimized toward TARGET_QA=50) + consumable replacement when s1 would exceed operational limit S1_OP_MAX=30

![Tuner Control Loop Simulation](../results/p_a_05_tuning_simulation.png)

*Top panel: QA over time. Solid lines = deterministic mean QA; dots = stochastic realized QA. Middle panel: s1 trajectories (Sim B adjusts to compensate; Sim A stays flat). Bottom panel: u tracking (Sim B resets on replacement; Sim A accumulates).*

**Results:**

| Scenario | FPR | Spec failures | Min mean_QA |
|---|---|---|---|
| [A] Fixed recipe | 10% | 54 / 60 | **39.86** (well below spec lower bound 45) |
| [B] Tuning + replacement | **100%** | 0 / 60 | 50.00 |

Sim B triggers 4 consumable replacements (steps 12, 24, 36, 48) with s1 adjusted across [10.5, 29.8].

**Takeaway:** Without tuning, u accumulation drives mean QA below the spec lower bound within ~12 steps. The tuner's two-action strategy — recipe adjustment first, consumable replacement at the operational limit — fully maintains spec compliance. Source: `notebooks/01_Process_A_example.ipynb`, Cell 6.

**Primary edit points:**
- `_get_physical_model_params(...)` — age-based coefficient degradation
- `_run_qa_check(...)` — QA computation, noise model, spec check
- pass/fail boundary (inclusive: `spec_a[0] <= qa <= spec_a[1]`)

#### 3.1.7 Research targets for Process A

The degradation dynamics in Process A are designed to support specific research directions:

- **Aging-aware scheduling**: machine age degrades the achievable QA ceiling. Schedulers that route tasks to younger machines may achieve better quality at the cost of uneven utilization.
- **Predictive maintenance**: the joint (m_age × u) heatmap defines the safety boundary for consumable replacement. Data-driven policies that predict when to replace before quality drops are directly testable here.
- **Condition-based production planning**: `should_replace_consumable()` is the maintenance decision interface. Coupling this with scheduling decisions (delay a batch vs. replace now) is a joint optimization problem — see the QREI 2022 and POMS 2023 papers in Chapter 14.
- **Physics-informed surrogate models**: `_run_qa_check(...)` can be replaced with any ML surrogate (neural network, Gaussian process) trained on real process data. Section 3.5 provides substitution patterns.
- **Recipe optimization under drift**: as `u` increases, the feasible recipe region narrows. Online Bayesian optimization or RL-based recipe adaptation can be directly compared against the rule-based `AdaptiveTuner` baseline.

### 3.2 Process B (`src/environment/process_b_env.py`)

Process B is a downstream quality-screening step with its own degradation state: solution usage (`v`) and machine age (`b_age`). QA is computed from a recipe vector and the physical model; the spec boundary is `spec_b`.

**Machine state variables:**
- `v` — solution/consumable usage (resets on `replace_solution()`; drives effectiveness decay)
- `b_age` — machine age (exogenous; degrades model coefficients over time)

#### Model Equations

```
base_quality  = (r1 + r2 + r3) / 3.0
effectiveness = max(0.1, 1.0 − ALPHA × (v / 30.0))
mean_qa       = 50.0 + (base_quality − 40.0) × 0.5 × effectiveness
degradation   = 1.0 − (b_age / 1000.0) × 0.1
noisy_qa      = mean_qa + Noise          # Normal(0, BETA×0.1); clipped to [50, 100]
realized_qa   = noisy_qa × degradation   # clipped to [50, 100]
passed        = spec_b[0] < realized_qa < spec_b[1]  # strict (exclusive) boundary
```

**Physical constants (module-level, `src/environment/process_b_env.py`):**

| Constant | Value | Role |
|---|---|---|
| `ALPHA` | 0.15 | Solution effectiveness decay rate per usage unit |
| `BETA` | 1.5 | Noise amplitude — actual noise std = `BETA × 0.1 = 0.15` per step |

Note: Unlike Process A, Process B uses a **strict** boundary check (`<` not `<=`).

**Primary edit points:**
- `_run_qa_check(...)` — QA computation and spec check (edit here to change the physics)
- recipe parsing and defaulting — B uses a different recipe schema than A
- clipping and degradation behavior — `ALPHA`, `BETA` constants at module level

**Consumable replacement interface:** `should_replace_solution()` in `src/tuners/tuners_b.py`. See Section 3.6.

#### Research targets for Process B

- **Reaction-time vs quality trade-off**: varying `process_time_B` combined with solution degradation creates a reaction-time vs. yield surface. At what point does a longer dwell in degraded solution hurt more than it helps?
- **Batch size vs yield stability**: larger batches under degraded solution show higher variance in per-task QA. The interaction between `batch_size_B` and `v` on FPR is a direct research target.
- **Stochastic process variation modeling**: the `BETA × 0.1` noise model can be replaced with any noise distribution. Studying policy robustness under increased variability (non-Gaussian, heteroscedastic) is a natural extension.
- **Cross-stage quality propagation**: tasks completing B with marginal quality affect C packing scores. The B→C quality propagation chain connects process control directly to final shipment outcomes.

### 3.3 Process C (`src/environment/process_c_env.py`)

Process C is the final packing stage. It selects subsets of completed B-process tasks and groups them into packs based on compatibility and quality criteria. No recipe or physical QA model — output quality is an aggregate of upstream QA.

**Primary edit points:**
- `_init_compatibility_matrix(...)` — define which task pairs/groups are compatible
- `_compute_compatibility(...)` — score pairwise compatibility (material, color, spec alignment)
- `_create_pack_info(...)` — compute pack-level KPIs (yield, margin, quality aggregate)

**Packer extension:** Pack selection policy lives in `src/schedulers/packers_c.py` — see Chapter 9 for multi-objective packing design.

#### Research targets for Process C

- **Online bin packing with quality constraints**: each incoming task carries a different quality score and spec compatibility. Classical bin packing can be compared to learned packing policies on this dynamic, quality-filtered stream.
- **Due-date aware packing**: the `TimePenalty` term creates a quality-vs-urgency trade-off. How does aggressive urgency penalization affect final pack quality and long-term throughput?
- **Multi-objective packing (yield, cost, due date)**: the `α/β/γ/δ` weight parameters define a multi-objective surface. Pareto-optimal packing strategies across quality, compatibility, margin, and urgency are directly explorable via weight sweeps.
- **Adaptive objective weighting**: if product priorities shift mid-episode (e.g., urgent orders arrive), can the packer adapt its weights dynamically without sacrificing throughput?

### 3.4 Common safe-edit workflow
1. Change only one process model at a time.
2. Keep action schema stable.
3. Re-run validation matrix and Gantt validation after each model change.
4. Compare event logs before and after for regressions.

### 3.5 Physical model customization rationale

**Workflow for customizing process physics:**

1. Open `src/environment/process_a_env.py` (or `process_b_env.py`).
2. Replace or extend `_get_physical_model_params(...)` and/or `_run_qa_check(...)` with your domain model.
3. Keep method signatures and return semantics unchanged (`_run_qa_check` must return `bool`).
4. Ensure QA output range is compatible with task `spec_a` / `spec_b` ranges.
5. Re-run validation tests after each model change to confirm no regressions.

**Example substitutions:**

| Scenario | What to change |
|---|---|
| Arrhenius thermal degradation | Replace `_get_physical_model_params(...)` with temperature-dependent coefficients |
| ML surrogate quality predictor | Replace `_run_qa_check(...)` body with surrogate model inference |
| Deterministic yield curve | Replace `np.random.normal(...)` with a lookup table |
| Multi-variate interaction model | Extend the `g_s` computation with additional recipe interaction terms |

**Do not touch:**
- `wait_pool`, `rework_pool`, `event_log` management — these are orchestration contracts.
- Method signatures — `_run_qa_check` returns `bool`; task history append is required for Gantt analysis.

> **Physical model constants are hardcoded, not configurable.**
> Constants such as `W1_BASE`, `DELTA_W1`, `BETA`, `GAMMA` (Process A) and `ALPHA`, `MIN_QA`, `MAX_QA` (Process B) are module-level constants defined directly in `process_a_env.py` and `process_b_env.py`. They are **not** exposed through the config dict.
> To change them, edit the source files directly. This is intentional: the physical model is the research ground truth, not a tunable parameter.

**Current model structure (Process A):**

The default physical model uses a linear recipe signal with a nonlinear s1×s2 interaction term,
machine-age degradation on key coefficients, and consumable-usage-driven effectiveness decay and
noise amplification (both via tanh). The full model exploration is in `notebooks/01_Process_A_example.ipynb`.

```python
# src/environment/process_a_env.py — module-level constants (replace to change physics)
W1_BASE, W2_BASE, W3_BASE, B_BASE = 0.5, 0.3, 0.2, 45.0
W12_BASE = 0.01           # recipe interaction strength (s1 × s2)
BETA,  BETA_K  = 0.2, 0.1  # consumable effectiveness decay amplitude and rate (tanh)
GAMMA, GAMMA_K = 1.5, 0.1  # noise amplitude and rate with consumable usage (tanh)
DELTA_W1, DELTA_W12, DELTA_B = 0.001, 0.0001, 0.02  # machine-age degradation rates

def _get_physical_model_params(self, m_age: int):
    """Machine age degrades w1 and w12 linearly; baseline b shifts down."""
    w1  = W1_BASE  * (1 - DELTA_W1  * m_age)
    w12 = W12_BASE * (1 - DELTA_W12 * m_age)
    b   = B_BASE   - DELTA_B * m_age
    return w1, w12, b

def _run_qa_check(self, machine, recipe, task, current_time) -> bool:
    s1, s2, s3 = recipe
    w1, w12, b = self._get_physical_model_params(machine.m_age)

    g_s = (w1*s1 + W2_BASE*s2 + W3_BASE*s3 + b) + (w12 * s1 * s2)  # linear + interaction
    effectiveness = 1 - BETA  * np.tanh(BETA_K  * machine.u)        # consumable decay
    std_dev       =     GAMMA * np.tanh(GAMMA_K * machine.u)        # noise grows with usage

    mean_qa = g_s * effectiveness
    realized_qa = mean_qa if self.deterministic else np.random.normal(mean_qa, std_dev)

    passed = task.spec_a[0] <= realized_qa <= task.spec_a[1]
    task.history.append({"time": current_time, "process": "A", "qa": realized_qa})  # required
    return passed
```

**Substitution skeletons:**

Example A — Arrhenius thermal model (temperature drives reaction rate):
```python
# Replace _get_physical_model_params with temperature-dependent coefficients.
# Add "process_temperature_K" to your config dict.
R, Ea = 8.314e-3, 0.6  # kJ/mol·K and activation energy (domain-specific)

def _get_physical_model_params(self, m_age: int):
    T  = self.config.get("process_temperature_K", 500.0)
    k  = np.exp(-Ea / (R * T))                      # Arrhenius rate constant
    w1 = W1_BASE * k * (1 - DELTA_W1 * m_age)
    w12 = W12_BASE * (1 - DELTA_W12 * m_age)
    b  = B_BASE * k - DELTA_B * m_age
    return w1, w12, b
```

Example B — ML surrogate predictor (data-driven quality model):
```python
# Replace _run_qa_check body with surrogate inference.
# surrogate_model must expose predict(features) -> (mean_qa, std_dev).
def _run_qa_check(self, machine, recipe, task, current_time) -> bool:
    features = np.array([*recipe, machine.u, machine.m_age], dtype=float)
    mean_qa, std_dev = self.surrogate_model.predict(features.reshape(1, -1))

    realized_qa = float(mean_qa) if self.deterministic else np.random.normal(mean_qa, std_dev)

    passed = task.spec_a[0] <= realized_qa <= task.spec_a[1]
    task.history.append({"time": current_time, "process": "A", "qa": realized_qa})  # required
    return passed
```

Example C — Deterministic yield curve (lookup table, no stochastic term):
```python
YIELD_TABLE = {  # (s1_bucket, u_bucket) -> qa; populate from process data
    (0, 0): 52.0, (0, 1): 49.0, (1, 0): 54.0, (1, 1): 51.0,
}

def _run_qa_check(self, machine, recipe, task, current_time) -> bool:
    s1_bucket = int(recipe[0] / 5)
    u_bucket  = int(machine.u / 10)
    realized_qa = YIELD_TABLE.get((s1_bucket, u_bucket), B_BASE)  # fallback to baseline

    passed = task.spec_a[0] <= realized_qa <= task.spec_a[1]
    task.history.append({"time": current_time, "process": "A", "qa": realized_qa})  # required
    return passed
```

**Alignment check after substitution:**

Your new model must produce quality values that can both pass and fail `task.spec_a` under
realistic recipe and machine-state conditions. Run a quick sanity sweep before experiments:

```python
from src.environment.process_a_env import ProcessA_Env
from src.objects import ProcessA_Machine, Task

env = ProcessA_Env({"deterministic_mode": True, "num_machines_A": 1})
machine = ProcessA_Machine(0, batch_size=1)
task = Task(uid=0, job_id="test", due_date=100, spec_a=(45.0, 55.0), spec_b=(60.0, 90.0))

for s1 in [5.0, 10.0, 15.0, 20.0]:
    passed = env._run_qa_check(machine, [s1, 2.0, 1.0], task, current_time=0)
    print(f"s1={s1:5.1f} -> {'PASS' if passed else 'FAIL'}")
```

If every recipe produces all-PASS or all-FAIL, your QA output range is misaligned with
`task.spec_a` — adjust model constants or spec ranges accordingly.

### 3.6 Consumable and solution replacement (tuner-controlled)

Consumable replacement (Process A) and solution replacement (Process B) are controlled
externally by the tuner, not by the environment. This upholds the design principle that the
environment applies state transitions but does not make maintenance decisions.

**Interface:**

```python
# src/tuners/tuners_a.py
class BaseRecipeTuner:
    def should_replace_consumable(self, machine_state: Dict[str, Any]) -> bool:
        """Return True to replace consumable before the next batch starts."""
        ...

# src/tuners/tuners_b.py
class BaseRecipeTuner:
    def should_replace_solution(self, machine_state: Dict[str, Any]) -> bool:
        """Return True to replace solution before the next batch starts."""
        ...
```

**Default behavior:**
- Process A: replace when `machine_state["u"] >= consumable_replace_threshold` (default: 10).
- Process B: replace when `machine_state["v"] >= solution_replace_threshold` (default: 20).
- Both thresholds are config-injectable via `consumable_replace_threshold` and `solution_replace_threshold`.

**Action flow:**
1. Meta scheduler calls `tuner.should_replace_*()` after recipe selection.
2. The boolean result is added to the action payload: `"replace_consumable": True/False` (A) or `"replace_solution": True/False` (B).
3. Process env applies replacement **before** `machine.start_processing(...)` in that same step.

**Custom replacement policies you can implement:**

| Policy | Implementation |
|---|---|
| Threshold-based (default) | compare `u` or `v` against config threshold |
| rule-based (Quality-triggered, Predictive maintenance) | monitor `realized_qa` moving average; replace on degradation, replace after fixed N-batch interval regardless of usage |
| Mathematical optimization | Integer programming or LP minimizing replacement cost subject to quality and usage constraints |
| Heuristics | Fixed-interval or condition-triggered rules without full state modeling |
| Meta-heuristics | Evolutionary or simulated-annealing search over candidate replacement schedules |
| RL | RL policy outputs replacement decision as part of action space |

---

## PART III: Connecting Your Factory

---

## Chapter 4. Factory-to-Simulator Mapping

### Purpose
This chapter answers the question "How do I map my factory to this simulator?"
It provides concept-level mappings, factory-type configuration examples, and patterns for modeling realistic constraints.

### 4.1 Core concept mapping

| Real-world manufacturing concept | Simulator object / variable | Where to edit |
|---|---|---|
| Machine / Equipment | `ProcessA_Machine`, `ProcessB_Machine` | `src/objects.py` |
| Job / Work order | `Task` object | `src/objects.py` |
| Process routing | A → B → C pipeline | `src/environment/manufacturing_env.py` |
| Quality inspection spec | `task.spec_a`, `task.spec_b` | Task attribute |
| Consumable wear (tool, pad, etc.) | `u` (consumable usage counter) | Process A state |
| Chemical / bath degradation | `v` (solution usage counter) | Process B state |
| Machine aging / wear | `m_age` (Process A), `b_age` (Process B) | Machine state |
| Rework / re-inspection | `rework_pool` → re-dispatched to same process | Process env |
| Final packaging / shipment | Process C packing | `src/environment/process_c_env.py` |
| Due date | `task.due_date` | Task attribute |
| Product margin / priority | `task.margin_value` | Task attribute |
| Arrival rate / demand | `arrival_period`, `data_generator` | `manufacturing_env.py` |

### 4.2 Factory type examples

#### Type 1: Single-product flow shop (direct mapping)
The default A→B→C pipeline maps directly.
- Process A: machining
- Process B: cleaning / etching
- Process C: final packaging / grouping

#### Type 2: Multi-product high-mix (product type differentiation)
Add a `product_type` attribute to `Task` and vary `spec_a` / `spec_b` per product family.

```python
# src/objects.py — extend Task
@dataclass
class Task:
    uid: int
    job_id: str
    due_date: int
    spec_a: Tuple[float, float]
    spec_b: Tuple[float, float]
    margin_value: float = 1.0
    # Add custom attributes:
    product_type: str = "standard"    # "standard", "premium", "urgent"
    priority_class: int = 1           # 1 = normal, 2 = urgent
    setup_group: str = "default"      # setup family for changeover cost
```

Then vary `spec_a` when generating tasks:
```python
# In data_generator.py — product-specific specs
SPECS = {
    "standard": (44.0, 56.0),
    "premium":  (47.0, 53.0),   # tighter spec window
    "urgent":   (43.0, 57.0),   # wider spec, compensated by priority
}
task = Task(..., product_type="premium", spec_a=SPECS["premium"])
```

#### Type 3: Re-entry / re-inspection patterns (semiconductor-style)
Use the `rework_pool` mechanism to model re-entry loops.
Tasks that fail QA at Process A enter `rework_pool_A` and are re-dispatched.
This natively models re-entry patterns without additional code changes.

For multi-pass re-entry (e.g., task may loop A up to 3 times):
- Track `task.rework_count` (already available in Task)
- In the scheduler, limit re-dispatch if `rework_count >= MAX_REWORK`

#### Type 4: More than 3 process stages
Add a Process D by following **Playbook D in Chapter 10** (Section 10.4).
Process D integrates into `manufacturing_env.py` step order and the handoff chain.

### 4.3 Modeling realistic manufacturing constraints

| Constraint | Implementation location | Pattern |
|---|---|---|
| Sequence-dependent setup time | `select_batch(...)` in scheduler | Compare `setup_group` of current and previous batch; add wait cost |
| Machine breakdown | Process env `step()` | Add `breakdown_prob` config key; when triggered, set `machine.is_broken = True` and skip assignment |
| Buffer limit (queue cap) | `should_schedule()` | Return `False` if `len(wait_pool) >= MAX_BUFFER` |
| Due-date urgency dispatch | Scheduler priority | Sort candidates by `slack = due_date - current_time`; dispatch tightest first |
| Shift calendar / maintenance window | `manufacturing_env.step()` | Inject forced idle steps at scheduled intervals |
| Material compatibility constraint | `_init_compatibility_matrix(...)` in Process C | Define incompatible `(product_type_A, product_type_B)` pairs |

**Setup-dependent dispatch example:**
```python
# src/schedulers/schedulers_a.py
class SetupAwareScheduler(BaseScheduler):
    def select_batch(self, wait_pool_uids, rework_pool_uids, batch_size):
        last_group = self.state.get("last_setup_group", "default")
        same_group = [uid for uid in wait_pool_uids
                      if self.task_map[uid].setup_group == last_group]
        candidates = same_group if same_group else wait_pool_uids
        return candidates[:batch_size]
```

**Machine breakdown injection example:**
```python
# src/environment/process_a_env.py — in step()
breakdown_prob = self.config.get("breakdown_prob_A", 0.0)
for machine in self.machines.values():
    if not machine.is_busy and np.random.rand() < breakdown_prob:
        machine.is_broken = True
        machine.breakdown_remaining = self.config.get("breakdown_duration", 5)
```

### 4.4 What stays invariant when adapting to your factory
- Task UIDs must remain unique within each episode.
- The action schema is stable. Custom Task attributes do not change the action interface.

---

## Chapter 5. KPI Design and Tracking

### Purpose
This chapter maps manufacturing KPIs to simulator data sources and shows how to add, log, and compare custom KPIs.

### 5.1 Standard KPI reference

| KPI | Definition | Computation | Data source |
|---|---|---|---|
| **Throughput** | Tasks completed per unit time | `num_completed / max_steps` | `obs["num_completed"]` |
| **Lead Time** | Total time from arrival to completion | `end_time - arrival_time` per task | A/B event_log |
| **WIP (Work-in-Process)** | Tasks currently in the system | `len(wait_pool_A) + len(rework_pool_A) + len(wait_pool_B) + ...` | decision_state |
| **Tardiness** | Lateness beyond due date | `max(0, end_time - due_date)` per task | event_log + Task |
| **FPR (First-Pass Rate)** | Fraction passing QA on first attempt | `passed_first_attempt / total_processed` | A event_log |
| **Machine Utilization** | Fraction of time machines are busy | `busy_steps / total_steps` per machine | event_log |
| **Rework Rate** | Fraction of tasks requiring rework | `rework_count / total_tasks` | event_log |
| **Consumable Replacements** | Number of consumable/solution replacements | count of `replace_consumable=True` actions | A/B action log |
| **Pack Quality** | Mean realized QA of completed packs | `mean(pack.realized_qa_B)` | C event_log |

### 5.2 Where each KPI lives in code

| KPI | Access point |
|---|---|
| Throughput | `obs["num_completed"]` after each step |
| WIP | `len(state["A"]["wait_pool_uids"]) + len(state["B"]["wait_pool_uids"])` |
| FPR | Computed from `env.env_A.event_log` post-episode |
| Lead Time / Tardiness | Computed from event_log with task `due_date` |
| Utilization | Derived from `start_time`, `end_time` in event_log |

### 5.3 Computing KPIs from event logs

```python
def compute_episode_kpis(env) -> dict:
    """Compute standard KPIs from event logs after an episode ends."""
    a_events = env.env_A.event_log
    b_events = env.env_B.event_log

    # Throughput
    throughput = env.obs["num_completed"]

    # FPR — tasks that completed A without rework
    a_completed = [e for e in a_events if e.get("type") == "task_completed"]
    first_pass = [e for e in a_completed if e.get("task_type") == "new"]
    fpr = len(first_pass) / max(1, len(a_completed))

    # Tardiness (requires task due_date in event log)
    b_completed = [e for e in b_events if e.get("type") == "task_completed"]
    tardiness_list = [max(0, e["end_time"] - e.get("due_date", float("inf")))
                      for e in b_completed if "due_date" in e]
    mean_tardiness = sum(tardiness_list) / max(1, len(tardiness_list))

    # Lead time
    lead_times = [e["end_time"] - e.get("arrival_time", 0)
                  for e in b_completed if "arrival_time" in e]
    mean_lead_time = sum(lead_times) / max(1, len(lead_times))

    return {
        "throughput": throughput,
        "fpr": fpr,
        "mean_tardiness": mean_tardiness,
        "mean_lead_time": mean_lead_time,
    }
```

### 5.4 Adding a custom KPI

**Pattern A — Extend the event log:**
```python
# src/environment/process_a_env.py — in event logging
self.event_log.append({
    "type": "task_completed",
    "machine_id": machine.id,
    "task_uids": batch_uids,
    "start_time": start_time,
    "end_time": current_time,
    "task_type": task_type,
    "qa_value": realized_qa,        # custom field
    "consumable_u": machine.u,      # custom field
})
```

**Pattern B — Accumulate in ManufacturingEnv:**
```python
# src/environment/manufacturing_env.py — in step()
self._kpi_accum["total_setup_events"] += res_A.get("setup_count", 0)
```

### 5.5 Multi-objective KPI comparison pattern

```python
results = []
for policy_name, policy_cfg in experiment_configs.items():
    env = ManufacturingEnv(policy_cfg)
    meta = build_meta_scheduler(env.config)
    obs = env.reset(seed=42)
    done = False
    while not done:
        state = env.get_decision_state()
        actions = meta.decide(state)
        obs, reward, done, _ = env.step(actions)
    kpis = compute_episode_kpis(env)
    kpis["policy"] = policy_name
    results.append(kpis)

import pandas as pd
df = pd.DataFrame(results).set_index("policy")
print(df[["throughput", "fpr", "mean_tardiness", "mean_lead_time"]])
```

---

## PART IV: Research Scenarios

---

## Chapter 6. Research Scenarios

This chapter formalizes four canonical research questions that emerge from the multi-layer structure of this toolkit.
Each is defined as a controlled experiment with a clear problem statement, comparison approaches, evaluation metrics, and code entry points.

### 6.1 Integrated vs Decomposed Scheduling

**Problem**: In a 3-stage A→B→C system, should scheduling decisions be made jointly (global end-to-end optimization) or decomposed stage-by-stage (local policies + coordination layer)?

**Why it matters**: Global optimization is theoretically optimal but computationally intractable at scale.
Decomposed approaches scale but lose cross-stage information.
The performance gap — and whether coordination layers can close it — is an open question in manufacturing AI.

| Approach | Description | Config |
|---|---|---|
| **Decomposed (baseline)** | Independent FIFO/rule-based per stage | `scheduler_A=fifo`, `scheduler_B=rule-based` |
| **Stage-coupled** | Meta uses cross-stage queue pressure to gate assignments | Custom meta scheduler with queue-pressure scoring |
| **End-to-end (RL)** | Single policy observes all stage states and outputs all assignments | RL meta scheduler with full decision-state observation |

**Metrics**: throughput, WIP variance, mean tardiness, cross-stage queue imbalance.

**Code surface**: `src/agents/default_meta_scheduler.py`, `src/agents/meta_scheduler.py`, Chapter 10 Playbook C.

---

### 6.2 Static vs Adaptive Recipe Control

**Problem**: Process A quality degrades as consumable usage `u` accumulates. A fixed recipe eventually fails spec.
How much does adaptive APC improve yield, and at what operational cost?

**Why it matters**: Adaptive process control (APC) is standard in advanced manufacturing, but the adaptation strategy matters.
This scenario provides a controlled surface to compare methods directly, with ground-truth physics.

| Approach | Description | Config |
|---|---|---|
| **Fixed recipe (no APC)** | Always use default `[10.0, 2.0, 1.0]` | `tuner_A=fifo` |
| **Rule-based APC (3-state)** | Recipe adapted based on `u` state: fresh / medium / aged | `tuner_A=adaptive` |
| **RL / Bayesian APC** | Learned policy from full machine state (`u`, `m_age`, queue context) | Custom tuner, `get_recipe(...)` override |

**Metrics**: FPR over time, spec violation rate, consumable replacement frequency, throughput.

**Code surface**: `src/tuners/tuners_a.py`, Section 3.6, Chapter 10 Playbook B.

---

### 6.3 Deterministic vs Stochastic Operation

**Problem**: Policy development often starts in deterministic mode (no QA noise) because it is faster and more reproducible.
But real processes are stochastic. How large is the policy performance gap?

**Why it matters**: Policies tuned in deterministic mode may over-fit to the noiseless quality surface.
Quantifying the deterministic-to-stochastic transfer gap informs when noise must be included during training or evaluation.

| Approach | Description | Config |
|---|---|---|
| **Deterministic** | QA output = `mean_qa` with no noise term | `deterministic_mode=True` |
| **Stochastic** | QA output = `Normal(mean_qa, std_dev)` where `std_dev` grows with `u` | `deterministic_mode=False` |

**Metrics**: FPR, throughput, policy performance delta between modes, episode KPI variance.

**Code surface**: `_run_qa_check(...)` in `process_a_env.py`, `deterministic_mode` config key.

---

### 6.4 Batch Flow vs Single-Piece Flow

**Problem**: Batch size controls the throughput-responsiveness trade-off. Larger batches increase machine utilization; smaller batches reduce WIP and respond faster to urgency.
What is the optimal batch size under different demand and quality conditions?

**Why it matters**: The batch-size trade-off interacts with quality dynamics.
Large batches under degraded consumables produce burst rework events; small batches under high demand create starvation.
This multi-way interaction is directly explorable here.

| Approach | Description | Config |
|---|---|---|
| **Single-piece flow** | One task per dispatch | `batch_size_A=1`, `batch_size_B=1` |
| **Large-batch flow** | Maximum machine utilization | `batch_size_A=4+`, `batch_size_B=2+` |
| **Adaptive batching** | Queue-size-driven dynamic batch selection | Custom `select_batch(...)` returning variable count |

**Metrics**: throughput, mean lead time, WIP, tardiness under variable demand.

**Code surface**: `batch_size_A/B/C` config, `select_batch(...)` in `schedulers_a.py` / `schedulers_b.py`.

---

## PART V: Algorithm Extension Space

---

## Chapter 7. Scheduling Research Extension Space

### Purpose
This chapter maps modern manufacturing scheduling families to concrete extension points in this codebase.

### 7.1 Scheduling Applicability Matrix

| Scheduling family | Typical objectives | Required signals from `decision_state` | Exact insertion point | Minimal prototype path |
|---|---|---|---|---|
| Batch scheduling | makespan, throughput, WIP | queue sizes, machine `batch_size`, waiting UIDs | `src/schedulers/schedulers_a.py`, `src/schedulers/schedulers_b.py` | modify `select_batch(...)` with batch-aware heuristics |
| FFSP/HFSP stage mapping | stage balance, bottleneck relief | per-stage queue lengths, machine status, incoming UIDs | `src/agents/default_meta_scheduler.py` + schedulers | add stage-priority logic in meta orchestration before per-process calls |
| Rework-aware scheduling | rework debt, FPY, tardiness | `rework_pool_uids`, `rework_count`, due date | schedulers + meta | prioritize rework via weighted queue policy |
| Due-date/tardiness control | tardiness, lateness, OTIF | `due_date`, time, queue state | schedulers + meta | dispatch by slack or due-date score |
| Queue-time constrained scheduling | queue-time violation minimization | arrival time, wait duration, queue age stats | schedulers + meta | enforce max-wait thresholds in candidate selection |
| Setup-sensitive sequencing | setup time minimization | task attributes (`material_type`, `color`, custom setup tags) | scheduler and/or meta | add setup-transition cost term in ranking |
| Energy and maintenance-aware scheduling | energy, machine health, service intervals | machine usage/age (`u`, `m_age`, `v`, `b_age`) | schedulers + meta | add health penalty and maintenance windows |
| Joint scheduling + quality coupling | quality-adjusted throughput | queue + machine health + predicted quality | scheduler + tuner coordination through meta | pass quality score features into assignment scoring |

### 7.2 Applied problem families you can model here
- Semiconductor-like multi-stage flow with re-entry patterns.
- Small-batch high-mix production with dynamic arrivals.
- Quality-sensitive job shops where dispatch affects pass rate.
- Preventive-maintenance-aware flow-shop rescheduling.

### 7.3 Practical guidance for FFSP/HFSP in current architecture
The current A/B/C path is naturally stage-oriented.
To emulate FFSP/HFSP-style logic:
1. Treat A/B/C as stage groups.
2. Add stage-level pressure scores in meta scheduler.
3. Use stage pressure to gate per-stage machine assignment intensity.

---

## Chapter 8. Tuner, APC, and RL Research Extension Space

### Purpose
This chapter covers how to implement modern APC, recipe-control, and RL methods using the existing tuner and meta-scheduler interfaces while preserving safety and reproducibility.

### 8.1 APC/Tuner method matrix

| Method | Control target in this simulator | Required data | Where to implement | Main failure modes | Evaluation metrics |
|---|---|---|---|---|---|
| Run-to-run control | Adjust recipe to correct for previous-run QA deviation | previous QA outcomes, machine age/usage | tuner modules | slow adaptation under abrupt drift | spec violation rate, pass rate trend |
| Model predictive control (MPC) | Predict quality over a planning horizon and preemptively adjust recipe to minimize future spec violations | machine state + queue pressure + constraints | tuner + optional meta coupling | model mismatch, computational latency | pass/rework, constraint violations, solve latency |
| Robust optimization/control | uncertainty-safe recipe selection | QA variance proxies, machine drift indicators | tuner | conservative over-penalization | worst-case quality, robustness under disturbances |
| Bayesian optimization for setpoints | sample-efficient recipe search | recipe-performance history + quality objective | tuner with memory store | local minima, acquisition bias | sample efficiency, best-found quality |
| Contextual bandits | fast contextual recipe adaptation | machine context + queue context + local reward | tuner | delayed reward mismatch | cumulative reward, adaptation speed |
| Constrained RL | policy learning under safety constraints | state, action, safety cost | tuner (or meta+tuner) | unsafe exploration, unstable training | constraint violation count, quality and throughput |
| Digital twin adaptation | model-aligned parameter updates | event logs + process model residuals | tuner + offline model layer | simulation-real gap drift | sim-to-real transfer gap, policy stability |
| LLM-driven Evolutionary Optimization | Iterative evolution of control heuristics or setpoints | decision-state + performance feedback + error logs | supervisory layer or offline algorithm designer | slow convergence, hallucination | code validity, cumulative reward, evolutionary speed |

<!-- ### 8.2 LLM-driven Evolutionary/Iterative Optimization pattern
Following recent research (ReEvo, FunSearch, OPRO), LLM usage should move from one-shot proposals to **reflective evolution** loops:

1.  **Code/Heuristic Initialization:** LLM generates an initial set of control logic or recipes based on the environment description.
2.  **Simulation-in-the-loop Evaluation:** Execute the generated logic within the `ManufacturingEnv`. Collect performance metrics (FPY, throughput, tardiness).
3.  **Reflective Feedback:** Feed the performance results and any runtime errors back to the LLM.
4.  **Evolutionary Operators (LLM-guided):**
    - **Mutation:** LLM refines a single heuristic based on feedback.
    - **Crossover:** LLM combines logic from two high-performing heuristics.
5.  **Safe Deployment:** The best-performing evolved heuristic is gated by a hard validator and deployed as the active policy.

Safety requirements:
- **Validator Gating:** All LLM-generated code or recipes must pass a local symbolic validator (range and schema checks) before hitting the environment.
- **Deterministic Fallback:** If the evolution loop fails to produce a valid candidate within timeout, revert to a known-stable heuristic (e.g., `FIFOTuner`).
- **Observability:** Log the entire lineage of generated heuristics for post-mortem safety analysis. -->

### 8.3 Minimal APC implementation pattern in current code
1. Start from `FIFOTuner` baseline.
2. Add one new tuner class and one new factory mapping.
3. Keep scheduler fixed for first ablation.
4. Report both quality and operational KPIs, not quality only.
5. Optionally override `should_replace_consumable()` (Process A) or `should_replace_solution()` (Process B) to implement data-driven maintenance decisions — see **Section 3.6** for the interface contract and default threshold behavior.

### 8.4 Reward function design for RL research

The default reward function is a minimal placeholder in `src/environment/manufacturing_env.py`:

```python
def _calculate_reward(self, _res_A, _res_B, res_C) -> float:
    return len(res_C.get("completed", []))  # stub: count of completed tasks
```

**Example reward designs:**

| Objective | Reward formula |
|---|---|
| Throughput (default stub) | `len(res_C["completed"])` |
| Tardiness minimization | `-sum(max(0, time - task.due_date) for task in completed_now)` |
| Quality-weighted throughput | `sum(task.realized_qa_B for task in completed_now if task.realized_qa_B > 0)` |
| First-pass yield | `res_A["total_passed"] / max(1, res_A["total_processed"])` |
| Composite (recommended) | `throughput - α * tardiness - β * rework_count - γ * replacement_cost` |

**Where to modify:**
`src/environment/manufacturing_env.py` → `_calculate_reward(self, res_A, res_B, res_C)`

### 8.5 State feature extraction for RL

```python
import numpy as np

def extract_state_vector(decision_state: dict) -> np.ndarray:
    """Convert decision_state snapshot to a flat feature vector for RL."""
    a = decision_state["A"]
    b = decision_state["B"]

    t_norm = decision_state["time"] / max(1, decision_state["max_steps"])
    n_wait_a   = len(a["wait_pool_uids"])
    n_rework_a = len(a["rework_pool_uids"])
    n_wait_b   = len(b["wait_pool_uids"])
    n_rework_b = len(b["rework_pool_uids"])
    u_mean     = np.mean([m["u"]     for m in a["machines"].values()]) if a["machines"] else 0.0
    m_age_mean = np.mean([m["m_age"] for m in a["machines"].values()]) if a["machines"] else 0.0
    v_mean     = np.mean([m["v"]     for m in b["machines"].values()]) if b["machines"] else 0.0

    return np.array([t_norm, n_wait_a, n_rework_a, n_wait_b, n_rework_b,
                     u_mean, m_age_mean, v_mean], dtype=np.float32)
```

### 8.6 Action space design for RL

**Discrete action design (recommended starting point):**
```python
def decode_discrete_action(action_idx: int, state: dict, config: dict) -> dict:
    """Map integer action to V1 action dict for Process A."""
    machines = list(state["A"]["machines"].keys())
    wait_uids = list(state["A"]["wait_pool_uids"])
    actions_A = {}
    for i, machine_id in enumerate(machines):
        n = action_idx % (config["batch_size_A"] + 1)
        batch = wait_uids[:n]
        wait_uids = wait_uids[n:]
        if batch:
            actions_A[machine_id] = {
                "task_uids": batch,
                "recipe": config.get("default_recipe_A", [10.0, 2.0, 1.0]),
                "task_type": "new",
                "replace_consumable": False,
            }
    return {"A": actions_A, "B": {}, "C": {}}
```

**Recommended RL target:** batch selection priority, scheduling ordering, direct recipe parameter tuning, or hybrid combinations.

### 8.7 Minimal gym wrapper skeleton

> **Note:** This skeleton is not included in the base package. Copy it to a new file (e.g., `src/wrappers/gym_env.py`) and adapt observation extraction and action mapping to your specific RL algorithm. The base `ManufacturingEnv` follows a gym-compatible interface (`step`, `reset`) but is not registered as a `gym.Env`.

```python
import gymnasium as gym
from gymnasium import spaces
import numpy as np
from src.environment.manufacturing_env import ManufacturingEnv
from src.agents.factory import build_meta_scheduler

class ManufacturingGymEnv(gym.Env):
    """Minimal gym wrapper for ManufacturingEnv."""

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.env = ManufacturingEnv(config)
        self.meta = build_meta_scheduler(config)

        obs_dim = 8  # match extract_state_vector output
        self.observation_space = spaces.Box(
            low=0.0, high=np.inf, shape=(obs_dim,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(config.get("batch_size_A", 2) + 1)

    def reset(self, seed=None, options=None):
        obs = self.env.reset(seed=seed)
        state = self.env.get_decision_state()
        return extract_state_vector(state), {}

    def step(self, action):
        state = self.env.get_decision_state()
        actions = self.meta.decide(state)
        actions = apply_rl_action_to_A(action, actions, state, self.config)
        obs, reward, done, info = self.env.step(actions)
        next_state = self.env.get_decision_state()
        return extract_state_vector(next_state), reward, done, False, info

    def render(self):
        pass
```

### 8.8 Training stability tips

| Issue | Recommended approach |
|---|---|
| Sparse reward, slow learning | Start with `deterministic_mode=True` to remove stochastic QA noise; add dense intermediate rewards |
| Action space too large | Use existing scheduler/tuner as sub-policy; RL only controls meta-level coordination |
| Unstable episode length | Fix `max_steps` at a small value first (50–100); scale up after policy converges |
| Curriculum design | Increase `num_machines_*` and `max_steps` gradually; start single-product, add multi-product later |
| Known failure mode | Sparse reward without shaping → policy collapses to doing nothing. Always include a small per-step throughput bonus |

---

## Chapter 9. Packing and Multi-Objective Design in Process C

### Purpose
This chapter covers how Process C packing can be extended into a multi-objective optimization stage.

### 9.1 Current packer landscape
- `FIFOPacker`: simple baseline.
- `RandomPacker`: stress baseline for robustness checks.
- `GreedyScorePacker`: weighted objective over quality, compatibility, margin, and timing.

### 9.2 Scoring Function (`GreedyScorePacker`)

The built-in greedy packer evaluates each candidate pack using:

```
Score(Pack) = α·Quality + β·Compatibility + γ·Margin − δ·TimePenalty
```

| Term | Formula | Meaning |
|---|---|---|
| `Quality` | `mean(t.realized_qa_B for t in Pack)` | Prefer high-quality tasks |
| `Compatibility` | `mean(Compat(ti, tj) for all pairs in Pack)` | Prefer compatible material/color pairs |
| `Margin` | `mean(t.margin_value for t in Pack)` | Prefer high-margin tasks |
| `TimePenalty` | `max(0, current_time − min(t.due_date for t in Pack))` | Penalize overdue tasks |

**Default weights (config-injectable):**

| Parameter | Default | Config key |
|---|---:|---|
| α | 1.0 | `alpha_quality` |
| β | 0.5 | `beta_compat` |
| γ | 0.3 | `gamma_margin` |
| δ | 0.2 | `delta_time` |

`GreedyScorePacker` selects top-K candidates by `realized_qa_B`, generates all `N_pack`-size combinations within K, and returns the highest-scoring pack. Trade-off: `K_candidates` controls computation time vs. solution quality.

### 9.3 Multi-objective design pattern
For practical extensions, score terms usually include:
- Product quality aggregation.
- Compatibility constraints.
- Economic margin weighting.
- Queue-time and due-window penalties.
- Stability and feasibility constraints.

### 9.4 Suggested extension targets
- Weight-adaptive pack scoring under changing priorities.
- Fairness-aware pack selection across job families.
- Learned pack ranking with constraint filtering.

---

## PART VI: Implementation Guides

---

## Chapter 10. Extension Playbooks (Engineering Procedures)

### Purpose
This chapter provides step-by-step procedures for adding new algorithms without architectural ambiguity.

### 10.1 Playbook A: Add a new scheduler
1. Add class in `src/schedulers/schedulers_a.py` or `src/schedulers/schedulers_b.py`.
2. Implement `select_batch(...)` with deterministic fallback behavior.
3. Wire policy key in `src/agents/factory.py`.
4. Add/extend tests for duplicate-assignment prevention and queue priorities.

### 10.2 Playbook B: Add a new tuner/APC method
1. Add class in `src/tuners/tuners_a.py` or `src/tuners/tuners_b.py`.
2. Implement `get_recipe(task_rows, machine_state, queue_info, current_time)`.
3. Enforce output recipe sanity checks.
4. Wire configuration mapping in factory.
5. Add evaluation script or test for pass/rework and constraint compliance.

### 10.3 Playbook C: Add a custom meta scheduler
1. Subclass `BaseMetaScheduler` in `src/agents/meta_scheduler.py`.
2. Implement `decide(state)` and return V1-compatible actions.
3. Keep anti-duplication guarantees for task assignment.
4. Add decision-log instrumentation for analysis.

### 10.4 Playbook D: Add a new process (example: Process D)
1. Create `src/environment/process_d_env.py` with `reset`, `add_tasks`, `step`, `get_state`, `event_log`.
2. Add optional machine model in `src/objects.py`.
3. Integrate D into `src/environment/manufacturing_env.py` step order and handoff logic.
4. Extend `get_decision_state()` snapshots.
5. Extend meta scheduler and factory if D requires policies.
6. Add validation tests for flow, overlap, and schema integrity.

### 10.5 End-to-end example: New Scheduler + New Tuner + Factory wiring + Experiment

This walkthrough covers the full development sequence end to end.

#### Step A. Add a scheduler in `src/schedulers/schedulers_a.py`

```python
class UrgencyScheduler(BaseScheduler):
    def should_schedule(self) -> bool:
        return True

    def select_batch(self, wait_pool_uids, rework_pool_uids, batch_size):
        return self._select_with_rework_priority(wait_pool_uids, rework_pool_uids, batch_size)
```

#### Step B. Add a tuner in `src/tuners/tuners_a.py`

```python
class UsageAwareTuner(BaseRecipeTuner):
    def get_recipe(self, task_rows, machine_state, queue_info, current_time):
        u = float(machine_state.get("u", 0))
        if u < 3:
            return [10.0, 2.0, 1.0]
        if u < 7:
            return [12.0, 2.5, 1.2]
        return [14.0, 2.8, 1.4]
```

#### Step C. Wire both in `src/agents/factory.py`

```python
def _build_assignment_scheduler_a(config):
    scheduler_type = config.get("scheduler_A", "fifo")
    if scheduler_type == "urgency":
        return UrgencyScheduler(config)
    ...

def _build_tuner_a(config):
    tuner_type = config.get("tuner_A", config.get("scheduler_A", "fifo"))
    if tuner_type == "usage-aware":
        return UsageAwareTuner(config)
    ...
```

#### Step D. Run an experiment

```python
cfg = {
    "scheduler_A": "urgency",
    "tuner_A": "usage-aware",
    "scheduler_B": "rule-based",
    "packing_C": "greedy",
    "batch_size_A": 2,
    "batch_size_B": 1,
    "batch_size_C": 4,
    "max_steps": 100,
}
```

```bash
python -m tests.test_env_validation_matrix
python -m tests.test_integration
python -m tests.test_gantt_validation
python -m tests.simple_debug_test
```

#### Step E. Report comparison
Use the same seed/config policy and compare against baseline (`scheduler_A=fifo`, `tuner_A=fifo`) on:
1. Spec violation rate.
2. Pass/rework rate.
3. Throughput and completion count.
4. Runtime/inference overhead.

---

## Chapter 11. Case Study Pack (Implementation-Ready Experiments)

### Purpose
This chapter translates research questions into concrete experiments that can be run with minimal ambiguity.

### 11.1 Case study template
Use this template for every study:
1. Research question.
2. Minimal code-touch scope.
3. Config knobs.
4. Baseline vs proposed comparison protocol.
5. Reporting metrics.
6. Expected failure cases and interpretation.

### 11.2 Core case studies

#### Case 1. Batch-size sensitivity under queue pressure
- Question: How does throughput, WIP, and lateness change as batch size scales?
- Knobs: `batch_size_A`, `batch_size_B`, `batch_size_C`, `min_queue_size`, `max_wait_time`.
- Metrics: throughput, avg wait, pack frequency, pass/rework.

#### Case 2. FFSP-like stage balancing with bottleneck transfer timing
- Question: Can stage-aware dispatch reduce starvation/blocking effects?
- Knobs: stage pressure weights, assignment limits per stage.
- Metrics: stage utilization, queue oscillation, completion time.

#### Case 3. Rework-aware tardiness minimization
- Question: Does explicit rework prioritization reduce tardiness without quality collapse?
- Knobs: rework priority weights, due-date slack thresholds.
- Metrics: tardiness, rework completion lead time, pass/rework trend.

#### Case 4. Quality-coupled scheduling plus recipe tuning
- Question: Is joint assignment-control better than independent heuristics?
- Knobs: quality penalty weights, machine health thresholds.
- Metrics: first-pass yield, throughput, spec violations.

#### Case 5. Energy/maintenance-aware dispatching
- Question: Can health-aware dispatch stabilize quality while controlling maintenance events?
- Knobs: age penalties, replacement thresholds.
- Metrics: replacements, quality drift, cycle time.

#### Case 6. APC comparison (rule-based vs MPC vs BO-style tuner)
- Question: Which APC strategy gives best quality under bounded compute budget?
- Knobs: horizon length, BO budget, fallback policy.
- Metrics: pass rate, violation rate, inference latency.

#### Case 7. LLM-based tuner vs deterministic baseline
- Question: Can LLM-supervisory suggestions improve adaptation without safety regressions?
- Knobs: validator strictness, timeout threshold, fallback trigger policy.
- Metrics: spec violation rate, pass/rework, fallback rate, average latency, inference cost.
- Safety interpretation: Any violation increase requires tightening validators before claiming gains.

### 11.3 Extended scenarios: realistic manufacturing constraints

#### Case 8. Multi-product high-mix scheduling
- Question: With product-type-specific spec windows, what dispatch strategy minimizes cross-type interference?
- Setup: Add `product_type` to `Task` (see Chapter 4.2); define 2–3 spec profiles; vary mix ratio.
- Knobs: product mix ratio, spec window width per product.
- Metrics: per-product FPR, total WIP, due-date compliance rate per product family.

#### Case 9. Machine breakdown and emergency recovery
- Question: Under random breakdown events, which dispatch policy minimizes tardiness spikes?
- Setup: Add `breakdown_prob` config key; in `process_a_env.py` step, randomly set `machine.is_broken = True` for `breakdown_duration` steps.
- Knobs: `breakdown_prob` (0.01–0.05), `breakdown_duration` (3–10 steps), arrival rate.
- Metrics: tardiness spike magnitude, recovery lead time, throughput vs. no-breakdown baseline.

#### Case 10. Buffer limits and WIP control
- Question: With finite inter-stage buffers, what dispatch policy prevents blocking cascades?
- Setup: Add `max_buffer_A`, `max_buffer_B` config keys; in `should_schedule()`, return `False` when `len(wait_pool) >= max_buffer`.
- Knobs: `max_buffer_A` (5–20), `max_buffer_B` (3–10), arrival rate multiplier.
- Metrics: blocking frequency, WIP oscillation amplitude, downstream starvation rate.

---

## PART VII: Reference and Roadmap

---

## Chapter 12. Full Parameter and Contract Reference

### Purpose
This chapter provides an operational parameter reference with effect directions, interactions, and safe experiment defaults.

### 12.1 Core simulation parameters

| Key | Default | Effect direction | Interaction notes | Safe experiment range |
|---|---:|---|---|---|
| `num_machines_A` | 10 | up -> A capacity up | interacts with A queue pressure | 1 to 10 for local studies |
| `num_machines_B` | 5 | up -> B capacity up | interacts with B bottleneck behavior | 1 to 10 |
| `num_machines_C` | 1 | up -> potential C capacity up | default meta uses first machine key for action | 1 to 4 |
| `process_time_A` | 15 | up -> A completion slower | impacts same-step downstream load | 1 to 30 |
| `process_time_B` | 4 | up -> B completion slower | strongly affects C queue buildup | 1 to 20 |
| `batch_size_A` | 1 | up -> larger A assignments | may increase burstiness to B | 1 to 8 |
| `batch_size_B` | 1 | up -> larger B assignments | may increase burstiness to C | 1 to 8 |
| `batch_size_C` | 4 | up -> larger pack needed | coupled with `min_queue_size` | 1 to 10 |
| `N_pack` | alias | same as `batch_size_C` | normalized by env | legacy alias for `batch_size_C`; prefer `batch_size_C` in new configs |
| `min_queue_size` | normalized | up -> pack trigger delayed | clamped to not exceed `batch_size_C` | 1 to `batch_size_C` |
| `max_wait_time` | 30 | down -> timeout packs earlier | interacts with throughput vs waiting tradeoff | 5 to 60 |
| `max_packs_per_step` | 1 | up -> C can complete multiple packs per step | coupled with `num_machines_C` | 1 to 4 |
| `max_steps` | 1000 | up -> longer horizon | affects workload and late-arrival behavior | 50 to 5000 |
| `deterministic_mode` | False | True -> no stochastic QA noise | useful for controlled ablation | True or False |

### 12.2 Policy selection keys

| Key | Default | Valid values | Notes |
|---|---|---|---|
| `scheduler_A` | `fifo` | `fifo`, `adaptive`, `rl` | assignment only |
| `scheduler_B` | `rule-based` | `fifo`, `rule-based`, `rl` | assignment only |
| `tuner_A` | fallback to `scheduler_A` | `fifo`, `adaptive`, `rl` | recipe/control |
| `tuner_B` | fallback to `scheduler_B` | `fifo`, `rule-based`, `rl` | recipe/control |
| `packing_C` | `greedy` | `fifo`, `random`, `greedy` | C packing |

> **Tuner fallback behavior:** If `tuner_A` is not set in the config, it inherits the value of `scheduler_A`. Same for `tuner_B` / `scheduler_B`. This allows a single key to control both scheduling and tuning strategies simultaneously, useful for quick baselines.

> **RL scaffold behavior:** `RLBasedScheduler` (A and B) and `RLBasedTuner` (A and B) are scaffold classes. In the current implementation they fall back to their heuristic counterparts (`FIFOScheduler`, `RuleBasedScheduler`, `FIFOTuner`, `RuleBasedTuner`). To implement an actual RL policy, override `select_batch()` / `get_recipe()` inside the scaffold class.

### 12.3 Tuner/APC parameter keys

| Key | Default | Effect direction | Safe range |
|---|---:|---|---|
| `default_recipe_A` | `[10.0, 2.0, 1.0]` | baseline A setpoint | domain-specific |
| `consumable_replace_threshold` | 10 | up -> consumable replaced less often | 5 to 30 |
| `u_fresh_threshold` | 3 | up -> fresh-state window larger | 1 to 10 |
| `u_medium_threshold` | 7 | up -> medium-state window larger | 2 to 20 |
| `recipe_a_fresh` | `[10.0, 2.0, 1.0]` | affects low-usage quality | domain-specific |
| `recipe_a_medium` | `[12.0, 2.5, 1.2]` | affects mid-usage quality | domain-specific |
| `recipe_a_old` | `[15.0, 3.0, 1.5]` | compensates high-usage drift | domain-specific |
| `default_recipe_B` | `[50.0, 50.0, 30.0]` | baseline B setpoint (FIFOTuner) | domain-specific |
| `solution_replace_threshold` | 20 | up -> solution replaced less often | 5 to 50 |
| `v_fresh_threshold` | 5 | up -> fresh-solution region larger | 1 to 20 |
| `v_medium_threshold` | 15 | up -> medium-solution region larger | 2 to 40 |
| `b_age_new_threshold` | 10 | up -> new-machine state extended | 1 to 100 |
| `b_age_medium_threshold` | 50 | up -> medium-machine state extended | 2 to 200 |

> **Process B `RuleBasedTuner` recipe matrix:** uses a 9-combination lookup keyed by `(solution_state ∈ {fresh, medium, old}, machine_state ∈ {new, medium, old})`. State boundaries are controlled by `v_fresh_threshold`, `v_medium_threshold`, `b_age_new_threshold`, `b_age_medium_threshold`. An additional ±10% spec_b midpoint adjustment scales the selected recipe up or down based on the target quality window. See `src/tuners/tuners_b.py` for the full matrix.

### 12.4 C packer objective keys

| Key | Default | Effect direction | Safe range |
|---|---:|---|---|
| `alpha_quality` | 1.0 | up -> quality dominates score | 0.1 to 5.0 |
| `beta_compat` | 0.5 | up -> compatibility dominates | 0.0 to 5.0 |
| `gamma_margin` | 0.3 | up -> economic margin dominates | 0.0 to 5.0 |
| `delta_time` | 0.2 | up -> lateness penalty stronger | 0.0 to 5.0 |
| `K_candidates` | 15 | up -> broader search, slower runtime | 5 to 100 |
| `random_seed` | `None` | set -> reproducible random packing | integer |

### 12.5 Reset and scenario controls

| API input | Default | Behavior |
|---|---|---|
| `reset(seed_initial_tasks=True, initial_tasks=None, seed=None)` | default seeding enabled | auto-generate initial arrivals |
| `seed_initial_tasks=False` | off | starts empty unless `initial_tasks` provided |
| `initial_tasks=[...]` | none | exact controlled injection for scenario isolation |
| `seed=<int>` | none | fixes RNG state for reproducible stochastic runs |

### 12.6 Contract constraints summary
- State contract: read-only snapshot for decision.
- Action contract: V1 schema and process-keyed payload.
- Event contract: immutable trace used by validation and Gantt generation.

### 12.7 Optional future LLM keys (example only, not implemented contract)
- `llm_supervisor_enabled`
- `llm_timeout_ms`
- `llm_validator_profile`
- `llm_fallback_policy`

---

## Chapter 13. Validation and Reproducible Experiment Protocol

### Purpose
This chapter defines a reproducible protocol for correctness and comparative method evaluation.

### 13.1 Core validation commands

```bash
python -m tests.test_env_validation_matrix
python -m tests.test_integration
python -m tests.test_gantt_validation
python -m tests.simple_debug_test
```

### 13.2 Recommended result artifacts
- `results/scenario1_gantt_direct.png`
- `results/scenario2_gantt_direct.png`
- `results/scenario3_gantt_direct.png`
- `results/scenario4_gantt_direct.png`
- `results/scenario5_gantt_direct.png`

### 13.3 Documentation validation scenarios
Use these scenarios to validate the quality of this handbook itself:
1. A new researcher runs quick-start without asking for hidden assumptions.
2. An engineer adds one scheduler from the playbook only.
3. An engineer adds one tuner/APC method from the playbook only.
4. A team drafts Process D extension plan without unresolved design decisions.
5. A researcher reproduces baseline validation protocol and reports comparable metrics.
6. A researcher designs an LLM-supervisory tuner experiment with explicit safety guards and fallback.

### 13.4 Reporting template
For each experiment report include:
- Goal and hypothesis.
- Config snapshot.
- Seed policy.
- Baseline and proposed methods.
- KPI table (quality, throughput, waiting, compute cost).
- Failure analysis and rollback conditions.

---

## Chapter 14. Open Research Problems

### Purpose
This chapter connects the current repository to realistic high-impact research directions for 2024–2027.

### 14.1 Open problems mapped to this repository
- Robust multi-stage scheduling under coupled quality drift.
- Joint dispatch and control under non-stationary process conditions.
- Safety-bounded LLM supervision for industrial decision support.
- Cost-aware balancing of quality, delay, and compute/inference latency.
- Sim-to-real transfer of control and packing decisions.

### 14.2 Near-term practical roadmap for this toolkit
1. Introduce explicit policy-evaluation dashboards from event logs.
2. Add optional memory stores for tuner history and BO loops.
3. Add formal safety validator interfaces for candidate action gating.
4. Add example notebooks for scheduler and APC benchmarking.
5. Add optional LLM-supervisory wrapper examples with deterministic fallback.

<!-- ### 14.3 Recent Research Map (2023–2026, curated)
Reference format: `Year | Venue | Title | Link | Core contribution | Code mapping`

| Year | Venue | Title | Link | Core contribution | Code mapping |
|---:|---|---|---|---|---|
| 2024 | Nature | Mathematical discoveries from program search with LLMs (FunSearch) | https://doi.org/10.1038/s41586-023-06924-6 | Evolutionary code discovery for combinatorial problems | Offline heuristic designer |
| 2024 | ICLR | Large Language Models as Optimizers (OPRO) | https://arxiv.org/abs/2309.03409 | Optimization through iterative prompting with history | Prompt-driven setpoint optimizer |
| 2024 | NeurIPS | ReEvo: Large Language Models as Hyper-Heuristics with Reflective Evolution | https://arxiv.org/abs/2402.01145 | Reflective evolution loop for combinatorial optimization | Evolutionary supervisory layer |
| 2024 | NeurIPS | Difusco: Graph-based Diffusion Solvers for Combinatorial Optimization | https://proceedings.neurips.cc/paper_files/paper/2023/hash/difusco | Generative diffusion model for graph combinatorial problems | `src/schedulers/*` (Generative) |
| 2024 | IEEE RA-L | GOPT: Generalizable Online 3D Bin Packing via Transformer-based DRL | https://doi.org/10.1109/LRA.2024.3468161 | Transformer-based policy for online packing | `src/schedulers/packers_c.py` |
| 2024 | Mathematics | Integrating Heuristic Methods with DRL for Online 3D Bin-Packing Optimization | https://doi.org/10.3390/math12091395 | Hybrid Heuristic-PPO for stable packing | `src/schedulers/packers_c.py` |
| 2024 | IEEE TCYB | Multiobjective Flexible Job-Shop Rescheduling With New Job Insertion and PM | https://doi.org/10.1109/TCYB.2022.3151855 | Joint scheduling and maintenance optimization | `src/schedulers/*` + `src/tuners/*` |
| 2025 | IJCAI | A survey of optimization modeling meets LLMs | https://arxiv.org/abs/2402.01145 | LLM integration patterns for optimization workflows | Supervisory layer design |
| 2024 | IEEE TII | Flexible Job-Shop Scheduling via Graph Neural Network and DRL | https://doi.org/10.1109/TII.2024.3351234 | Heterogeneous GNN policy for flexible assignment | `src/schedulers/*` (GNN-based) |
| 2024 | Comp. & Chem. Eng. | Model-based safe reinforcement learning for nonlinear systems | https://doi.org/10.1016/j.compchemeng.2024.108601 | Safety-constrained learning formulation | Tuner + safety validator |
| 2023 | European Journal of Operational Research | A systematic review of multi-objective hybrid flow shop scheduling | https://doi.org/10.1016/j.ejor.2022.08.009 | Classification of MOHFS problem types and Pareto optimization methods | `src/environment/manufacturing_env.py` (A→B→C structure) + `src/schedulers/*` |
| 2023 | Nature | Human–machine collaboration for improving semiconductor process development | https://doi.org/10.1038/s41586-023-05773-7 | Bayesian optimization of semiconductor recipe parameters | `src/tuners/tuners_a.py`, `src/tuners/tuners_b.py` |
| 2022 | Quality and Reliability Engineering International | Condition-based preventive maintenance with a yield rate threshold | https://doi.org/10.1002/qre.3191 | Uses product yield/quality rate as the condition variable for PM | `should_replace_consumable()` in `src/tuners/tuners_a.py`, `should_replace_solution()` in `src/tuners/tuners_b.py` |
| 2023 | Production and Operations Management | Robust condition-based production and maintenance planning | https://doi.org/10.1111/poms.14071 | Joint scheduling and maintenance timing under degradation state | `src/agents/default_meta_scheduler.py` + `src/tuners/*` | -->

---

## Chapter 15. Practical Adoption Path

### Purpose
This chapter answers the question manufacturing engineers ask most: "How do I actually apply this to my factory?"
It provides a step-by-step adoption roadmap and a complexity-level guide for deciding where to start.

### 15.1 Step-by-step adoption roadmap

#### Step 1: Simplify and map your process

Start by abstracting your factory to the A→B→C structure:
- Identify which of your process stages maps to A (machining/processing), B (inspection/cleaning), and C (grouping/shipment).
- Decide which Task attributes you need: `due_date`, `product_type`, `priority_class`, `setup_group` (see Chapter 4).
- Decide on physical model fidelity: start with default equations, then replace them if your process dynamics differ significantly (see Section 3.5).

Deliverable: a config dict and a `Task` schema that covers your production case.

#### Step 2: Implement and validate your baseline rule

Before any AI, implement the dispatch rule your factory currently uses (FIFO, EDD, SPT, etc.) as a scheduler:
- Use Playbook A (Section 10.1) to add the rule as a new scheduler class.
- Measure KPIs using the pattern in Chapter 5.
- Compare your simulator KPIs against real historical data. If they diverge significantly, adjust the physical model or arrival rate before proceeding.

Deliverable: a confirmed baseline KPI profile (throughput, FPR, tardiness, rework rate).

#### Step 3: Run controlled policy comparisons

Select the most relevant case studies from Chapter 11 as experiment templates:
- Fix `seed`, config, and arrival scenario across all runs.
- Compare only one variable at a time (e.g., scheduler only, or tuner only).
- Use Chapter 13 validation commands to confirm no integrity regressions.

Deliverable: a comparison table of baseline vs. proposed policy across 3–5 KPIs.

#### Step 4: Introduce AI policies incrementally

Follow this order to limit risk at each step:
1. **Scheduler only** — swap the assignment policy; keep tuner fixed as `fifo`.
2. **Tuner only** — keep scheduler fixed; change the recipe/APC logic.
3. **Meta scheduler** — change cross-process coordination; keep per-process policies.
4. **Joint (scheduler + tuner)** — only after steps 1–3 validate independently.

At each step, run the full validation suite and confirm KPIs vs. the baseline established in Step 2.

#### Step 5: Sensitivity analysis

Before claiming results, check how robust your policy is to parameter variation:
- Vary `arrival_period` ±20%.
- Vary `breakdown_prob` if applicable (Case 9).
- Vary `batch_size_*` across the safe experiment range (Chapter 12).

Deliverable: sensitivity table showing KPI changes under parameter perturbation.

#### Step 6: Sim-to-real considerations

When moving validated policies toward real deployment:
- The physical models (Process A, B, C) are simplifications. Validate key dynamics (FPR vs. u, m_age effect) against real process data before relying on them for deployment decisions.
- Replace `_run_qa_check(...)` with a surrogate model trained on real process data if available (Section 3.5, Example B).
- Real systems have unmodeled effects (temperature variation, operator behavior, lot-to-lot material variance). Account for these in safety margins.
- Consider deploying as a decision-support tool first (suggest rather than auto-execute) to build operational trust.

### 15.2 Expansion complexity guide

| Goal | Files to touch | Estimated effort |
|---|---|---|
| Change a config parameter | config dict only | 5 minutes |
| Add a custom KPI | `manufacturing_env.py` or post-processing | ~1 hour |
| Add a new scheduler | `schedulers_a/b.py` + `factory.py` | 2–4 hours |
| Add a new tuner / APC method | `tuners_a/b.py` + `factory.py` | 2–4 hours |
| Replace the physical model (Process A or B) | `process_a_env.py` or `process_b_env.py` | 4–8 hours |
| Add custom Task attributes | `src/objects.py` + `data_generator.py` | 2–4 hours |
| Add breakdown / buffer-limit constraints | Process env + scheduler | 4–8 hours |
| Add a new process stage (Process D) | New env file + `manufacturing_env.py` integration | 1–2 days |
| Implement an RL policy | gym wrapper + tuner or meta scheduler | 1–3 days |
| Replace physical model with ML surrogate | `process_*_env.py` + surrogate training | 2–5 days |

### 15.3 Known adoption pitfalls

| Pitfall | How to avoid |
|---|---|
| Simulator KPIs don't match real factory | Calibrate arrival rate and process time before comparing policies |
| RL policy doesn't converge | Start with `deterministic_mode=True`; add dense intermediate reward; use short `max_steps` |
| New scheduler breaks downstream integrity | Run `test_env_validation_matrix` after every code change |
| Claiming results without baseline | Always establish and report a baseline under identical seed and scenario |
| Sim-to-real gap overlooked | Document model assumptions explicitly; validate key dynamics against historical data |

---

## Appendix A. Glossary
- Decision state: read-only snapshot consumed by policies.
- Handoff: same-step transfer of passed tasks between processes.
- Rework: failed task routed back for reprocessing.
- FPR (First-Pass Rate): fraction of tasks that pass QA on the first attempt, without rework.
- Scheduler: assignment policy selecting task batches.
- Tuner: recipe/control policy producing process parameters.
- Packer: final-stage grouping policy for C.
- Meta scheduler: orchestrator that composes scheduler, tuner, and packer outputs.
- WIP (Work-in-Process): tasks currently inside the system (waiting, in-process, or in rework).
- Lead Time: total elapsed time from a task's arrival to its completion.
- Tardiness: amount by which a task's completion time exceeds its due date (`max(0, end − due)`).

## Appendix B. Terminology Map

| Concept | In this repo |
|---|---|
| Stage | Process A, B, C |
| Dispatching | Scheduler `select_batch(...)` |
| Process control / APC | Tuner `get_recipe(...)` |
| Orchestration | Meta scheduler `decide(...)` |
| Plant transition | `ManufacturingEnv.step(...)` |
| Runtime observability | event logs + `get_decision_state()` |
| KPI tracking | event log post-processing (Chapter 5) |
| Factory adaptation | Chapter 4 mapping + Chapter 15 adoption path |

**Tuner vs APC**: "Tuner" is the code-level term used in this repository (`src/tuners/*`, base class `BaseRecipeTuner`). "APC" (Adaptive Process Control) is the manufacturing domain term for the same concept. They are interchangeable in this handbook — "Tuner" refers to the implementation class, "APC" refers to the algorithm category it implements.

## Appendix C. Quick-Start Checklists

### C.1 Add a new scheduler
1. Implement class in `src/schedulers/*`.
2. Wire to `src/agents/factory.py`.
3. Run validation matrix.
4. Compare against baseline with same seeds.

### C.2 Add a new tuner or APC method
1. Start from deterministic fallback tuner.
2. Add new method with bounded outputs.
3. Add validator checks for recipe ranges.
4. Run integration + Gantt validation.
5. Report pass/rework and latency.

### C.3 Add a new packer or Process C strategy
1. Implement a class in `src/schedulers/packers_c.py`, extending `BasePacker`.
2. Override `should_pack(wait_pool, current_time, last_pack_time)` and `select_pack(wait_pool, current_time)`.
3. Register the new key in `src/agents/factory.py` under `_build_packer_c()`.
4. Run integration test with `packing_C=<your_key>` and verify completed task counts.
5. Compare against the `greedy` baseline under identical seeds.

### C.4 Adapt to a real factory (quick checklist)
1. Map process stages to A/B/C (Chapter 4).
2. Define Task attributes for your product mix.
3. Implement baseline dispatch rule as a scheduler.
4. Measure KPI baseline (Chapter 5).
5. Validate simulator KPIs against historical data.
6. Introduce AI policies one layer at a time (Chapter 15).

---

This handbook is a research and engineering reference for modular manufacturing simulation.
It defines a platform for studying the structured interaction of scheduling, process control, and cross-stage coupling — and provides the tools to extend, adapt, and validate those studies systematically.
