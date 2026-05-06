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
- [x] Updated process timings to `A=20`, `B=5`, `C=2`.
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

## Verified

- [x] `.venv/bin/python -m pytest` passes.
- [x] Browser verified:
  - A/B equipment row opens `#machine`.
  - A/B quality trend points render.
  - clicking a quality point updates the detail panel.
  - browser console has no errors.

## Next Checklist

- [x] Add persistent database-backed runtime state beyond audit records:
  lots, wafers, equipment, recipes, events, recommendations, commands.
- [x] Consolidate canonical AI MES, MES runtime, API, and UI documentation under
  `docs/ai-mes/`.
- [ ] Replace the current linear harness decision flow with the documented
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
  - [ ] Teach L3 to allocate multi-stage budgets from a single portfolio pass
        instead of selecting only one command per harness cycle.
- [ ] Split the large static `live_ui.py` into maintainable frontend assets or
  templates before the UI grows further.
- [ ] Add recipe/APC recommendation endpoints:
  `GET/POST /api/v1/recipes`, `/api/v1/ai/recommendations/recipe`,
  `/api/v1/commands/recipe-adjust`.
- [ ] Add explicit FeatureSnapshot schema persistence for every decision cycle.
- [ ] Add genealogy views:
  lot -> wafer -> operation -> equipment -> recipe -> QA result -> command.
- [ ] Add machine detail for C equipment:
  batch composition, packing quality, queue age, compatibility, pack id.
- [ ] Add machine-level material/consumable models:
  A consumable life, B solution life, warning thresholds, replacement commands.
- [ ] Add drilldown from Gantt bar to the same machine/task detail context.
- [ ] Add evaluator checks for UI/API connectivity:
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

## Current Implementation Gap

The current MES harness is still linear:

```text
MESPlannerAgent creates L4 objective and L3 stage priority
  -> MESGeneratorAgent gets one stage's rule candidates
  -> generator selects the first L1 candidate
  -> generator creates one L2 recipe/APC recommendation
  -> Rule Engine validates L1/L2 and creates a command
```

The canonical architecture requires a different decision order:

```text
L1 local candidate portfolio
  -> L2 candidate annotations
  -> L4 objective
  -> L3 stage/group/candidate selection
  -> L1 selected concrete allocation
  -> L2 selected process fields
  -> Rule Engine
  -> Command
```

First implementation scope:

```text
C packing portfolio first, while keeping A/B behavior compatible.
```

This first slice should not rewrite the simulator kernel. It should keep the
existing recommendation envelope and command shape, but add the missing
portfolio fields:

- `candidate_id`
- `candidate_type`
- `group_key`
- `local_score`
- `local_rank`
- `features`
- `reasons`
- L3 `selected_candidate_id`
- L3 `selected_group_key`
- L2 `candidate_id`

## Notes

- This is still a simulator-backed MES MVP, not a production MES.
- AI must recommend only. Rule Engine validation remains the boundary before
  any command execution.
- Current UI is intentionally dense and operational, not a marketing page.
- Generated result images under `results/` can change after tests/scripts.
