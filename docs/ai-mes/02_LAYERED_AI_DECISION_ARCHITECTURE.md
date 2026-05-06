# Layered AI Decision Architecture

Status: canonical  
Last updated: 2026-05-06

## Core Decision Model

The AI MES uses four decision layers, but the information flow is not only
top-down. Local layers first expose what is feasible. Upper layers then choose
which local opportunity best matches fab-wide goals.

```text
Candidate intelligence flows upward:
L1 local candidates -> L2 process annotations -> L3 flow selection -> L4 objective

Execution intent flows downward:
L4 objective -> L3 selected group/stage -> L1 final allocation -> L2 final APC
  -> Rule Engine -> Command
```

This is the central design. Any implementation that makes L3 or L4 directly
choose task lists without L1 candidate support is crossing layer boundaries.

## Layer Responsibilities

| Layer | Name | Question | Output |
|---|---|---|---|
| L1 | Local dispatch / packing | What feasible task/equipment or pack combinations exist locally? | Candidate portfolio and final allocation within a selected group |
| L2 | Process dynamics / APC | What recipe, quality, replacement, or maintenance implications attach to each candidate? | Candidate annotations and final process-control fields |
| L3 | Cross-stage meta scheduling | Which stage, customer group, product group, or WIP pressure should be favored now? | Selected group/stage intent, budgets, constraints, and reasons |
| L4 | System objective | Which business/fab objective weights matter now? | Objective id, objective weights, override policy, and governance |

## C Packing Canonical Example

For C packing, the final decision is:

```text
pi(a | s)
```

Where:

- `s` is the C wait pool plus relevant fab state,
- `a` is the selected product combination on a selected C machine.

The final policy decomposes into local combination quality and upper-layer
customer/product selection:

```text
pi(a | s)
= pi_L3_L4(a_customer_product | s, L1_candidate_portfolio)
  * pi_L1(a_product_combo | s, a_customer_product)
```

L1 answers: "If the upper layer chooses customer/product group Alpha, what is
the best concrete pack combination for Alpha?"

L3/L4 answer: "Should we choose Alpha, Beta, or another group under WIP, due
date, customer priority, rework pressure, throughput, yield, and business
objectives?"

### Example

```text
L1 candidate portfolio:
  Alpha group:
    candidate A1 local_score=100
    candidate A2 local_score=94

  Beta group:
    candidate B1 local_score=90
    candidate B2 local_score=88

Upper-layer context:
  Alpha due date risk: high
  Beta local score: lower
  C queue age: increasing
  fab objective: due-date recovery

L3/L4 selection:
  select Alpha despite needing to preserve global due-date recovery.

L1 finalization:
  choose Alpha candidate A1.
```

The key is that L1 exposes Alpha and Beta local frontiers. L3/L4 do not invent
the product combination themselves.

## Candidate Portfolio Contract

Every L1 candidate should be a structured action candidate, not just a task list.

```python
{
    "candidate_id": "CAND_C_ALPHA_001",
    "stage": "C",
    "candidate_type": "PACK",
    "group_key": {
        "customer_id": "ALPHA",
        "product_id": "P1",
        "material_type": "plastic"
    },
    "equipment_id": "C_0",
    "task_uids": [101, 104, 109, 112],
    "local_score": 100.0,
    "local_rank": 1,
    "features": {
        "avg_quality": 72.1,
        "compatibility": 0.98,
        "avg_wait_time": 18,
        "min_due_date": 132,
        "margin_value": 0.82
    },
    "reasons": [
        "same_customer",
        "high_compatibility",
        "batch_ready"
    ]
}
```

For A/B, the same shape applies with `candidate_type="DISPATCH"` and fields such
as `operation_id`, `task_type`, and `batch_size`.

## L2 Annotation Contract

L2 attaches process-control information to each candidate or to the selected
candidate.

For A:

