# -*- coding: utf-8 -*-
"""FastAPI route wiring for the simulator-backed MES MVP."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from src.mes.domain import AIRecommendation
from src.mes.runtime.ai_dev import (
    ai_dev_candidate_portfolio,
    decision_cycles_payload,
    policy_stack_payload,
)
from src.mes.runtime.common import normalize_target_stage
from src.mes.runtime.context import MESAPIContext
from src.mes.runtime.candidate_portfolio import (
    candidate_portfolio as build_candidate_portfolio,
    latest_candidate_portfolio,
)
from src.mes.runtime.decision_trace import decision_chain as build_decision_chain
from src.mes.runtime.equipment_detail import equipment_detail as build_equipment_detail
from src.mes.runtime.gantt import gantt_state
from src.mes.runtime.live_state import fab_kpis, live_fab_state, mes_state
from src.mes.runtime.simulation_control import (
    generate_tasks as generate_runtime_tasks,
    ready_stages,
    run_auto_cycle,
    run_single_cycle,
    run_until as run_until_cycles,
    tick_once,
)
from src.mes.ui.assets import control_room_html


context = MESAPIContext()
app = FastAPI(title="Manufacturing AI MES MVP API", version="0.2.0")


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    return HTMLResponse(control_room_html())


@app.get("/mes", response_class=HTMLResponse)
def mes_screen() -> HTMLResponse:
    return HTMLResponse(control_room_html())


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/decision-state")
def get_decision_state() -> Dict[str, Any]:
    return context.env.get_decision_state()


@app.get("/api/v1/kpis/fab")
def get_fab_kpis() -> Dict[str, Any]:
    return fab_kpis(context)


@app.get("/api/v1/wip")
def get_wip() -> Dict[str, Any]:
    state = mes_state(context)
    return {"time": state.get("time", 0), "wip": state.get("wip", {})}


@app.get("/api/v1/equipment")
def get_equipment() -> Dict[str, Any]:
    state = mes_state(context)
    items = context.harness.store.equipment()
    return {
        "time": state.get("time", 0),
        "count": len(items),
        "items": [item.to_dict() for item in items],
    }


@app.get("/api/v1/lots")
def get_lots() -> Dict[str, Any]:
    state = mes_state(context)
    items = context.harness.store.lots()
    return {
        "time": state.get("time", 0),
        "count": len(items),
        "items": [item.to_dict() for item in items],
    }


@app.get("/api/v1/wafers")
def get_wafers(lot_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    state = mes_state(context)
    items = context.harness.store.wafers(lot_id)
    return {
        "time": state.get("time", 0),
        "lot_id": lot_id,
        "count": len(items),
        "items": [item.to_dict() for item in items],
    }


@app.get("/api/v1/recipes")
def get_recipes(operation_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    state = mes_state(context)
    items = context.harness.store.recipes(operation_id)
    return {
        "time": state.get("time", 0),
        "operation_id": operation_id,
        "count": len(items),
        "items": [item.to_dict() for item in items],
    }


@app.get("/api/v1/dispatch/candidates")
def get_dispatch_candidates(stage: str = Query("A")) -> Dict[str, Any]:
    target_stage = normalize_target_stage(stage, default="A")
    if target_stage == "AUTO":
        raise HTTPException(status_code=400, detail="stage must be A, B, or C")
    items = context.harness.service.dispatch_candidates(
        context.env.get_decision_state(),
        stage=target_stage,
    )
    return {"time": context.env.time, "stage": target_stage, "count": len(items), "items": items}


@app.post("/api/v1/harness/run")
def harness_run(target_stage: str = Query("A")) -> Dict[str, Any]:
    target = normalize_target_stage(target_stage, default="A")
    if target == "AUTO":
        return run_auto_cycle(context)
    return run_single_cycle(context, target, execute=False)


@app.get("/api/v1/ai/recommendations")
def get_recommendations(
    correlation_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    items = context.harness.store.recommendations(correlation_id)
    return {
        "time": context.env.time,
        "correlation_id": correlation_id,
        "count": len(items),
        "items": [item.to_dict() for item in items],
    }


@app.get("/api/v1/events")
def get_events(correlation_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    items = context.harness.store.events(correlation_id)
    return {
        "time": context.env.time,
        "correlation_id": correlation_id,
        "count": len(items),
        "items": [item.to_dict() for item in items],
    }


@app.get("/api/v1/commands")
def get_commands(correlation_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    items = context.harness.store.commands(correlation_id)
    return {
        "time": context.env.time,
        "correlation_id": correlation_id,
        "count": len(items),
        "items": [item.to_dict() for item in items],
    }


@app.post("/api/v1/rules/validate")
def validate_rules(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    recommendations = [
        AIRecommendation(**item)
        for item in payload.get("recommendations", [])
    ]
    validation = context.harness.service.validate_recommendations(
        context.env.get_decision_state(),
        recommendations,
    )
    return validation.to_dict()


@app.post("/api/v1/commands/track-in/preview")
def preview_track_in(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    target = normalize_target_stage(payload.get("target_stage"), default="A")
    if target == "AUTO":
        stages = ready_stages(context, "AUTO")
        target = stages[0] if stages else "A"
    return run_single_cycle(context, target, execute=False)


@app.post("/api/v1/commands/track-in/execute")
def execute_track_in(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    target = normalize_target_stage(payload.get("target_stage"), default="A")
    if target == "AUTO":
        return run_auto_cycle(context)
    return run_single_cycle(context, target, execute=True)


@app.post("/api/v2/tasks/generate")
def generate_tasks(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    time_point = payload.get("time_point")
    return generate_runtime_tasks(context, None if time_point is None else int(time_point))


@app.post("/api/v2/harness/run-cycle")
def run_cycle(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    target = normalize_target_stage(payload.get("target_stage"), default="AUTO")
    if target == "AUTO":
        return run_auto_cycle(context)
    return run_single_cycle(context, target, execute=True)


@app.post("/api/v2/harness/run-until")
def run_until(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    target = normalize_target_stage(payload.get("target_stage"), default="AUTO")
    max_cycles = max(1, min(500, int(payload.get("max_cycles", 25))))
    return run_until_cycles(context, target, max_cycles)


@app.get("/api/v2/decision-chain/{correlation_id}")
def decision_chain(correlation_id: str) -> Dict[str, Any]:
    return build_decision_chain(context, correlation_id)


@app.get("/api/v2/candidate-portfolio/latest")
def candidate_portfolio_latest() -> Dict[str, Any]:
    return latest_candidate_portfolio(context)


@app.get("/api/v2/candidate-portfolio/{correlation_id}")
def candidate_portfolio(correlation_id: str) -> Dict[str, Any]:
    return build_candidate_portfolio(context, correlation_id)


@app.get("/api/v2/ai-dev/policy-stack")
def ai_dev_policy_stack() -> Dict[str, Any]:
    return policy_stack_payload(context)


@app.get("/api/v2/ai-dev/decision-cycles")
def ai_dev_decision_cycles(limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
    return decision_cycles_payload(context, limit=limit)


@app.get("/api/v2/ai-dev/candidate-portfolio/{correlation_id}")
def ai_dev_portfolio(correlation_id: str) -> Dict[str, Any]:
    return ai_dev_candidate_portfolio(context, correlation_id)


@app.get("/api/v2/equipment/{equipment_id}/detail")
def equipment_detail(equipment_id: str) -> Dict[str, Any]:
    return build_equipment_detail(context, equipment_id)


@app.get("/api/v2/gantt")
def gantt(
    lookback: int = Query(36, ge=6, le=240),
    lookahead: int = Query(12, ge=4, le=120),
) -> Dict[str, Any]:
    return gantt_state(context, lookback=lookback, lookahead=lookahead)


@app.post("/api/v2/simulation/reset")
def reset_simulation() -> Dict[str, Any]:
    context.reset_runtime()
    return live_fab_state(context)


@app.post("/api/v2/simulation/autoplay/start")
def autoplay_start(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    context.autoplay_enabled = True
    context.autoplay_target_stage = normalize_target_stage(
        payload.get("target_stage"),
        default="AUTO",
    )
    context.autoplay_generate_every = max(1, int(payload.get("generate_every", 20)))
    cycles = max(0, min(50, int(payload.get("bootstrap_cycles", 1))))
    last = None
    for _ in range(cycles):
        last = tick_once(context, context.autoplay_target_stage)
    return {
        "enabled": True,
        "target_stage": context.autoplay_target_stage,
        "generate_every": context.autoplay_generate_every,
        "time": context.env.time,
        "last_cycle": last,
    }


@app.post("/api/v2/simulation/autoplay/stop")
def autoplay_stop() -> Dict[str, Any]:
    context.autoplay_enabled = False
    return {"enabled": False, "time": context.env.time}


@app.get("/api/v2/simulation/autoplay/status")
def autoplay_status(step_cycles: int = Query(0, ge=0, le=100)) -> Dict[str, Any]:
    stepped = 0
    if context.autoplay_enabled and step_cycles > 0:
        for _ in range(step_cycles):
            tick_once(context, context.autoplay_target_stage)
            stepped += 1
    return {
        "enabled": context.autoplay_enabled,
        "target_stage": context.autoplay_target_stage,
        "time": context.env.time,
        "stepped_cycles": stepped,
        "live": live_fab_state(context),
    }


@app.get("/api/v2/fab/live")
def fab_live() -> Dict[str, Any]:
    return live_fab_state(context)
