# DESIGN.md

Canonical UI source: `docs/ai-mes/06_UI_CONTROL_ROOM_SPEC.md`.
This file keeps root-level visual rules for quick reference.

## 1. Visual Theme & Atmosphere

This project is a simulator-backed semiconductor AI MES. The UI must feel like
an operations control system, not a marketing page.

Design goals:

- Dense but readable production information.
- Fast scanning for dispatchers, process engineers, and AI supervisors.
- Clear separation between AI recommendation, rule validation, and execution.
- Strong auditability through `correlation_id`, event status, and parent chain.
- Quiet enterprise surfaces with precise status color, not decorative gradients.

The first viewport should always show the actual working system:

- Fab and stage status.
- WIP and queue pressure.
- Current 4-layer decision chain.
- Rule Engine gate status.
- Dispatch candidates and validated command.

Do not make a landing page. Do not use large hero typography, decorative blobs,
or vague product copy.

## 2. Color Palette & Roles

Use neutral operational surfaces and reserve color for meaning.

| Token | Hex | Role |
|---|---:|---|
| `ink` | `#161616` | Primary text |
| `muted` | `#525252` | Secondary labels |
| `subtle` | `#6f6f6f` | Table metadata |
| `canvas` | `#f4f4f4` | App background |
| `surface` | `#ffffff` | Panels and tables |
| `surface-alt` | `#f9f9f9` | Table header and quiet bands |
| `border` | `#d0d0d0` | Panel and row dividers |
| `border-strong` | `#8d8d8d` | Active panel border |
| `blue` | `#0f62fe` | Primary action and active state |
| `cyan` | `#1192e8` | Information and simulator state |
| `green` | `#24a148` | Passed, available, healthy |
| `yellow` | `#f1c21b` | Warning and queue risk |
| `orange` | `#ff832b` | Setup, attention, drift |
| `red` | `#da1e28` | Rejected, down, violation |
| `purple` | `#8a3ffc` | AI recommendation and model state |

Rules:

- Keep backgrounds mostly `canvas`, `surface`, and `surface-alt`.
- Use blue only for selected navigation and primary command buttons.
- Use purple only for AI-specific states.
- Use green/yellow/orange/red only for operational status.
- Avoid monochrome dark dashboards unless the user explicitly asks for dark mode.

## 3. Typography Rules

Use system UI fonts for reliability:

```css
font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
  "Segoe UI", sans-serif;
```

Type scale:

| Role | Size | Weight | Usage |
|---|---:|---:|---|
| App title | 18px | 650 | Top-left product label |
| Page title | 22px | 650 | Current workspace title |
| Section title | 15px | 650 | Panel headings |
| Table header | 11px | 600 | Uppercase table labels |
| Body | 13px | 400 | Table cells and compact text |
| Metadata | 12px | 400 | Secondary values |
| KPI value | 26px | 650 | Main numeric values |

Rules:

- Letter spacing is `0`.
- Do not scale font size with viewport width.
- Use tabular numbers for KPI and equipment metrics.
- Prefer short labels over explanatory paragraphs inside the app.

## 4. Component Styling

### App Shell

- Left navigation: fixed width on desktop, horizontal stack on mobile.
- Top command bar: current simulation time, active correlation id, rule gate.
- Content area: CSS grid panels with predictable heights.

### Panels

- Border radius: 6px.
- Border: 1px solid `border`.
- Background: `surface`.
- No nested cards.
- Use panel headers with title on the left and compact state on the right.

### Tables

- Primary data should be shown in tables, not decorative cards.
- Sticky-looking header style: `surface-alt`, uppercase 11px labels.
- Row height: 44px minimum.
- Use status chips inside cells.

### Status Chips

- Height: 22px.
- Border radius: 999px.
- Uppercase labels.
- Use color meaning consistently:
  - Green: passed, idle, eligible.
  - Yellow: reserved, queue risk.
  - Orange: setup, drift, pending review.
  - Red: rejected, down, hold.
  - Purple: AI generated.

### Command Buttons

- Primary buttons: blue background, white text.
- Secondary buttons: surface background, border.
- Destructive buttons: red border/text unless confirmed.
- Buttons should be compact and action-specific: `Run cycle`, `Validate`,
  `Track in`, `Hold`, `Replay chain`.

### Decision Chain

The 4-layer chain must be visually persistent:

```text
L4 Objective -> L3 Stage Priority -> L1 Dispatch/Packing -> L2 Recipe/APC
```

Each layer block should show:

- Layer id.
- Recommendation type.
- Recommendation id.
- Parent recommendation id.
- Feature snapshot id.
- Score/confidence.
- Validation status.

Use arrows or connecting lines, but keep the layout compact.

## 5. Layout Principles

Desktop layout:

- 240px sidebar.
- 1fr content area.
- KPI strip at top.
- Main grid: stage board, decision chain, rule gate, dispatch table.
- Secondary grid: equipment matrix, event timeline, evaluator checklist.

Mobile layout:

- Collapse sidebar into a top nav band.
- Stack panels vertically.
- Keep tables horizontally scrollable.
- Decision chain becomes a vertical sequence.

Spacing:

- 8px base grid.
- 16px between panels.
- 12px inside dense table panels.
- 20px page padding.

## 6. Depth & Elevation

Use minimal shadows. MES users need clarity more than atmosphere.

- Normal panels: no shadow or very light shadow.
- Active panel: stronger border, not heavy shadow.
- Modal/drawer: `0 12px 32px rgba(0, 0, 0, 0.16)`.

## 7. Do's and Don'ts

Do:

- Start with the operational dashboard.
- Show real simulator/MES concepts: WIP, equipment, command, event, lot, wafer.
- Make `correlation_id` visible.
- Make AI recommendation and Rule Engine validation visually separate.
- Include evaluator connectivity status for development builds.

Don't:

- Do not create a marketing hero page.
- Do not hide the decision chain behind a vague AI score.
- Do not imply AI directly executes equipment commands.
- Do not use large glowing gradients, decorative orbs, or bokeh backgrounds.
- Do not make the palette only blue, purple, or dark slate.
- Do not put cards inside cards.

## 8. Responsive Behavior

Breakpoints:

- `1200px`: reduce main grid to two columns.
- `900px`: collapse shell to one column.
- `640px`: stack all panels; tables scroll horizontally.

Touch targets:

- Minimum 36px for buttons.
- Minimum 44px row height for selectable rows.

## 9. Agent Prompt Guide

For future UI work, use this prompt intent:

```text
Build a dense semiconductor MES operations screen. Use DESIGN.md as the visual
source of truth. The UI must show fab/stage status, WIP, equipment, AI
recommendation envelopes, Rule Engine validation, command execution, events, and
4-layer decision chain traceability. Do not make a landing page.
```

Primary screen names:

- Fab Control Room
- Stage Dispatch Board
- Decision Chain Inspector
- Lot/Wafer Trace
- Equipment and Recipe Monitor
- Event and Genealogy Audit
- Evaluator Console
