# MES Product UI Foundation V1

Status: planned  
Branch: `codex/mes-product-ui-foundation-v1`  
Base: `mes` at `e59e610`

## Goal

Convert the current simulator-oriented MES UI into the product shell for a
commercial Semiconductor Digital Twin MES.

This is not a visual decoration pass. The goal is to establish durable
information architecture, reusable UI primitives, and page structures that can
later absorb production adapters, genealogy, operator approval, richer
equipment state, and digital twin views.

## Scope

V1 keeps the current FastAPI + static HTML/CSS/JS delivery model.

Included:

- Product navigation grouped by role.
- Clear separation between operations, traceability, AI development, and audit
  screens.
- Shared UI primitives for page shell, panel, table, toolbar, status chip,
  inspector, timeline, empty state, and raw payload containment.
- Priority layout improvements for:
  - `#machine`,
  - `#assignment-trace`,
  - `#ai-dev`.
- Dense-data rendering improvements for long ids, Gantt labels, decision-cycle
  rows, candidate rows, and raw JSON.
- UI contract tests that protect the new page structure.

Excluded:

- React, Next.js, or Tailwind migration.
- Direct `open-design` runtime dependency.
- 3D digital twin implementation.
- New AI policy behavior.
- Backend decision logic changes.
- Marketing or landing-page UI.

## Open Design Usage

`https://github.com/nexu-io/open-design` is used as a reference for design
system structure, token discipline, and enterprise product-console patterns.

The useful references are:

- `ibm`: structured blue/gray enterprise system.
- `enterprise`: data workflow hierarchy and high-contrast controls.
- `application`: general app shell and productivity UI structure.

The MES app should not copy any brand system verbatim. Open Design informs the
internal MES design system; it does not become the runtime framework.

## Target Information Architecture

| Group | Screens | Primary question |
|---|---|---|
| Operate | Fab Control, Flow & Gantt, Equipment, Machine Detail | Is the fab healthy, and what is running where? |
| Trace | Decision Chain, Assignment Trace, Candidate Portfolio | Why did this decision or assignment happen? |
| AI Development | AI Dev Console | Which policies, candidates, scores, and experiments explain behavior? |
| System / Audit | Events | What happened in the execution log? |

## UI Primitive Contract

The UI should expose these reusable primitives before individual screen styling
is expanded:

- `page-shell`: page-level surface and scope.
- `section-kicker`: short purpose text under section titles.
- `panel`: bounded information area.
- `table-scroll`: horizontal/vertical containment for dense tables.
- `truncate-id`: safe display for long correlation/candidate/command ids.
- `inspector-grid`: split-pane detail layout.
- `trace-layer-list`: ordered decision/action timeline.
- `status`: semantic state chip.
- `raw-json-collapsed`: contained raw payload inspector.

## Implementation Steps

1. Add UI contract tests in `tests/test_mes_product_ui_foundation.py`.
2. Refactor `src/mes/ui/templates/control_room.html` navigation and page shell
   semantics.
3. Add product UI tokens and primitives in
   `src/mes/ui/static/control_room.css`.
4. Improve dense id and raw payload rendering in
   `src/mes/ui/static/control_room.js`.
5. Update `docs/ai-mes/06_UI_CONTROL_ROOM_SPEC.md` to reference this product
   shell direction.
6. Verify with focused tests, full pytest, and browser smoke checks for
   `#machine`, `#assignment-trace`, and `#ai-dev`.

## Completion Criteria

- Operator information and AI developer information are visually separated.
- Each page clearly answers one primary question.
- Tables, panels, inspectors, and timelines follow one consistent visual
  grammar.
- Long ids and dense data do not break panel boundaries.
- `#machine`, `#assignment-trace`, and `#ai-dev` use product shell structure.
- Existing simulator, API, decision-chain, and trace behavior remain unchanged.
