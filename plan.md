# MES Handoff Plan

## Current Goal

Build a simulator-backed semiconductor AI MES from the existing A -> B -> C
manufacturing simulation. The MES should show live WIP, equipment state,
AI recommendation traceability, rule validation, command execution, Gantt
scheduling, and machine-level APC quality behavior.

## Completed

- [x] Wrote the AI MES design direction around the 4-layer decision chain:
  `L4 Objective -> L3 Stage Priority -> L1 Dispatch/Packing -> L2 Recipe/APC
  -> Rule Engine -> Command`.
- [x] Added simulator-to-MES mapping:
  `Task -> Wafer`, `job_id -> Lot`, `Machine -> Equipment`,
  `get_decision_state() -> Decision Snapshot`.
- [x] Built the MES harness structure for planner -> generator -> evaluator.
- [x] Added Rule Engine validation before command execution.
- [x] Added recommendation, validation, command, and event persistence through
  the MES store / SQLite store path.
- [x] Added FastAPI read/control endpoints for health, WIP, equipment, KPIs,
  events, recommendations, decision chain, harness cycle execution, autoplay,
  and Gantt data.
- [x] Added a live `/mes` control room UI following `DESIGN.md`.
- [x] Added automatic task generation and autoplay stepping so WIP flows through
  A -> B -> C over time.
- [x] Updated MES default batch baseline to `A=5 tools x batch 3 x 20`,
  `B=3 tools x batch 2 x 8`, `C=3 tools x batch 4 x 2`.
- [x] Added a global and stage Gantt view with rolling time window, current-time
  marker, task ids, C batch packing visualization, and no C buffer pseudo-row.
- [x] Added machine detail dashboard for A/B equipment:
  - clickable equipment rows,
  - per-machine yield, average QA, latest QA, processed count, material state,
  - step-vs-quality trend chart,
  - point click/hover detail with task ids, recipe, target window, and
    consumable/solution state.
- [x] Extended A/B process event logs with QA values, recipe snapshot,
  pass/fail counts, and material state snapshots.
- [x] Added tests for live MES, Gantt behavior, autoplay flow, and A/B machine
  quality detail API.
- [x] Added Control Room Traceability V1:
  L3 budget plan, selected candidate portfolio, L2 annotations, final command,
  and Gantt-to-machine-detail drilldown.
- [x] Added factory-built swappable MES policy stack:
  current default is FIFO-style L1 schedulers/packer, rule-based L2 APC,
  `L3_CANDIDATE_PORTFOLIO_RULE`, and `L4_CYCLE_WEIGHT_RULE`, with policy ids
  carried through recommendations and Control Room traceability.
- [x] Added Control Room reset action:
  `Reset -> POST /api/v2/simulation/reset -> refresh`.

## Verified

- [x] `.venv/bin/python -m pytest` passes.
- [x] Browser verified:
  - A/B equipment row opens `#machine`.
  - A/B quality trend points render.
  - clicking a quality point updates the detail panel.
  - browser console has no errors.

## Next Checklist

- [x] Implement MES Policy Stack V2:
  - [x] Add swappable L3/L4 policy interfaces.
  - [x] Move current `MESPlannerAgent` L3/L4 rule logic into default policy
        classes.
  - [x] Build L1/L2/L3/L4 policies through `src/agents/factory.py`.
  - [x] Keep the harness as a policy orchestrator.
  - [x] Add regression and fake L3 policy injection tests.
  - [x] Expose L3/L4 policy ids in API/UI traceability.
- [x] Add persistent database-backed runtime state beyond audit records:
  lots, wafers, equipment, recipes, events, recommendations, commands.
- [x] Consolidate canonical AI MES, MES runtime, API, and UI documentation under
  `docs/ai-mes/`.
- [x] Replace the current linear harness decision flow with the documented
  candidate-portfolio flow:
  - [x] Generate L1 candidate portfolios before L3 selection.
  - [x] Add C packing candidates grouped by customer/product/material.
  - [x] Let L3 select `selected_candidate_id` and `selected_group_key` from the
        portfolio using L4 objective weights.
  - [x] Make L1 finalize the selected concrete dispatch/pack candidate.
  - [x] Make L2 annotate/finalize the selected L1 candidate with
        `candidate_id`.
  - [x] Extend Rule Engine and evaluator checks for L3/L1/L2 candidate
        consistency.
  - [x] Add full L2 annotations for every candidate before L3 selection, not
        only for the selected L1 candidate.
  - [x] Teach L3 to allocate multi-stage budgets from a single portfolio pass
        instead of selecting only one command per harness cycle.
