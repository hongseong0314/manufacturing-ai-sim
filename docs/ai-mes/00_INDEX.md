# AI MES Canonical Documentation

Status: canonical working specification
Last updated: 2026-05-10
Scope: simulator-backed semiconductor AI MES, AI decision architecture, MES
runtime, APIs, and UI control room.

This folder is the source of truth for the AI MES direction. Older planning
documents and prototypes remain useful as history, but implementation decisions
should start here.

## Document Map

| Order | Document | Purpose |
|---:|---|---|
| 1 | [01_SYSTEM_VISION.md](01_SYSTEM_VISION.md) | Product goal, boundaries, non-goals, and current code mapping |
| 2 | [02_LAYERED_AI_DECISION_ARCHITECTURE.md](02_LAYERED_AI_DECISION_ARCHITECTURE.md) | Final 4-layer AI decision model and candidate/selection flow |
| 3 | [03_MES_DOMAIN_MODEL.md](03_MES_DOMAIN_MODEL.md) | MES domain entities, simulator mapping, and persistence model |
| 4 | [04_RUNTIME_HARNESS_RULE_ENGINE.md](04_RUNTIME_HARNESS_RULE_ENGINE.md) | Harness, rule engine, command, event, and simulator execution runtime |
| 5 | [05_API_CONTRACTS.md](05_API_CONTRACTS.md) | Current and target FastAPI API contracts |
| 6 | [06_UI_CONTROL_ROOM_SPEC.md](06_UI_CONTROL_ROOM_SPEC.md) | Operational UI spec, visual rules, views, and data bindings |
| 7 | [07_IMPLEMENTATION_ROADMAP.md](07_IMPLEMENTATION_ROADMAP.md) | Build phases, acceptance criteria, tests, and migration strategy |
| 8 | [archive/README.md](archive/README.md) | Legacy document map and supersession notes |

## Decision Summary

The final AI MES architecture is not a simple top-down chain. It is a two-pass
decision system:

```text
Candidate intelligence flows upward:
L1 local candidates -> L2 process annotations -> L3 flow selection -> L4 objective

Execution intent flows downward:
L4 objective -> L3 selected group/stage -> L1 final allocation -> L2 final APC
  -> Rule Engine -> MES Command -> Simulator action
```

For C packing, this means the local packer must not immediately choose the final
global action. It should first generate a portfolio of feasible pack candidates
grouped by customer, product, material, due-date risk, or another business key.
L3/L4 then select which customer/product group should be favored under global
WIP, rework, due-date, throughput, yield, and business objectives. L1 finally
chooses the concrete product combination inside that selected group.

The practical target is:

```text
pi(a | s)
= pi_L3_L4(a_customer_product | s, L1_candidate_portfolio)
  * pi_L1(a_product_combo | s, a_customer_product)
```

L2 attaches process feasibility, recipe/APC, replacement, quality prediction,
and maintenance context to the candidates and final command.

## Source Of Truth Rules

- Keep simulator physics in `src/environment/*`.
- Keep per-process local policies in `src/schedulers/*` and `src/tuners/*`.
- Treat `src/agents/factory.py` as the policy-stack source of truth. It builds
  the swappable L1/L2/L3/L4 stack from config.
- Treat `src/agents/default_meta_scheduler.py` as a legacy simulator
  orchestrator and regression comparator, not the active MES L3 path.
- Treat `src/mes/harness.py` as a compatibility facade. The actual planner,
  generator, evaluator, and DTO artifacts live under `src/mes/harnessing/`.
- Treat `src/mes/rule_engine.py` as the execution gate. AI recommendations do
  not directly mutate simulator or MES state.
- Treat `src/mes/api.py` as route wiring only. Runtime state, simulation
  control, traceability, equipment detail, and Gantt payload builders live under
  `src/mes/runtime/`.
- Treat `src/mes/ui/templates/control_room.html` and `src/mes/ui/static/*` as
  the control-room implementation. `src/mes/live_ui.py` is a compatibility
  import only.

## Current Implementation Snapshot

Implemented today:

- Simulator kernel: `ManufacturingEnv`, `ProcessA_Env`, `ProcessB_Env`,
  `ProcessC_Env`.
- Local policies: A/B schedulers, A/B tuners, C packers.
- Legacy orchestrator: `DefaultMetaScheduler.decide(state)` returns V1
  `env.step(actions)` payloads.
- MES shell DTOs: Product, Lot, Wafer, Equipment, Recipe, FeatureSnapshot,
  AIRecommendation, Event, Genealogy, RuleValidationResult, MESCommand.
- Rule engine: validates L1 dispatch/pack plus L2 recipe and creates a command.
- Harness: creates a two-pass `L1 portfolio -> L2 annotations -> L4 -> L3
  -> L1 -> L2` recommendation chain through `src/mes/harnessing/`.
- MES policy stack: factory-built L1/L2/L3/L4 policy slots with current
  defaults `L1_FIFO_BASELINE`, `L2_RULE_BASED_APC`,
  `L3_CANDIDATE_PORTFOLIO_RULE`, and `L4_CYCLE_WEIGHT_RULE`.
- Runtime: `src/mes/runtime/context.py`, `simulation_control.py`,
  `live_state.py`, `decision_trace.py`, `equipment_detail.py`, and `gantt.py`
  own API payload generation and simulator lifecycle.
- Decision service: `src/mes/services.py` is a facade over
  `src/mes/decision/candidates.py`, `annotations.py`, and
  `simulator_actions.py`.
- Store: in-memory plus SQLite JSON payload persistence for audit records and
  runtime entities.
- API/UI: live simulator-backed MES endpoints and a dense `/mes` control room.
- Control-room baseline: A has 5 tools with batch size 3 and process time 20;
  B has 3 tools with batch size 2 and process time 8; C has 3 tools with batch
  size 4 and process time 2.

Not yet implemented:

- Full candidate portfolio workbench APIs/views for all selected and unselected
  alternatives.
- Runtime experiment preset controls for balanced/A-bottleneck/B-bottleneck
  scenarios.
- Production reservation locks, operator approvals, auth/roles, or SECS/GEM.
- Normalized PostgreSQL schema and event replay as the primary state source.

## Editing Policy

When changing the AI MES architecture, update this folder first. The old
documents under `sandox/` should not be used as decision authority unless copied
or summarized into this folder.
