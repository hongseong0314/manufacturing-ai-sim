# API Contracts

Status: canonical  
Last updated: 2026-05-10

## Purpose

This document defines the simulator-backed MES API surface and the target API
contracts needed for the layered AI architecture.

The current route implementation lives in `src/mes/api.py`. Route functions are
thin and delegate runtime behavior to `src/mes/runtime/*`.

| Runtime concern | Module |
|---|---|
| lifecycle/reset | `src/mes/runtime/context.py` |
| run-cycle/run-until/autoplay/generate lot | `src/mes/runtime/simulation_control.py` |
| live control-room state | `src/mes/runtime/live_state.py` |
| decision-chain traceability | `src/mes/runtime/decision_trace.py` |
| AI developer console payloads | `src/mes/runtime/ai_dev.py` |
| equipment detail | `src/mes/runtime/equipment_detail.py` |
| Gantt state | `src/mes/runtime/gantt.py` |

## Current Read APIs

| Endpoint | Purpose |
|---|---|
| `GET /health` | Service health |
| `GET /api/v1/decision-state` | Raw simulator decision state |
| `GET /api/v1/kpis/fab` | Fab KPI summary |
| `GET /api/v1/wip` | WIP by stage |
| `GET /api/v1/equipment` | Equipment list |
| `GET /api/v1/lots` | Lot list from store-backed runtime snapshot |
| `GET /api/v1/wafers` | Wafer list, optional `lot_id` filter |
| `GET /api/v1/recipes` | Recipe list, optional `operation_id` filter |
| `GET /api/v1/dispatch/candidates?stage=A` | L1 policy-stack dispatch candidates |
| `GET /api/v1/ai/recommendations` | Recommendation records, optional `correlation_id` |
| `GET /api/v1/events` | Event records, optional `correlation_id` |
| `GET /api/v1/commands` | Command records, optional `correlation_id` |
| `GET /api/v2/decision-chain/{correlation_id}` | Aggregated chain details |
| `GET /api/v2/candidate-portfolio/latest` | Latest actionable selected/rejected portfolio workbench payload |
| `GET /api/v2/candidate-portfolio/{correlation_id}` | Portfolio snapshot for one decision correlation |
| `GET /api/v2/ai-dev/policy-stack` | Active L1/L2/L3/L4 policy stack and config |
| `GET /api/v2/ai-dev/decision-cycles` | Correlation-level AI decision cycle browser |
| `GET /api/v2/ai-dev/candidate-portfolio/{correlation_id}` | Developer portfolio payload with score/L2 details |
| `GET /api/v2/equipment/{equipment_id}/detail` | A/B/C machine quality and packing detail data |
| `GET /api/v2/gantt` | Gantt rows, bars, stage views, and horizon |
| `GET /api/v2/fab/live` | Live control-room state |