- [ ] Split the large static `live_ui.py` into maintainable frontend assets or
  templates before the UI grows further.
- [ ] Add recipe/APC recommendation endpoints:
  `GET/POST /api/v1/recipes`, `/api/v1/ai/recommendations/recipe`,
  `/api/v1/commands/recipe-adjust`.
- [ ] Add explicit FeatureSnapshot schema persistence for every decision cycle.
- [ ] Add genealogy views:
  lot -> wafer -> operation -> equipment -> recipe -> QA result -> command.
- [x] Add machine detail for C equipment:
  batch composition, packing quality, queue age, compatibility, pack id.
- [ ] Add machine-level material/consumable models:
  A consumable life, B solution life, warning thresholds, replacement commands.
- [x] Add drilldown from Gantt bar to the same machine/task detail context.
- [x] Add evaluator checks for UI/API connectivity:
  live state, Gantt state, equipment detail, event chain, command audit.
- [ ] Move simulation runtime control to a service layer that can later be
  replaced by production MES/SECS-GEM integration.
- [ ] Define production integration boundaries:
  route master, equipment master, recipe master, dispatch command adapter,
  equipment event ingestion, and hold/release workflow.
- [ ] Add operator workflows:
  manual hold, release, recipe approval, command replay, event export.
- [ ] Add authentication/roles before any production-style command mutation.

## Important Files

- `docs/ai-mes/00_INDEX.md`: canonical AI MES documentation entry point.
- `docs/ai-mes/02_LAYERED_AI_DECISION_ARCHITECTURE.md`: final layered AI
  decision architecture.
- `docs/ai-mes/04_RUNTIME_HARNESS_RULE_ENGINE.md`: target harness, Rule Engine,
  validation, and command chain.
- `docs/ai-mes/06_UI_CONTROL_ROOM_SPEC.md`: canonical MES control room UI spec.
- `DESIGN.md`: root frontend visual rules, summarized in `docs/ai-mes/`.
- `sandox/`: legacy drafts and static prototypes.
- `src/mes/api.py`: FastAPI MES API and live runtime endpoints.
- `src/mes/live_ui.py`: current live MES control room HTML/CSS/JS.
- `src/mes/harness.py`: planner/generator/evaluator harness flow.
- `src/mes/services.py`: MES service mapping and command behavior.
- `src/mes/rule_engine.py`: Rule Engine validation before command creation.
- `src/environment/process_a_env.py`: A process QA/APC event source.
- `src/environment/process_b_env.py`: B process QA/APC event source.
- `src/environment/process_c_env.py`: C packing behavior.
- `tests/test_mes_api.py`: API contract tests.
- `tests/test_mes_autoplay.py`: live/autoplay/Gantt tests.

## Current Implementation State

The MES harness now follows the documented two-pass decision order:

```text
L1 local candidate portfolio
  -> L2 annotations for every candidate
  -> L4 objective weights
  -> L3 stage/group/candidate selection and dispatch budgets
  -> L1 selected concrete allocation
  -> L2 selected process fields
  -> Rule Engine
  -> Command
  -> Control Room traceability
```

Current Control Room Traceability V1 exposes:

- L3 budget plan and selected candidate ids.
- L3/L4 policy ids.
- selected candidate portfolio rows with group/customer/product context.
- L2 annotation count and selected candidate annotation.
- final L1/L2 actions and Rule Engine command.
- Gantt bar drilldown into the same machine detail API.

Current simulator-backed MES baseline:

```text
A: 5 equipment, batch_size=3, process_time=20
B: 3 equipment, batch_size=2, process_time=8
C: 3 equipment, batch_size=4, process_time=2, max_packs_per_step=3
```

## Next Implementation Gap

The next gap is to make experimentation and traceability deeper around the
implemented decision chain:

```text
Experiment presets/runtime config
  -> FeatureSnapshot schema persistence
  -> genealogy views
  -> recipe/APC adjustment commands
  -> operator approval/hold/release workflows
  -> production integration adapters
```

## Notes

- This is still a simulator-backed MES MVP, not a production MES.
- AI must recommend only. Rule Engine validation remains the boundary before
  any command execution.
- Current UI is intentionally dense and operational, not a marketing page.
- Generated result images under `results/` can change after tests/scripts.
