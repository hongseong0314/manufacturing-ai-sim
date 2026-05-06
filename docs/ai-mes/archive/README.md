# Legacy Document Map

Status: reference only  
Last updated: 2026-05-06

This folder records which older documents fed the canonical AI MES docs.

The canonical docs now live in `docs/ai-mes/`. Do not use the old files as the
source of truth unless their content has been copied or summarized into the
canonical folder.

## Legacy Sources

| Legacy path | Current role |
|---|---|
| `sandox/semiconductor_ai_mes_final_design.md` | Historical full MES design draft. Superseded by `01` through `07` in this folder. |
| `sandox/mes_frontend_ux_plan.md` | Historical frontend UX plan. Superseded by `06_UI_CONTROL_ROOM_SPEC.md`. |
| `DESIGN.md` | Root design rules. Still useful for UI styling, summarized into `06_UI_CONTROL_ROOM_SPEC.md`. |
| `plan.md` | Handoff checklist. Still useful for work tracking, but not canonical architecture. |
| `README.md` | Simulator toolkit overview. Still useful for general project onboarding. |
| `sandox/mes_control_room_scrappy.html` | Static UI prototype. Reference artifact only. |
| `sandox/preview.html` | Static preview artifact only. |

## Supersession Notes

Important changes from the older design:

- The 4-layer AI architecture is now explicitly two-pass:
  lower-layer candidate intelligence flows upward, then selected intent flows
  back downward.
- C packing is the canonical example for candidate portfolio selection.
- `DefaultMetaScheduler` is treated as the current legacy simulator
  orchestrator, not the final MES L3 implementation.
- L1 owns candidate feasibility and final local allocation.
- L2 owns process annotation and final recipe/APC/process fields.
- L3/L4 select from lower-layer portfolios instead of inventing task lists.
- Rule Engine must eventually validate upper/lower layer consistency, not only
  L1/L2 executability.

