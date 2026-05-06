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

- [ ] Add persistent database-backed runtime state beyond audit records:
  lots, wafers, equipment, recipes, events, recommendations, commands.
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

- `sandox/semiconductor_ai_mes_final_design.md`: main design document.
- `DESIGN.md`: frontend UX rules.
- `src/mes/api.py`: FastAPI MES API and live runtime endpoints.
- `src/mes/live_ui.py`: current live MES control room HTML/CSS/JS.
- `src/mes/harness.py`: planner/generator/evaluator harness flow.
- `src/mes/services.py`: MES service mapping and command behavior.
- `src/environment/process_a_env.py`: A process QA/APC event source.
- `src/environment/process_b_env.py`: B process QA/APC event source.
- `src/environment/process_c_env.py`: C packing behavior.
- `tests/test_mes_api.py`: API contract tests.
- `tests/test_mes_autoplay.py`: live/autoplay/Gantt tests.

## Notes

- This is still a simulator-backed MES MVP, not a production MES.
- AI must recommend only. Rule Engine validation remains the boundary before
  any command execution.
- Current UI is intentionally dense and operational, not a marketing page.
- Generated result images under `results/` can change after tests/scripts.
