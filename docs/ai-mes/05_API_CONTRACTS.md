# API Contracts

Status: canonical  
Last updated: 2026-05-06

## Purpose

This document defines the simulator-backed MES API surface and the target API
contracts needed for the layered AI architecture.

The current implementation lives in `src/mes/api.py`.

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
| `GET /api/v1/dispatch/candidates?stage=A` | Rule-only dispatch candidates |
| `GET /api/v1/ai/recommendations` | Recommendation records, optional `correlation_id` |
| `GET /api/v1/events` | Event records, optional `correlation_id` |
| `GET /api/v1/commands` | Command records, optional `correlation_id` |
| `GET /api/v2/decision-chain/{correlation_id}` | Aggregated chain details |
| `GET /api/v2/equipment/{equipment_id}/detail` | A/B machine quality dashboard data |
| `GET /api/v2/gantt` | Gantt rows, bars, stage views, and horizon |
| `GET /api/v2/fab/live` | Live control-room state |

## Current Mutation APIs

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/harness/run` | Run harness preview for one stage or AUTO |
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

## Target Layered AI APIs

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
when the API request is valid but the recommendation is not executable.

## API Evolution Rules

- Keep `/api/v1/*` stable for current UI.
- Add new candidate-portfolio endpoints without breaking existing harness APIs.
- Keep `/api/v2/*` simulation control endpoints as MVP runtime controls.
- Do not expose direct simulator mutations except through validated commands or
  explicit development endpoints such as task generation/reset.