## Current Mutation APIs

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/harness/run` | Preview one stage, or execute L3-budget AUTO |
| `POST /api/v1/rules/validate` | Validate recommendation payloads |
| `POST /api/v1/commands/track-in/preview` | Preview track-in command |
| `POST /api/v1/commands/track-in/execute` | Execute validated command |
| `POST /api/v2/tasks/generate` | Generate simulator tasks |
| `POST /api/v2/harness/run-cycle` | Run and execute one cycle |
| `POST /api/v2/harness/run-until` | Run cycles until stop condition |
| `POST /api/v2/simulation/reset` | Reset simulator runtime |
| `POST /api/v2/simulation/autoplay/start` | Enable autoplay |
| `POST /api/v2/simulation/autoplay/stop` | Disable autoplay |
| `GET /api/v2/simulation/autoplay/status` | Poll autoplay and optionally step |

## Current V2 Payload Summary

`POST /api/v2/harness/run-cycle` with `target_stage="AUTO"` returns an L3
budget-driven execution payload:

```python
{
    "mode": "AUTO",
    "selection_source": "l3_budget_plan",
    "budget_plan": {
        "selected_candidate_ids": ["CAND_..."],
        "dispatch_budgets": {"A": 5, "B": 0, "C": 0},
        "budget_candidate_ids": {"A": ["CAND_..."], "B": [], "C": []}
    },
    "combined_actions": {"A": {...}, "B": {}, "C": {}},
    "cycles": [...]
}
```

`GET /api/v2/decision-chain/{correlation_id}` returns the persisted audit chain
and a `traceability` block with L4/L3 policy ids, selected candidates, final
L1/L2 actions, validated command, and `portfolio_summary`.

`GET /api/v2/candidate-portfolio/latest` and
`GET /api/v2/candidate-portfolio/{correlation_id}` return the workbench-ready
portfolio snapshot. `latest` prefers the latest actionable portfolio over a
newer empty cycle, while still reporting the latest empty correlation and empty
diagnostics.

```python
{
    "correlation_id": "CORR_...",
    "feature_snapshot_id": "FS_...",
    "kind": "ACTIONABLE",
    "is_actionable": True,
    "empty_reason": None,
    "last_actionable_correlation_id": "CORR_...",
    "latest_empty_correlation_id": "CORR_...",
    "diagnostics": {
        "stages": {
            "A": {"queue_size": 12, "idle_machines": 2, "candidate_count": 5}
        }
    },
    "count": 12,
    "summary": {
        "selected_count": 1,
        "rejected_count": 11,
        "stage_counts": {"A": 5, "B": 3, "C": 4},
        "objective_id": "OBJ_DUE_DATE_RECOVERY",
        "l4_policy_id": "L4_CYCLE_WEIGHT_RULE",
        "l3_policy_id": "L3_CANDIDATE_PORTFOLIO_RULE"
    },
    "items": [
        {
            "candidate_id": "CAND_C_ALPHA_001",
            "stage": "C",
            "candidate_type": "PACK",
            "group_key": {"customer_id": "ALPHA"},
            "equipment_id": "C_0",
            "task_uids": [1, 2, 3, 4],
            "local_score": 90.0,
            "upper_score": 124.2,
            "score_components": {
                "local_candidate_score": 90.0,
                "due_date_pressure": 2.0,
                "wip_pressure": 4.0,
                "objective_weight_bonus": 34.2,
                "quality_risk_penalty": 0.0,
                "final_upper_score": 124.2
            },
            "l2_annotation": {"quality_risk": "LOW"},
            "selected": True,
            "budget_selected": True,
            "rejection_reason": None,
            "linked_recommendation_ids": {"L4": "REC_...", "L3": "REC_..."},
            "command_status": "EXECUTED"
        }
    ]
}
```

`GET /api/v2/ai-dev/policy-stack` returns the active factory-built stack:

```python
{
    "factory_name": "build_mes_policy_stack",
    "l1_policy_id": "L1_FIFO_BASELINE",
    "l2_policy_id": "L2_RULE_BASED_APC",
    "l3_policy_id": "L3_CANDIDATE_PORTFOLIO_RULE",
    "l4_policy_id": "L4_CYCLE_WEIGHT_RULE",
    "config": {"scheduler_A": "fifo", "tuner_A": "rule-based"},
    "layers": {
        "L3": {
            "policy_id": "L3_CANDIDATE_PORTFOLIO_RULE",
            "model_id": "candidate-portfolio-meta-scheduler",
            "model_version": "0.1.0"
        }
    }
}
```

`GET /api/v2/ai-dev/decision-cycles` returns recent correlation rows for the
developer cycle browser. `GET /api/v2/ai-dev/candidate-portfolio/{correlation_id}`
adds objective weights, L3 action, policy stack metadata, selected candidate,
score breakdown, and L2 annotations to the base portfolio payload.

`GET /api/v2/gantt` returns `flow`, `rows`, `bars`, `stage_views`, `horizon`,
and `legend`.

`GET /api/v2/equipment/{equipment_id}/detail` returns A/B APC quality trends or
C packing composition quality, including material/color counts for C.

## Future Standalone Layered AI APIs

The current API can run the baseline chain. The target architecture needs APIs
that expose candidate portfolios before final upper-layer selection.

### Candidate Portfolio

```http
GET /api/v1/ai/candidates?stage=C
```

Response:

```python
{
    "time": 42,
    "stage": "C",
    "count": 12,
    "group_keys": [
        {"customer_id": "ALPHA", "product_id": "P1"},
        {"customer_id": "BETA", "product_id": "P2"}
    ],
    "items": [
        {
            "candidate_id": "CAND_C_ALPHA_001",
            "candidate_type": "PACK",
            "stage": "C",
            "group_key": {"customer_id": "ALPHA"},
            "equipment_id": "C_0",
            "task_uids": [1, 2, 3, 4],
            "local_score": 100.0,
            "features": {"compatibility": 0.98}
        }
    ]
}
```

### Candidate Annotation

```http
POST /api/v1/ai/candidates/annotate
```

Request:

```python
{
    "correlation_id": "CORR_...",
    "candidates": [...]
}
```

Response:

```python
{
    "correlation_id": "CORR_...",
    "count": 12,
    "items": [
        {
            "candidate_id": "CAND_C_ALPHA_001",
            "l2": {
                "pack_quality_prediction": 72.1,
                "quality_risk": "LOW"
            }
        }
    ]
}
```

### Objective Recommendation

```http
POST /api/v1/ai/recommendations/objective
```

Creates or previews L4 objective weights.

### Meta Selection

```http
POST /api/v1/ai/recommendations/meta-selection
```

Consumes annotated candidate portfolios and returns L3/L4 group selection.

Request:

```python
{
    "correlation_id": "CORR_...",
    "objective": {...},
    "candidate_portfolio": [...]
}
```

Response:

```python
{
    "recommendation_id": "REC_L3_...",
    "layer_id": "L3",
    "recommended_action": {
        "selected_stage": "C",
        "selected_group_key": {"customer_id": "ALPHA"},
        "selected_candidate_id": "CAND_C_ALPHA_001"
    }
}
```

### Finalize Command

```http
POST /api/v1/commands/finalize
```

Consumes selected L4/L3/L1/L2 recommendations and returns validation/command
preview.

### Execute Command

```http
POST /api/v1/commands/{command_id}/execute
```

Executes only commands that are validated and executable.

## Response Envelope Rules

Every AI-facing response should include:

- `time`,
- `correlation_id` when part of a decision chain,
- `count` for collections,
- `items` for lists,
- stable ids for recommendations, snapshots, candidates, and commands,
- validation status when available.

## Error Rules

Recommended error categories:

| HTTP status | Use |
|---:|---|
| 400 | invalid target stage, malformed recommendation, impossible request |
| 404 | unknown lot, wafer, equipment, command, or correlation id |
| 409 | command no longer executable because state changed |
| 422 | syntactically valid but rule-invalid request |
| 500 | unexpected internal error |

Rule rejects should usually return `200` with `validation_status="REJECTED"`

## Current Control Room Runtime Baseline

The local `/mes` runtime currently starts with:

```text
A: 5 equipment, batch_size=3, process_time=20
B: 3 equipment, batch_size=2, process_time=8
C: 3 equipment, batch_size=4, process_time=2, max_packs_per_step=3
```

The UI exposes Start, Stop, Run cycle, Generate lot, and Reset. Reset calls
`POST /api/v2/simulation/reset` and refreshes live state.

Rule rejects should remain successful HTTP responses when the request shape is
valid but the recommendation is not executable.

## AI Developer Experiment APIs

Policy Experiment Runner V1 is intentionally a development API. It captures an
immutable scenario snapshot from the current simulator state, replays that
snapshot through multiple factory-built policy stacks, and returns comparison
payloads without mutating the live simulator.

### Capture Scenario

```http
POST /api/v2/ai-dev/scenarios/capture
```

Response shape:

```python
{
    "scenario_id": "SCN_...",
    "time": 37,
    "source_correlation_id": "CORR_...",
    "config": {"scheduler_A": "fifo", "tuner_A": "rule-based"},
    "decision_state": {"A": {}, "B": {}, "C": {}, "tasks": {}},
    "tasks": {},
    "A": {},
    "B": {},
    "C": {},
    "equipment": [],
    "kpis": {}
}
```

### List Scenarios

```http
GET /api/v2/ai-dev/scenarios
```

Returns summary rows with `scenario_id`, `time`, `task_count`, `queue_sizes`,
and `equipment_count`.

### List Policy Variants

```http
GET /api/v2/ai-dev/policy-variants
```

V1 variants are config/objective presets:

- `baseline_fifo_rule`
- `l3_due_date_aggressive`
- `l3_throughput_aggressive`
- `c_grouped_packing`
- `bottleneck_relief`

### Run Experiment

```http
POST /api/v2/ai-dev/experiments/run
```

Request:

```python
{
    "scenario_id": "SCN_...",
    "variant_ids": ["baseline_fifo_rule", "c_grouped_packing"]
}
```

Response:

```python
{
    "experiment_id": "EXP_...",
    "scenario_id": "SCN_...",
    "count": 2,
    "results": [
        {
            "variant_id": "baseline_fifo_rule",
            "correlation_id": "CORR_EXP_...",
            "l4_objective_id": "OBJ_THROUGHPUT_FIRST",
            "selected_stage": "A",
            "selected_candidate_id": "CAND_A_...",
            "candidate_count": 5,
            "local_score": 17.8,
            "upper_score": 23.9,
            "quality_risk": "LOW",
            "command_valid": True,
            "validation_status": "PASSED",
            "portfolio": {"items": []},
            "score_components": {},
            "kpi_delta": {
                "selected_task_count": 3,
                "expected_wip_reduction": 3,
                "expected_completion_delta": 0,
                "command_count_delta": 1
            }
        }
    ],
    "comparison": {
        "best_variant_id": "baseline_fifo_rule",
        "best_reason": "highest_upper_score_then_expected_wip_reduction",
        "decision_diff": []
    }
}
```

### Read Experiment

```http
GET /api/v2/ai-dev/experiments/{experiment_id}
```

Returns the stored in-memory experiment payload. V1 experiment storage is reset
with the runtime and is not part of SQLite genealogy.

## API Evolution Rules

- Keep `/api/v1/*` stable for current UI.
- Add new candidate-portfolio endpoints without breaking existing harness APIs.
- Keep `/api/v2/*` simulation control endpoints as MVP runtime controls.
- Keep `/api/v2/ai-dev/*` as explicit development endpoints. They may replay
  frozen state, but they must not mutate the live simulator except scenario
  capture metadata stored on the API context.
- Do not expose direct simulator mutations except through validated commands or
  explicit development endpoints such as task generation/reset.
