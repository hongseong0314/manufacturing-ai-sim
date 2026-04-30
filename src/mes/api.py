# -*- coding: utf-8 -*-
"""Minimal FastAPI read surface for simulator-backed MES MVP."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, Query

from src.environment.manufacturing_env import ManufacturingEnv
from src.mes import MESDevelopmentHarness


def _build_default_env() -> ManufacturingEnv:
    env = ManufacturingEnv(
        {
            "num_machines_A": 1,
            "num_machines_B": 1,
            "num_machines_C": 1,
            "process_time_A": 1,
            "process_time_B": 1,
            "process_time_C": 0,
            "deterministic_mode": True,
        }
    )
    env.reset(seed=11)
    return env


class MESAPIContext:
    """Shared runtime context for API handlers."""

    def __init__(self):
        self.env = _build_default_env()
        self.harness = MESDevelopmentHarness()


context = MESAPIContext()
app = FastAPI(title="Manufacturing AI MES MVP API", version="0.1.0")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/harness/run")
def run_harness(target_stage: str = Query("A", pattern="^[ABCabc]$")) -> Dict[str, Any]:
    result = context.harness.run(context.env.get_decision_state(), target_stage=target_stage.upper())
    return result.to_dict()


@app.get("/api/v1/kpis/fab")
def get_fab_kpis() -> Dict[str, Any]:
    mes_state = context.harness.service.decision_state_to_mes(context.env.get_decision_state())
    return {
        "time": mes_state.get("time", 0),
        "kpis": mes_state.get("kpis", {}),
        "wip": mes_state.get("wip", {}),
    }


@app.get("/api/v1/wip")
def get_wip() -> Dict[str, Any]:
    mes_state = context.harness.service.decision_state_to_mes(context.env.get_decision_state())
    return {
        "time": mes_state.get("time", 0),
        "wip": mes_state.get("wip", {}),
    }


@app.get("/api/v1/equipment")
def get_equipment() -> Dict[str, Any]:
    mes_state = context.harness.service.decision_state_to_mes(context.env.get_decision_state())
    return {
        "time": mes_state.get("time", 0),
        "equipment": mes_state.get("equipment", []),
    }


@app.get("/api/v1/ai/recommendations")
def get_recommendations(correlation_id: Optional[str] = None) -> Dict[str, Any]:
    data = [r.to_dict() for r in context.harness.store.recommendations(correlation_id)]
    return {"items": data, "count": len(data)}


@app.get("/api/v1/events")
def get_events(correlation_id: Optional[str] = None) -> Dict[str, Any]:
    data = [e.to_dict() for e in context.harness.store.events(correlation_id)]
    return {"items": data, "count": len(data)}


@app.get("/api/v1/dispatch/candidates")
def get_dispatch_candidates(stage: str = Query("A", pattern="^[ABCabc]$")) -> Dict[str, Any]:
    decision_state = context.env.get_decision_state()
    resolved_stage = stage.upper()
    items = context.harness.service.dispatch_candidates(decision_state, stage=resolved_stage)
    return {"stage": resolved_stage, "items": items, "count": len(items)}


@app.post("/api/v1/rules/validate")
def validate_rules(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    decision_state = context.env.get_decision_state()
    recommendations: List[Any] = list(payload.get("recommendations", []))
    validation = context.harness.service.validate_recommendations(decision_state, recommendations)
    return validation.to_dict()


@app.post("/api/v1/commands/track-in/preview")
def preview_track_in(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    target_stage = str(payload.get("target_stage", "A")).upper()
    correlation_id = payload.get("correlation_id")
    result = context.harness.run(
        context.env.get_decision_state(),
        target_stage=target_stage,
        correlation_id=str(correlation_id) if correlation_id else None,
    )
    return result.to_dict()


@app.post("/api/v1/commands/track-in/execute")
def execute_track_in(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    target_stage = str(payload.get("target_stage", "A")).upper()
    correlation_id = payload.get("correlation_id")
    result = context.harness.run_and_step(
        context.env,
        target_stage=target_stage,
        correlation_id=str(correlation_id) if correlation_id else None,
    )
    return result.to_dict()
