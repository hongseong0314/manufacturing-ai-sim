# System Vision

Status: canonical  
Last updated: 2026-05-10

## Goal

Build a simulator-backed semiconductor AI MES that turns the current A -> B -> C
manufacturing simulation into an auditable decision system:

```text
A: machining / process QA -> B: cleaning / process QA -> C: packing
```

The system must show and persist:

- live WIP and equipment state,
- AI recommendation traceability,
- rule validation,
- command execution,
- Gantt scheduling,
- machine-level APC and quality behavior,
- lot/wafer/equipment/recipe/event/genealogy context.

This is an MES control and research system, not a marketing demo. The primary
purpose is to study and operate layered AI decisions without mixing decision
logic into simulator physics.

## Product Principle

AI recommends. The Rule Engine validates. MES executes. The environment only
applies validated actions and physics.

```text
Decision state
  -> AI recommendation envelopes
  -> Rule Engine validation
  -> MES command
  -> simulator action
  -> event/audit/KPI update
```

No AI policy should directly call `env.step()` or mutate process state.

## System Boundaries

### Simulator Kernel

The simulator kernel owns physics and state transitions.

| Module | Responsibility |
|---|---|
| `src/environment/manufacturing_env.py` | Top-level A -> B -> C orchestration |
| `src/environment/process_a_env.py` | A process physics, QA, consumable behavior |
| `src/environment/process_b_env.py` | B process physics, QA, solution behavior |
| `src/environment/process_c_env.py` | C packing/finalization behavior |
| `src/objects.py` | Shared `Task` and `Machine` objects |

The key simulator contract is:

```python
state = env.get_decision_state()
observation, reward, done, info = env.step(actions)
```

### Policy Kernel

The current policy kernel owns local and legacy orchestration decisions.

| Module | Current role | Target MES role |
|---|---|---|
| `src/schedulers/schedulers_a.py` | A batch selection | L1 A dispatch candidate/finalizer |
| `src/schedulers/schedulers_b.py` | B batch selection | L1 B dispatch candidate/finalizer |
| `src/schedulers/packers_c.py` | C pack selection | L1 C pack candidate/finalizer |
| `src/tuners/tuners_a.py` | A recipe/replacement | L2 A recipe/APC annotator/finalizer |
| `src/tuners/tuners_b.py` | B recipe/replacement | L2 B recipe/APC annotator/finalizer |
| `src/agents/default_meta_scheduler.py` | V1 A/B/C action orchestrator | Legacy simulator baseline and source material for L3 |

The target MES should preserve these policies as lower-level policy components
instead of burying them inside a monolithic meta scheduler.

### MES Shell

The MES shell owns DTOs, persistence, recommendations, validation, commands, API,
and UI.

| Module | Responsibility |
|---|---|
| `src/mes/domain.py` | MES-facing dataclasses |
| `src/mes/adapters.py` | simulator <-> MES DTO/action mapping |
| `src/mes/services.py` | candidate and decision service helpers |
| `src/mes/rule_engine.py` | execution validation gate |
| `src/mes/harness.py` | development harness for layered decision chains |
| `src/mes/store.py` | in-memory repository and audit events |
| `src/mes/sqlite_store.py` | local SQLite persistence |
| `src/mes/api.py` | FastAPI endpoints and live runtime |
| `src/mes/live_ui.py` | current static control room UI |

## Non-Goals

The current MVP is not:

- a production MES,
- a replacement for a real route master, equipment master, or recipe master,
- a SECS/GEM or OPC-UA integration,
- a safety-certified equipment control layer,
- an autonomous fab controller,
- a multi-tenant enterprise application.

Those may become future integrations. The current system must first make the
decision chain correct, inspectable, and testable.

## Current State

The repository already has a working simulator and a simulator-backed MES shell.
The current MES path follows the two-pass layered decision flow:

```text
L1 candidate portfolio
  -> L2 candidate annotations
  -> L4 objective policy
  -> L3 meta scheduler policy
  -> L1 final dispatch/pack recommendation
  -> L2 final recipe/APC recommendation
  -> Rule Engine
  -> Command
```

`MESPlannerAgent` is now an orchestrator around factory-built policy slots. The
default L1 policies are FIFO-style schedulers/packer, L2 is rule-based APC,
L3 is `L3_CANDIDATE_PORTFOLIO_RULE`, and L4 is `L4_CYCLE_WEIGHT_RULE`.

The current control-room simulator baseline is:

```text
A: 5 equipment, batch_size=3, process_time=20
B: 3 equipment, batch_size=2, process_time=8
C: 3 equipment, batch_size=4, process_time=2, max_packs_per_step=3
```

## Target State

The final AI MES should operate as a two-pass system.

```text
Pass 1: Candidate intelligence
  L1 generates feasible local allocations and pack combinations.
  L2 annotates candidates with recipe/APC/quality/maintenance implications.
  L3 scores candidate families under cross-stage flow pressure.
  L4 applies fab/business objective weights.

Pass 2: Execution intent
  L4/L3 select the favored stage/group/customer/product family.
  L1 finalizes the concrete equipment and task/wafer combination.
  L2 finalizes recipe/APC/maintenance command fields.
  Rule Engine validates the complete chain.
  MES command executes through the simulator adapter.
```

This preserves local specialization while allowing global objectives to select
among local possibilities.
