# Extensible Manufacturing Simulation Toolkit

A Research-Facing Hybrid Handbook for Modular Manufacturing Simulation and Method Development.

## Preface

Modern manufacturing research increasingly requires fast iteration across three tightly coupled decision layers:
1. State transition and process physics.
2. Scheduling and dispatching.
3. Process control and recipe adaptation.

This repository is designed as a modular research box where those layers are separable, composable, and testable.
The practical goal is simple: a researcher should be able to take this codebase, plug in a new algorithm, run controlled experiments, and report reproducible results without rewriting the environment core.

The default production path is `A -> B -> C`, but the architecture is intentionally extensible to additional processes, additional policies, and additional control paradigms.

This handbook is chapterized and implementation-oriented. It explains both what exists today and how to extend it safely.

![Simulation Process Flow](figures/process_flow.png)

## Table of Contents

1. [Preface](#preface)
2. [5-Minute Quick Start](#5-minute-quick-start)
3. [Chapter 1. System Philosophy and Modular Boundary](#chapter-1-system-philosophy-and-modular-boundary)
4. [Chapter 2. Runtime Semantics and Data Contracts](#chapter-2-runtime-semantics-and-data-contracts)
5. [Chapter 3. Environment Internals and Physical-Model Customization](#chapter-3-environment-internals-and-physical-model-customization)
6. [Chapter 4. Scheduling Research Extension Space (Manufacturing-First)](#chapter-4-scheduling-research-extension-space-manufacturing-first)
7. [Chapter 5. Tuner and APC Research Extension Space (LLM-Integrated)](#chapter-5-tuner-and-apc-research-extension-space-llm-integrated)
8. [Chapter 6. Packing and Multi-Objective Design in Process C](#chapter-6-packing-and-multi-objective-design-in-process-c)
9. [Chapter 7. Extension Playbooks (Engineering Procedures)](#chapter-7-extension-playbooks-engineering-procedures)
10. [Chapter 8. Case Study Pack (Implementation-Ready Experiments)](#chapter-8-case-study-pack-implementation-ready-experiments)
11. [Chapter 9. Full Parameter and Contract Reference](#chapter-9-full-parameter-and-contract-reference)
12. [Chapter 10. Validation and Reproducible Experiment Protocol](#chapter-10-validation-and-reproducible-experiment-protocol)
13. [Chapter 11. Open Research Problems and Near-Term Roadmap](#chapter-11-open-research-problems-and-near-term-roadmap)
14. [Appendix A. Glossary](#appendix-a-glossary)
15. [Appendix B. Terminology Map](#appendix-b-terminology-map)
16. [Appendix C. Quick-Start Checklists](#appendix-c-quick-start-checklists)

## 5-Minute Quick Start

This page is a minimal path for first-time users to run the toolkit and verify that the environment-control loop works end to end.

### Goal
In five minutes, you should be able to:
1. Run a full regression sanity check.
2. Run one integrated simulation.
3. Generate/inspect gantt outputs.

### Step 1. Environment check

```bash
conda run -n batch_env python -V
conda run -n batch_env python -m tests.test_env_validation_matrix
```

Expected outcome:
- The test module exits without assertion failures.

### Step 2. Run a scenario-level integration

```bash
conda run -n batch_env python -m tests.test_gantt_validation
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
- `num_completed` is non-negative and typically positive in standard scenarios.

### Step 4. Read outputs
- Use chapter 2 for state/action/event semantics.
- Use chapter 10 for validation protocol.
- Use chapter 8 for research-ready case templates.

## Chapter 1. System Philosophy and Modular Boundary

### Purpose
Define the design philosophy and hard module boundaries so that algorithmic experimentation does not break environment integrity.

### What You Can Change
- External scheduling logic.
- Recipe tuning and advanced control logic.
- Packing objective design.
- Process-specific equations and failure/rework behavior.

### What Stays Invariant
- `ManufacturingEnv` remains transition-centric.
- The loop remains `state -> decide -> step`.
- Actions are externally provided and sanitized before execution.
- Testability and event-log traceability remain first-class constraints.

### 1.1 Architectural boundary in one sentence
The environment executes transitions, while decision modules decide assignments and control actions.

### 1.2 Why this boundary matters for research
In many manufacturing studies, claims fail to generalize because environment logic and controller logic are entangled.
This project avoids that by isolating responsibilities:
- `src/environment/*`: process semantics and state transition.
- `src/agents/*`: orchestration and action generation.
- `src/schedulers/*`: assignment policy.
- `src/tuners/*`: recipe/control policy.

This separation supports controlled ablation studies such as:
- Same scheduler, different tuner.
- Same tuner, different scheduler.
- Same local policies, different meta-orchestration.

### 1.3 Core execution loop

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

## Chapter 2. Runtime Semantics and Data Contracts

### Purpose
Provide an exact and reproducible contract for state snapshots, action payloads, event logs, and same-step handoff timing.

### What You Can Change
- Decision logic that builds actions.
- Queue priority and batching policy.
- Which parts of decision state your policy consumes.

### What Stays Invariant
- Handoff order: A step, then B step, then C step.
- Decision state is read-only snapshot data.
- Missing action for a process is a no-op, not implicit auto-dispatch.

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

### 2.3 Action schema

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

### 2.4 Event schema (analysis contract)

| Process | Event types | Typical fields |
|---|---|---|
| A | `task_assigned`, `task_completed` | `timestamp`, `machine_id`, `task_uids`, `start_time`, `end_time`, `task_type` |
| B | `task_assigned`, `task_completed` | same as A |
| C | `task_queued`, `pack_completed` | queue and pack lifecycle fields, `pack_id` |

### 2.5 Integrity invariants used by tests
- No duplicate assignment of the same task UID in one decision cycle.
- No machine overlap in assignment intervals.
- Monotonic flow consistency across A -> B -> C.
- Rework count is non-decreasing.
- Strict external control: no action means no new dispatching.

## Chapter 3. Environment Internals and Physical-Model Customization

### Purpose
Explain where process behavior lives, where equations live, and how to modify them without breaking orchestration.

### What You Can Change
- Physical equations and degradation models in process env modules.
- QA pass/fail rules and stochastic behavior.
- Task attributes and compatibility logic.

### What Stays Invariant
- Process environments remain responsible for transition semantics.
- `ManufacturingEnv` remains responsible for top-level orchestration and handoff.
- External action contract remains V1 in this pass.

### 3.1 Process A (`src/environment/process_a_env.py`)
A includes age and consumable dynamics (`m_age`, `u`) and computes QA from recipe and model coefficients.

Representative structure:
- Age-adjusted coefficients.
- Nonlinear process signal term.
- Effectiveness reduction with usage.
- Stochastic noise (unless deterministic mode).
- Inclusive QA boundary for spec check.

Primary edit points for advanced studies:
- `_get_physical_model_params(...)`
- `_run_qa_check(...)`
- pass/fail boundary definition

### 3.2 Process B (`src/environment/process_b_env.py`)
B uses a simplified quality screening model with machine state influence (`v`, `b_age`) and strict boundary checking.

Primary edit points:
- `_run_qa_check(...)`
- recipe parsing and defaulting
- clipping and degradation behavior

### 3.3 Process C (`src/environment/process_c_env.py`)
C handles queueing, selection, compatibility, and final pack completion metrics.

Primary edit points:
- `_init_compatibility_matrix(...)`
- `_compute_compatibility(...)`
- `_create_pack_info(...)`

### 3.4 Common safe-edit workflow
1. Change only one process model at a time.
2. Keep action schema stable.
3. Re-run validation matrix and gantt validation after each model change.
4. Compare event logs before and after for regressions.

## Chapter 4. Scheduling Research Extension Space (Manufacturing-First)

### Purpose
Map modern manufacturing scheduling families to concrete extension points in this codebase.

### What You Can Change
- Batch selection logic.
- Queue priority logic.
- Process-coupled dispatch features.
- Meta-level cross-process coordination.

### What Stays Invariant
- Scheduler modules remain assignment-focused.
- Recipe tuning remains outside scheduler in tuner modules.
- Environment remains external-action driven.

### 4.1 Scheduling Applicability Matrix

| Scheduling family | Typical objectives | Required signals from `decision_state` | Exact insertion point | Minimal prototype path |
|---|---|---|---|---|
| Batch scheduling | makespan, throughput, WIP | queue sizes, machine `batch_size`, waiting UIDs | `src/schedulers/schedulers_a.py`, `src/schedulers/schedulers_b.py` | modify `select_batch(...)` with batch-aware heuristics |
| FFSP/HFSP stage mapping | stage balance, bottleneck relief | per-stage queue lengths, machine status, incoming UIDs | `src/agents/default_meta_scheduler.py` + schedulers | add stage-priority logic in meta orchestration before per-process calls |
| Rework-aware scheduling | rework debt, FPY, tardiness | `rework_pool_uids`, `rework_count`, due date | schedulers + meta | prioritize rework via weighted queue policy |
| Due-date/tardiness control | tardiness, lateness, OTIF | `due_date`, time, queue state | schedulers + meta | dispatch by slack or due-date score |
| Queue-time constrained scheduling | queue-time violation minimization | arrival time, wait duration, queue age stats | schedulers + meta | enforce max-wait thresholds in candidate selection |
| Setup-sensitive sequencing (extension target) | setup time minimization | task attributes (`material_type`, `color`, custom setup tags) | scheduler and/or meta | add setup-transition cost term in ranking |
| Energy and maintenance-aware scheduling | energy, machine health, service intervals | machine usage/age (`u`, `m_age`, `v`, `b_age`) | schedulers + meta | add health penalty and maintenance windows |
| Joint scheduling + quality coupling | quality-adjusted throughput | queue + machine health + predicted quality | scheduler + tuner coordination through meta | pass quality score features into assignment scoring |

### 4.2 Applied problem families you can model here
- Semiconductor-like multi-stage flow with re-entry patterns.
- Small-batch high-mix production with dynamic arrivals.
- Quality-sensitive job shops where dispatch affects pass rate.
- Preventive-maintenance-aware flow-shop rescheduling.

### 4.3 Practical guidance for FFSP/HFSP in current architecture
The current A/B/C path is naturally stage-oriented.
To emulate FFSP/HFSP-style logic:
1. Treat A/B/C as stage groups.
2. Add stage-level pressure scores in meta scheduler.
3. Use stage pressure to gate per-stage machine assignment intensity.
## Chapter 5. Tuner and APC Research Extension Space (LLM-Integrated)

### Purpose
Define how to implement modern APC and recipe-control methods using the existing tuner interfaces while preserving safety and reproducibility.

### What You Can Change
- Tuner logic in `src/tuners/tuners_a.py` and `src/tuners/tuners_b.py`.
- Meta-level coupling between scheduling and tuning.
- Policy selection rules in `src/agents/factory.py` and custom meta schedulers.

### What Stays Invariant
- Tuners output recipe vectors through `get_recipe(...)`.
- The environment does not auto-tune internally.
- Hard execution constraints must remain enforceable before action application.

### 5.1 APC/Tuner method matrix

| Method | Control target in this simulator | Required data | Where to implement | Main failure modes | Evaluation metrics |
|---|---|---|---|---|---|
| Run-to-run control | lot-to-lot recipe correction | previous QA outcomes, machine age/usage | tuner modules | slow adaptation under abrupt drift | spec violation rate, pass rate trend |
| Model predictive control (MPC) | horizon-aware recipe planning | machine state + queue pressure + constraints | tuner + optional meta coupling | model mismatch, computational latency | pass/rework, constraint violations, solve latency |
| Robust optimization/control | uncertainty-safe recipe selection | QA variance proxies, machine drift indicators | tuner | conservative over-penalization | worst-case quality, robustness under disturbances |
| Bayesian optimization for setpoints | sample-efficient recipe search | recipe-performance history + quality objective | tuner with memory store | local minima, acquisition bias | sample efficiency, best-found quality |
| Contextual bandits | fast contextual recipe adaptation | machine context + queue context + local reward | tuner | delayed reward mismatch | cumulative reward, adaptation speed |
| Constrained RL | policy learning under safety constraints | state, action, safety cost | tuner (or meta+tuner) | unsafe exploration, unstable training | constraint violation count, quality and throughput |
| Digital twin adaptation | model-aligned parameter updates | event logs + process model residuals | tuner + offline model layer | simulation-real gap drift | sim-to-real transfer gap, policy stability |
| LLM-assisted supervisory tuning (constraint-bounded) | candidate recipe/policy proposal from structured context | decision-state slices + recent event summaries | optional supervisory layer in tuner or meta | hallucinated or infeasible proposals, latency spikes | spec violation, pass/rework, fallback rate, inference cost |

### 5.2 LLM-assisted supervisory tuning design pattern
LLM usage in this toolkit should be supervisory and constraint-bounded:
1. Build structured prompt context from `decision_state` and recent event summaries.
2. Ask LLM for candidate recipe or policy suggestions.
3. Run hard validators (range checks, schema checks, safety checks).
4. If candidate fails, execute deterministic fallback tuner.
5. Log candidate, validator result, and fallback reason for auditability.

Safety requirements for LLM usage:
- LLM proposes candidates only.
- Rule validators gate all actions before execution.
- Deterministic fallback is mandatory on validation failure or timeout.
- LLM is advisor/supervisor, not direct actuator.

Optional future extension note:
- `LLMSupervisoryTuner(BaseRecipeTuner)` implementing `get_recipe(...)` can be added later.
- This is optional and not required by current runtime contract.

### 5.3 Minimal APC implementation pattern in current code
1. Start from `FIFOTuner` baseline.
2. Add one new tuner class and one new factory mapping.
3. Keep scheduler fixed for first ablation.
4. Report both quality and operational KPIs, not quality only.

## Chapter 6. Packing and Multi-Objective Design in Process C

### Purpose
Explain how final-stage packing can be turned into a tunable multi-objective decision layer.

### What You Can Change
- Pack trigger logic (`should_pack`).
- Pack selection logic (`select_pack`).
- Compatibility and quality score definitions.

### What Stays Invariant
- C remains action-driven.
- Pack completion emits event-log records.
- Queue integrity and UID consistency must remain preserved.

### 6.1 Current packer landscape
- `FIFOPacker`: simple and transparent baseline.
- `RandomPacker`: stress baseline for robustness checks.
- `GreedyScorePacker`: weighted objective over quality, compatibility, margin, and timing.

### 6.2 Multi-objective design pattern
For practical extensions, score terms usually include:
- Product quality aggregation.
- Compatibility constraints.
- Economic margin weighting.
- Queue-time and due-window penalties.
- Stability and feasibility constraints.

### 6.3 Suggested extension targets
- Weight-adaptive pack scoring under changing priorities.
- Fairness-aware pack selection across job families.
- Learned pack ranking with constraint filtering.

## Chapter 7. Extension Playbooks (Engineering Procedures)

### Purpose
Provide implementation-ready procedures that remove architectural ambiguity for new methods.

### What You Can Change
- New scheduler classes.
- New tuner classes.
- New packers.
- New meta schedulers.
- New process environments.

### What Stays Invariant
- Keep environment orchestration contract stable.
- Keep V1 action schema stable unless a deliberate migration is planned.
- Keep tests and event logs as the source of truth for behavior.

### 7.1 Playbook A: Add a new scheduler
1. Add class in `src/schedulers/schedulers_a.py` or `src/schedulers/schedulers_b.py`.
2. Implement `select_batch(...)` with deterministic fallback behavior.
3. Wire policy key in `src/agents/factory.py`.
4. Add/extend tests for duplicate-assignment prevention and queue priorities.

### 7.2 Playbook B: Add a new tuner/APC method
1. Add class in `src/tuners/tuners_a.py` or `src/tuners/tuners_b.py`.
2. Implement `get_recipe(task_rows, machine_state, queue_info, current_time)`.
3. Enforce output recipe sanity checks.
4. Wire configuration mapping in factory.
5. Add evaluation script or test for pass/rework and constraint compliance.

### 7.3 Playbook C: Add a custom meta scheduler
1. Subclass `BaseMetaScheduler` in `src/agents/meta_scheduler.py`.
2. Implement `decide(state)` and return V1-compatible actions.
3. Keep anti-duplication guarantees for task assignment.
4. Add decision-log instrumentation for analysis.

### 7.4 Playbook D: Add a new process (example: Process D)
1. Create `src/environment/process_d_env.py` with `reset`, `add_tasks`, `step`, `get_state`, `event_log`.
2. Add optional machine model in `src/objects.py`.
3. Integrate D into `src/environment/manufacturing_env.py` step order and handoff logic.
4. Extend `get_decision_state()` snapshots.
5. Extend meta scheduler and factory if D requires policies.
6. Add validation tests for flow, overlap, and schema integrity.

### 7.5 End-to-end example: New Scheduler + New Tuner + Factory wiring + Experiment

This is a single-path example showing the full development sequence with minimal ambiguity.

#### Step A. Add a scheduler in `src/schedulers/schedulers_a.py`

```python
class UrgencyScheduler(BaseScheduler):
    def should_schedule(self) -> bool:
        return True

    def select_batch(self, wait_pool_uids, rework_pool_uids, batch_size):
        # Keep rework-first invariant, then apply urgency order for new tasks.
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
conda run -n batch_env python -m tests.test_env_validation_matrix
conda run -n batch_env python -m tests.test_gantt_validation
```

#### Step E. Report comparison
Use the same seed/config policy and compare against baseline (`scheduler_A=fifo`, `tuner_A=fifo`) on:
1. Spec violation rate.
2. Pass/rework rate.
3. Throughput and completion count.
4. Runtime/inference overhead.

## Chapter 8. Case Study Pack (Implementation-Ready Experiments)

### Purpose
Translate research questions into concrete experiments that can be run with minimal ambiguity.

### What You Can Change
- Scenario configs.
- Policy choices.
- Objective weighting and KPIs.

### What Stays Invariant
- Report baseline and proposed methods under the same scenario seed policy.
- Keep action/state schema fixed during method comparisons.
- Keep reproducibility artifacts (config, seed, command) in results.

### 8.1 Case study template
Use this template for every study:
1. Research question.
2. Minimal code-touch scope.
3. Config knobs.
4. Baseline vs proposed comparison protocol.
5. Reporting metrics.
6. Expected failure cases and interpretation.

### 8.2 Mandatory case studies

#### Case 1. Batch-size sensitivity under queue pressure
- Question: How does throughput, WIP, and lateness change as batch size scales?
- Minimal code touch: config only.
- Knobs: `batch_size_A`, `batch_size_B`, `batch_size_C`, `min_queue_size`, `max_wait_time`.
- Metrics: throughput, avg wait, pack frequency, pass/rework.

#### Case 2. FFSP-like stage balancing with bottleneck transfer timing
- Question: Can stage-aware dispatch reduce starvation/blocking effects?
- Minimal code touch: meta scheduler scoring only.
- Knobs: stage pressure weights, assignment limits per stage.
- Metrics: stage utilization, queue oscillation, completion time.

#### Case 3. Rework-aware tardiness minimization
- Question: Does explicit rework prioritization reduce tardiness without quality collapse?
- Minimal code touch: scheduler ranking function.
- Knobs: rework priority weights, due-date slack thresholds.
- Metrics: tardiness, rework completion lead time, pass/rework trend.

#### Case 4. Quality-coupled scheduling plus recipe tuning
- Question: Is joint assignment-control better than independent heuristics?
- Minimal code touch: scheduler features + tuner adaptation rules.
- Knobs: quality penalty weights, machine health thresholds.
- Metrics: first-pass yield, throughput, spec violations.

#### Case 5. Energy/maintenance-aware dispatching
- Question: Can health-aware dispatch stabilize quality while controlling maintenance events?
- Minimal code touch: scheduler penalty term for `u/m_age/v/b_age`.
- Knobs: age penalties, replacement thresholds.
- Metrics: replacements, quality drift, cycle time.

#### Case 6. APC comparison (rule-based vs MPC vs BO-style tuner)
- Question: Which APC strategy gives best quality under bounded compute budget?
- Minimal code touch: add tuner implementations and factory mappings.
- Knobs: horizon length, BO budget, fallback policy.
- Metrics: pass rate, violation rate, inference latency.

#### Case 7. LLM-supervisory tuner vs deterministic baseline
- Question: Can LLM-supervisory suggestions improve adaptation without safety regressions?
- Minimal code touch: optional supervisory wrapper around existing tuner.
- Knobs: validator strictness, timeout threshold, fallback trigger policy.
- Metrics: spec violation rate, pass/rework, fallback rate, average latency, inference cost.
- Safety interpretation: Any violation increase requires tightening validators before claiming gains.
## Chapter 9. Full Parameter and Contract Reference

### Purpose
Provide an operational parameter reference with directionality, interactions, and safe experiment defaults.

### What You Can Change
- Scenario-level config values.
- Policy-specific hyperparameters.
- Thresholds and objective weights.

### What Stays Invariant
- Parameter names must align with implemented config keys.
- Contract tables must remain consistent with runtime behavior.
- LLM keys remain optional examples only in this pass.

### 9.1 Core simulation parameters

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
| `N_pack` | alias | same as `batch_size_C` | normalized by env | use with `batch_size_C` only if legacy |
| `min_queue_size` | normalized | up -> pack trigger delayed | clamped to not exceed `batch_size_C` | 1 to `batch_size_C` |
| `max_wait_time` | 30 | down -> timeout packs earlier | interacts with throughput vs waiting tradeoff | 5 to 60 |
| `max_steps` | 1000 | up -> longer horizon | affects workload and late-arrival behavior | 50 to 5000 |
| `deterministic_mode` | False | True -> no stochastic QA noise | useful for controlled ablation | True or False |

### 9.2 Policy selection keys

| Key | Default | Valid values | Notes |
|---|---|---|---|
| `scheduler_A` | `fifo` | `fifo`, `adaptive`, `rl` | assignment only |
| `scheduler_B` | `rule-based` | `fifo`, `rule-based`, `rl` | assignment only |
| `tuner_A` | fallback to `scheduler_A` | `fifo`, `adaptive`, `rl` | recipe/control |
| `tuner_B` | fallback to `scheduler_B` | `fifo`, `rule-based`, `rl` | recipe/control |
| `packing_C` | `greedy` | `fifo`, `random`, `greedy` | C packing |

### 9.3 Tuner/APC parameter keys

| Key | Default | Effect direction | Safe range |
|---|---:|---|---|
| `default_recipe_A` | `[10.0, 2.0, 1.0]` | baseline A setpoint | domain-specific |
| `u_fresh_threshold` | 3 | up -> fresh-state window larger | 1 to 10 |
| `u_medium_threshold` | 7 | up -> medium-state window larger | 2 to 20 |
| `recipe_a_fresh` | `[10.0, 2.0, 1.0]` | affects low-usage quality | domain-specific |
| `recipe_a_medium` | `[12.0, 2.5, 1.2]` | affects mid-usage quality | domain-specific |
| `recipe_a_old` | `[15.0, 3.0, 1.5]` | compensates high-usage drift | domain-specific |
| `default_recipe_B` | `[50.0, 50.0, 30.0]` | baseline B setpoint | domain-specific |
| `v_fresh_threshold` | 5 | up -> fresh-solution region larger | 1 to 20 |
| `v_medium_threshold` | 15 | up -> medium-solution region larger | 2 to 40 |
| `b_age_new_threshold` | 10 | up -> new-machine state extended | 1 to 100 |
| `b_age_medium_threshold` | 50 | up -> medium-machine state extended | 2 to 200 |

### 9.4 C packer objective keys

| Key | Default | Effect direction | Safe range |
|---|---:|---|---|
| `alpha_quality` | 1.0 | up -> quality dominates score | 0.1 to 5.0 |
| `beta_compat` | 0.5 | up -> compatibility dominates | 0.0 to 5.0 |
| `gamma_margin` | 0.3 | up -> economic margin dominates | 0.0 to 5.0 |
| `delta_time` | 0.2 | up -> lateness penalty stronger | 0.0 to 5.0 |
| `K_candidates` | 15 | up -> broader search, slower runtime | 5 to 100 |
| `random_seed` | `None` | set -> reproducible random packing | integer |

### 9.5 Reset and scenario controls

| API input | Default | Behavior |
|---|---|---|
| `reset(seed_initial_tasks=True, initial_tasks=None)` | default seeding enabled | auto-generate initial arrivals |
| `seed_initial_tasks=False` | off | starts empty unless `initial_tasks` provided |
| `initial_tasks=[...]` | none | exact controlled injection for scenario isolation |

### 9.6 Contract constraints summary
- State contract: read-only snapshot for decision.
- Action contract: V1 schema and process-keyed payload.
- Event contract: immutable trace used by validation and gantt.

### 9.7 Optional future LLM keys (example only, not implemented contract)
These keys are optional future examples for experiments and are not required by current runtime:
- `llm_supervisor_enabled`
- `llm_timeout_ms`
- `llm_validator_profile`
- `llm_fallback_policy`

## Chapter 10. Validation and Reproducible Experiment Protocol

### Purpose
Define a reproducible protocol for correctness and comparative method evaluation.

### What You Can Change
- Scenario definitions.
- Metric sets and reporting format.
- Baseline/proposed policy combinations.

### What Stays Invariant
- Validation commands must run on unchanged action/state contracts.
- Reported results must include config and seed context.
- Gantt and event consistency checks remain mandatory.

### 10.1 Core validation commands

```bash
conda run -n batch_env python -m tests.test_env_validation_matrix
conda run -n batch_env python -m tests.test_integration
conda run -n batch_env python -m tests.test_gantt_validation
conda run -n batch_env python -m tests.simple_debug_test
```

### 10.2 Recommended result artifacts
- `results/scenario1_gantt_direct.png`
- `results/scenario2_gantt_direct.png`
- `results/scenario3_gantt_direct.png`
- `results/scenario4_gantt_direct.png`

### 10.3 Documentation validation scenarios
Use these scenarios to validate the quality of this handbook itself:
1. A new researcher runs quick-start without asking for hidden assumptions.
2. An engineer adds one scheduler from the playbook only.
3. An engineer adds one tuner/APC method from the playbook only.
4. A team drafts Process D extension plan without unresolved design decisions.
5. A researcher reproduces baseline validation protocol and reports comparable metrics.
6. A researcher designs an LLM-supervisory tuner experiment with explicit safety guards and fallback.

### 10.4 Reporting template
For each experiment report include:
- Goal and hypothesis.
- Config snapshot.
- Seed policy.
- Baseline and proposed methods.
- KPI table (quality, throughput, waiting, compute cost).
- Failure analysis and rollback conditions.

## Chapter 11. Open Research Problems and Near-Term Roadmap

### Purpose
Connect current repository capabilities with realistic high-impact research directions for 2023 to 2026.

### What You Can Change
- Research objectives and benchmark definitions.
- Method classes and ablation depth.
- Safety/constraint policies for advanced controllers.

### What Stays Invariant
- Research claims should map to concrete insertion points in this codebase.
- Safety and integrity constraints should not be relaxed to inflate results.
- References should remain curated and implementation-relevant.

### 11.1 Open problems mapped to this repository
- Robust multi-stage scheduling under coupled quality drift.
- Joint dispatch and control under non-stationary process conditions.
- Safety-bounded LLM supervision for industrial decision support.
- Cost-aware balancing of quality, delay, and compute/inference latency.
- Sim-to-real transfer of control and packing decisions.

### 11.2 Near-term practical roadmap for this toolkit
1. Introduce explicit policy-evaluation dashboards from event logs.
2. Add optional memory stores for tuner history and BO loops.
3. Add formal safety validator interfaces for candidate action gating.
4. Add example notebooks for scheduler and APC benchmarking.
5. Add optional LLM-supervisory wrapper examples with deterministic fallback.

### 11.3 Recent Research Map (2023 to 2026, curated)
Reference format is standardized as:
`Year | Venue | Title | Link | Core contribution | Code mapping`

Link verification note:
- Checked on February 20, 2026.
- All DOI links listed below resolved with HTTP 200 from `doi.org`.
- Some publisher landing pages can still return anti-bot responses to automated clients.

| Year | Venue | Title | Link | Core contribution | Code mapping |
|---:|---|---|---|---|---|
| 2023 | Journal of Manufacturing Systems | Quality-based scheduling for a flexible job shop | https://doi.org/10.1016/j.jmsy.2023.07.005 | Quality-aware dispatch objective for flexible shops | `src/schedulers/*` + meta scoring |
| 2023 | Robotics and Computer-Integrated Manufacturing | DRL and MAS for dynamic re-entrant hybrid flow shop scheduling | https://doi.org/10.1016/j.rcim.2023.102605 | Disturbance-aware stage scheduling in dynamic settings | `src/agents/default_meta_scheduler.py` |
| 2024 | Computers and Industrial Engineering | Re-entrant hybrid flow-shop scheduling with stockers using DRL | https://doi.org/10.1016/j.cie.2024.109995 | Buffer/stocker constraints for stage-coupled scheduling | meta + scheduler constraints |
| 2025 | Computers and Industrial Engineering | Multi-objective flexible flow-shop rescheduling with maintenance and setup | https://doi.org/10.1016/j.cie.2024.110813 | Rescheduling with maintenance/setup tradeoffs | scheduler objective extensions |
| 2025 | Computers and Operations Research | Formulations and algorithms for scheduling on parallel-batching machines | https://doi.org/10.1016/j.cor.2024.106859 | Strong batch-capacity modeling baseline | scheduler and process constraints |
| 2025 | Journal of Computational Design and Engineering | HRL-GAT for distributed two-stage hybrid flow-shop scheduling | https://doi.org/10.1093/jcde/qwaf114 | Hierarchical RL structure for multi-stage coordination | custom `BaseMetaScheduler` |
| 2024 | Chemical Engineering Research and Design | Integrating run-to-run and feedback control for batch process optimization | https://doi.org/10.1016/j.cherd.2024.01.030 | Practical run-to-run and feedback integration | `src/tuners/*` |
| 2024 | Computers and Chemical Engineering | Model-based safe reinforcement learning for nonlinear systems | https://doi.org/10.1016/j.compchemeng.2024.108601 | Safety-constrained learning formulation | tuner + safety validator |
| 2024 | Computers and Chemical Engineering | Augmenting/replacing conventional process control using reinforcement learning | https://doi.org/10.1016/j.compchemeng.2024.108826 | RL with fallback-aware control integration | tuner fallback design |
| 2025 | Computers and Chemical Engineering | Practical reinforcement learning control with input-output constraints | https://doi.org/10.1016/j.compchemeng.2025.109248 | Bounded-action control under hard constraints | tuner constraints and guards |
| 2025 | Computers and Chemical Engineering | Physics-guided transfer learning for Bayesian optimization in process engineering | https://doi.org/10.1016/j.compchemeng.2025.109331 | Sample-efficient BO with transferable structure | BO-style tuner with history |
| 2024 | Communications Engineering | Reinforcement learning control for waste biorefining under uncertainty | https://doi.org/10.1038/s44172-024-00183-7 | Uncertainty-aware industrial control evidence | tuner uncertainty modeling |
| 2025 | IJCAI Proceedings | A survey of optimization modeling meets LLMs | https://doi.org/10.24963/ijcai.2025/1192 | LLM integration patterns for optimization workflows | optional supervisory layer design |
| 2025 | Advanced Engineering Informatics | LLM-empowered dynamic scheduling for intelligent hybrid flow shops | https://doi.org/10.1016/j.aei.2025.104294 | LLM-assisted stage scheduling in dynamic production | custom meta scheduler + validator |
| 2025 | Journal of Intelligent Information Systems | Textual explanations for scheduling systems with large language models | https://doi.org/10.1007/s10844-025-00940-w | Explainability and operator-facing rationale generation | post-decision explanation module |
| 2025 | IFAC-PapersOnLine | Autonomous industrial control using an agentic framework with LLMs | https://doi.org/10.1016/j.ifacol.2025.07.170 | Agentic supervisory control with validation loops | optional supervisory tuner wrapper |
| 2024 | IEEE Robotics and Automation Letters | GOPT: Transformer-based online 3D bin packing | https://doi.org/10.1109/LRA.2024.3468161 | Learning-based online packing for dynamic arrival | `src/schedulers/packers_c.py` extension |
| 2024 | Scientific Reports | GAN-based genetic algorithm for 3D bin packing optimization | https://doi.org/10.1038/s41598-024-56699-7 | Hybrid search for combinatorial packing quality | custom packer with learned proposals |

## Appendix A. Glossary
- Decision state: read-only snapshot consumed by policies.
- Handoff: same-step transfer of passed tasks between processes.
- Rework: failed task routed back for reprocessing.
- Scheduler: assignment policy selecting task batches.
- Tuner: recipe/control policy producing process parameters.
- Packer: final-stage grouping policy for C.
- Meta scheduler: orchestrator that composes scheduler, tuner, and packer outputs.

## Appendix B. Terminology Map

| Concept | In this repo |
|---|---|
| Stage | Process A, B, C |
| Dispatching | Scheduler `select_batch(...)` |
| Process control / APC | Tuner `get_recipe(...)` |
| Orchestration | Meta scheduler `decide(...)` |
| Plant transition | `ManufacturingEnv.step(...)` |
| Runtime observability | event logs + `get_decision_state()` |

## Appendix C. Quick-Start Checklists

### C.1 Add one scheduler in one session
1. Implement class in `src/schedulers/*`.
2. Wire to `src/agents/factory.py`.
3. Run validation matrix.
4. Compare against baseline with same seeds.

### C.2 Add one APC/tuner method safely
1. Start from deterministic fallback tuner.
2. Add new method with bounded outputs.
3. Add validator checks for recipe ranges.
4. Run integration + gantt validation.
5. Report pass/rework and latency.

### C.3 Add LLM-supervisory tuning safely
1. Keep deterministic tuner as primary fallback.
2. Build structured context from decision state.
3. Validate every LLM proposal before action emission.
4. Log validation failures and fallback events.
5. Stop experiment if violation rate exceeds baseline tolerance.

---

This handbook is intended to function as a reusable and extensible research reference for manufacturing simulation and control, with practical pathways for algorithmic experimentation and safe deployment-oriented methodology.
