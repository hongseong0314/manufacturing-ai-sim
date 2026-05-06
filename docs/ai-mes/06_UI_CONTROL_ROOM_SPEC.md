# UI Control Room Specification

Status: canonical  
Last updated: 2026-05-06

## Purpose

The UI is an operational MES control room for a simulator-backed semiconductor
AI MES. It must help dispatchers, engineers, and AI developers understand:

- current WIP,
- equipment state,
- candidate portfolios,
- layered recommendations,
- Rule Engine validation,
- command execution,
- events and genealogy.

The UI must never imply that AI directly executes equipment commands.

## Visual Source Of Truth

The visual rules in root `DESIGN.md` are now summarized here. Future UI work
should prefer this document and update root `DESIGN.md` only when project-wide
frontend rules change.

Style:

- bright neutral operations UI,
- dense table-first layout,
- status color for meaning,
- purple only for AI/model states,
- blue for primary command/action,
- green/yellow/orange/red for operational status,
- 6px panel radius,
- no marketing hero,
- no decorative gradient blobs,
- no cards inside cards.

Typography:

- system UI / Inter-style font stack,
- compact text,
- tabular numbers for KPIs,
- no viewport-scaled typography.

## Primary Views

### Fab Control Room

First viewport. Shows actual runtime state.

Must include:

- simulator time,
- active correlation id,
- autoplay state,
- KPI strip,
- A/B/C stage board,
- equipment state summary,
- active decision chain,
- Rule Engine gate,
- command preview or last command,
- recent event timeline.

### Stage Dispatch Board

For each stage, shows candidate-level decision data.

For target architecture, this view must show:

- L1 candidate portfolio,
- grouping key such as customer/product/material,
- local score,
- L2 annotation,
- L3/L4 selected group,
- final selected candidate,
- rule precheck.

For C packing, the table should make the decomposition visible:

```text
Group candidates:
  Alpha -> A1, A2
  Beta -> B1, B2

Upper selection:
  L3/L4 selected Alpha

Final pack:
  C_0 receives A1 task_uids
```

### Decision Chain Inspector

Shows the auditable chain:

```text
L4 Objective
  -> L3 Stage/Group Selection
  -> L1 Dispatch/Packing
  -> L2 Recipe/APC
  -> Rule Validation
  -> Command
  -> Events
```

Each block shows:

- layer id,
- recommendation type,
- recommendation id,
- parent recommendation id,
- feature snapshot id,
- score/confidence,
- selected action,
- validation status,
- reasons.

### Lot/Wafer Trace

Shows production object history.

Must include:

- lot id,
- wafer ids,
- current operation,
- equipment assignment,
- QA results,
- rework count,
- command id,
- correlation id,
- event history.

### Equipment And Recipe Monitor

Shows whether the selected command can actually run.

Must include:

- equipment status,
- current batch,
- finish time,
- health state,
- current recipe,
- recipe approval/download/compare status,
- replacement or maintenance recommendation.

For A/B, include machine-level quality trend and recipe/material state.
For C, target detail includes batch composition, pack quality, queue age,
compatibility, and pack id.

### Evaluator Console

Development-only but important.

Must include:

- required layers present,
- correlation id consistency,
- parent chain integrity,
- feature snapshot presence,
- candidate portfolio presence,
- L3 selection matches L1 candidate,
- L2 annotation matches L1 candidate,
- rule validation result,
- simulator action matched command,
- command execution event presence.

## Layout

Desktop:

```text
Sidebar / top shell
KPI strip
Main grid:
  Stage board
  Decision chain
  Rule gate
  Dispatch/candidate table
Secondary grid:
  Equipment matrix
  Event timeline
  Evaluator checklist
```

Mobile:

- horizontal nav,
- stacked panels,
- horizontally scrollable tables,
- vertical decision chain.

## Current UI

Current implementation:

- `/mes` route serves `LIVE_MES_HTML` from `src/mes/live_ui.py`.
- UI polls live endpoints.
- It already shows WIP, equipment, decision chain, events, Gantt, autoplay, and
  A/B machine quality detail.

Current limitations:

- It does not yet show bottom-up candidate portfolios.
- It does not yet distinguish L3/L4 group selection from L1 final pack choice.
- C machine detail is not implemented.
- Genealogy view is not implemented.
- Operator approval workflows are not implemented.

## Required UI Evolution

Next UI milestone:

1. Add Candidate Portfolio panel for C packing.
2. Show group-level rows: customer/product/material/due-date group.
3. Show local candidate score vs upper-layer weighted score.
4. Show selected group separately from selected pack.
5. Add Rule Engine consistency checks for selected group/candidate.
6. Add C machine detail: pack composition, compatibility, queue age, pack id.

## UX Copy Rules

Use precise operational language:

- "AI recommendation"
- "Rule validation"
- "Validated command"
- "Candidate portfolio"
- "Selected group"
- "Final allocation"
- "Execution event"

Avoid vague phrases:

- "AI decided"
- "automatic control"
- "smart optimization" without showing score/reasons
- "best" without showing objective and constraints

## Screen Data Bindings

| UI area | Current API | Target API |
|---|---|---|
| KPI strip | `/api/v1/kpis/fab` | same plus AI KPI |
| Stage board | `/api/v1/wip`, `/api/v1/equipment` | same |
| Candidate table | `/api/v1/dispatch/candidates` | `/api/v1/ai/candidates` |
| Decision chain | `/api/v2/decision-chain/{correlation_id}` | same with portfolio metadata |
| Rule gate | `/api/v1/rules/validate` | same plus layer consistency reasons |
| Command preview | `/api/v1/commands/track-in/preview` | `/api/v1/commands/finalize` |
| Event timeline | `/api/v1/events` | same plus simulator event linkage |
| Gantt | `/api/v2/gantt` | same |
| Machine detail | `/api/v2/equipment/{id}/detail` | A/B/C detail coverage |