```python
{
    "candidate_id": "CAND_A_001",
    "recipe_id": "SIM_A_MEDIUM_APC",
    "recipe": [12.0, 2.5, 1.2],
    "parameters": {"temp": 12.0, "flow": 2.5, "duration": 1.2},
    "replace_consumable": False,
    "predicted_qa": 49.8,
    "target_spec": {"low": 47.1, "high": 52.9},
    "apc_policy": "A_SPEC_WINDOW_GRID_SEARCH"
}
```

For B:

```python
{
    "candidate_id": "CAND_B_001",
    "recipe_id": "SIM_B_DEFAULT",
    "recipe": [50.0, 50.0, 30.0],
    "replace_solution": False,
    "predicted_risk": "LOW"
}
```

For C:

```python
{
    "candidate_id": "CAND_C_ALPHA_001",
    "pack_quality_prediction": 72.1,
    "compatibility": 0.98,
    "pack_mode": "STANDARD",
    "quality_risk": "LOW"
}
```

C does not currently have a physical recipe/APC model, but it still needs L2
process annotations for quality, compatibility, packing mode, and future package
recipe constraints.

## L3 Selection Contract

L3 consumes the annotated candidate portfolio and chooses the stage/group focus.

```python
{
    "selected_stage": "C",
    "selected_group_key": {
        "customer_id": "ALPHA",
        "product_id": "P1"
    },
    "stage_priorities": {"A": 0.2, "B": 0.6, "C": 1.0},
    "dispatch_budgets": {"A": 0, "B": 1, "C": 1},
    "constraints": {
        "allow_rework": True,
        "prefer_due_date_recovery": True,
        "max_c_packs": 1
    },
    "score_components": {
        "local_candidate_score": 100.0,
        "due_date_pressure": 24.0,
        "wip_pressure": 11.0,
        "rework_pressure": 0.0
    },
    "reasons": ["due_date_recovery", "c_queue_ready"]
}
```

L3 should not finalize `task_uids` unless the selected candidate has already
been created by L1. It selects from the L1/L2 portfolio.

## L4 Objective Contract

L4 defines the system objective weights and governance mode.

```python
{
    "objective_id": "OBJ_DUE_DATE_RECOVERY",
    "weights": {
        "throughput": 0.8,
        "yield": 1.0,
        "tardiness": 1.4,
        "cost": 0.2,
        "customer_priority": 1.2
    },
    "governance": {
        "requires_rule_validation": True,
        "allow_operator_override": True,
        "max_command_count_per_cycle": 3
    },
    "reasons": ["commit_risk_high", "queue_pressure_normal"]
}
```

L4 should be stable across a planning interval. It does not need to change every
simulator tick unless the system objective changes.

## Recommendation Chain

The audit chain remains:

```text
L4 OBJECTIVE
  -> L3 STAGE_PRIORITY / GROUP_SELECTION
  -> L1 DISPATCH or PACK
  -> L2 RECIPE / APC / PROCESS_ANNOTATION
  -> RULE_VALIDATION
  -> COMMAND
```

The difference from the current implementation is that `candidate_actions` must
carry real portfolios, and upper layers must select from those portfolios.

## Current Implementation Gap

Current `MESPlannerAgent` creates L4 and L3 before L1 candidates exist. Current
`MESGeneratorAgent` creates one L1 candidate and one L2 recommendation after
that. This is acceptable as a rule-only baseline, but it cannot express the
desired factorization.

Target change:

```text
Current:
  L4/L3 choose stage -> L1 chooses first candidate -> L2 recipe -> validation

Target:
  L1 portfolio -> L2 annotations -> L3/L4 choose group/stage/objective
    -> L1 finalizes candidate -> L2 finalizes process fields -> validation
```

## Layer Boundary Rules

- L1 owns concrete task/equipment or pack-combination feasibility.
- L2 owns recipe/APC/process-control fields and predicted quality risk.
- L3 owns cross-stage, customer/product group, WIP, rework, and due-date tradeoff.
- L4 owns objective weights and governance.
- Rule Engine owns final executability.
- Environment owns physics and state transitions.

