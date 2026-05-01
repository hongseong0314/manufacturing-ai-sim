# -*- coding: utf-8 -*-
"""FastAPI surface for the simulator-backed MES MVP."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from src.environment.manufacturing_env import ManufacturingEnv
from src.mes import MESDevelopmentHarness
from src.mes.domain import AIRecommendation
from src.mes.live_ui import LIVE_MES_HTML
from src.mes.sqlite_store import SQLiteMESStore


STAGES = ("A", "B", "C")
EMPTY_ACTIONS = {"A": {}, "B": {}, "C": {}}


def _build_default_env() -> ManufacturingEnv:
    env = ManufacturingEnv(
        {
            "num_machines_A": 10,
            "num_machines_B": 5,
            "num_machines_C": 3,
            "batch_size_C": 4,
            "max_packs_per_step": 3,
            "process_time_A": 1,
            "process_time_B": 1,
            "process_time_C": 0,
            "deterministic_mode": True,
        }
    )
    env.reset(seed=11)
    return env


def _default_db_path() -> Path:
    return Path(os.environ.get("MES_DB_PATH", "data/mes_mvp.sqlite3"))


class MESAPIContext:
    def __init__(self):
        self.env = _build_default_env()
        self.store = SQLiteMESStore(_default_db_path())
        self.harness = MESDevelopmentHarness(store=self.store)
        self.autoplay_enabled = False
        self.autoplay_target_stage = "AUTO"
        self.autoplay_generate_every = 20
        self.last_generation_time: Optional[int] = None
        self.last_correlation_id: Optional[str] = None
        self.last_cycle: Optional[Dict[str, Any]] = None

    def reset_runtime(self) -> None:
        self.env = _build_default_env()
        self.autoplay_enabled = False
        self.autoplay_target_stage = "AUTO"
        self.last_generation_time = None
        self.last_correlation_id = None
        self.last_cycle = None


context = MESAPIContext()
app = FastAPI(title="Manufacturing AI MES MVP API", version="0.2.0")


def _normalize_target_stage(value: Optional[str], default: str = "AUTO") -> str:
    stage = str(value or default).upper()
    if stage not in {*STAGES, "AUTO"}:
        raise HTTPException(status_code=400, detail=f"unknown target_stage: {value}")
    return stage


def _mes_state() -> Dict[str, Any]:
    return context.harness.service.decision_state_to_mes(context.env.get_decision_state())


def _generate_tasks(time_point: Optional[int] = None) -> Dict[str, Any]:
    current_time = int(context.env.time if time_point is None else time_point)
    tasks = context.env.data_generator.generate_new_jobs(current_time)
    context.env.env_A.add_tasks(tasks)
    context.last_generation_time = current_time
    return {
        "time_point": current_time,
        "inserted_count": len(tasks),
        "task_uids": [task.uid for task in tasks],
        "queue_a_size": len(context.env.env_A.wait_pool),
    }


def _maybe_generate_periodic_tasks() -> Optional[Dict[str, Any]]:
    interval = int(context.autoplay_generate_every or 0)
    now = int(context.env.time)
    if interval <= 0 or now <= 0:
        return None
    if now % interval != 0 or context.last_generation_time == now:
        return None
    return _generate_tasks(now)


def _merge_actions(
    base: Dict[str, Dict[str, Any]],
    patch: Dict[str, Dict[str, Any]],
) -> None:
    for stage in STAGES:
        base.setdefault(stage, {})
        base[stage].update(patch.get(stage, {}))


def _ready_stages(target_stage: str) -> List[str]:
    if target_stage in STAGES:
        return [target_stage]
    state = context.env.get_decision_state()
    return [
        stage
        for stage in ("C", "B", "A")
        if context.harness.service.dispatch_candidates(state, stage=stage)
    ]


def _reserve_assignment_in_state(
    decision_state: Dict[str, Any],
    command: Dict[str, Any],
) -> Dict[str, Any]:
    """Reserve one validated command inside a planning snapshot.

    AUTO mode can safely issue several audited commands in one simulator tick.
    Between those commands, the working snapshot must hide already selected
    wafers and equipment so the next planner/generator pass uses a different
    idle tool.
    """
    stage = str(command.get("stage", "")).upper()
    equipment_id = str(command.get("equipment_id", ""))
    if stage not in STAGES or not equipment_id:
        return decision_state

    try:
        task_uids = [int(uid) for uid in command.get("task_uids", [])]
    except (TypeError, ValueError):
        task_uids = []
    if not task_uids:
        return decision_state

    cloned = copy.deepcopy(decision_state)
    stage_state = dict(cloned.get(stage, {}))
    selected_uids = set(task_uids)

    for key in (
        "wait_pool_uids",
        "rework_pool_uids",
        "incoming_from_A_uids",
        "incoming_from_B_uids",
    ):
        values = stage_state.get(key)
        if not isinstance(values, list):
            continue
        stage_state[key] = [
            uid for uid in values if int(uid) not in selected_uids
        ]

    machines = dict(stage_state.get("machines", {}))
    machine_key = equipment_id
    if machine_key not in machines:
        suffix = equipment_id.split("_")[-1]
        for candidate_key in machines:
            if str(candidate_key).split("_")[-1] == suffix:
                machine_key = candidate_key
                break

    machine_state = machines.get(machine_key)
    if isinstance(machine_state, dict):
        reserved_machine = dict(machine_state)
        current_time = int(cloned.get("time", 0) or 0)
        reserved_machine["status"] = "busy"
        reserved_machine["finish_time"] = current_time + 1
        reserved_machine["current_batch_uids"] = task_uids
        machines[machine_key] = reserved_machine

    stage_state["machines"] = machines
    cloned[stage] = stage_state
    return cloned


def _run_parallel_stage(
    stage: str,
    decision_state: Dict[str, Any],
) -> tuple[List[Any], Dict[str, Any]]:
    working_state = copy.deepcopy(decision_state)
    stage_state = working_state.get(stage, {})
    max_assignments = max(1, len(stage_state.get("machines", {})))
    results = []

    for _ in range(max_assignments):
        candidates = context.harness.service.dispatch_candidates(
            working_state,
            stage=stage,
        )
        if not candidates:
            break

        result = context.harness.run(working_state, target_stage=stage)
        results.append(result)
        if not result.passed or result.command is None:
            break

        working_state = _reserve_assignment_in_state(
            working_state,
            result.generated.validation.validated_command,
        )

    return results, working_state


def _record_step_for_results(
    results: List[Any],
    step_result: Dict[str, Any],
) -> None:
    post_state = context.env.get_decision_state()
    for result in results:
        result.step_result = step_result
        if result.command is not None:
            context.harness.store.record_command_executed(
                result.command.command_id,
                step_result=step_result,
                post_decision_state=post_state,
            )


def _run_auto_cycle() -> Dict[str, Any]:
    generated_tasks = _maybe_generate_periodic_tasks()
    state = context.env.get_decision_state()
    stages = _ready_stages("AUTO")
    results = []
    working_state = copy.deepcopy(state)
    combined_actions = {"A": {}, "B": {}, "C": {}}

    for stage in stages:
        stage_results, working_state = _run_parallel_stage(stage, working_state)
        results.extend(stage_results)
        for result in stage_results:
            if result.passed and result.command is not None:
                _merge_actions(combined_actions, result.simulator_actions)

    if any(combined_actions[stage] for stage in STAGES):
        observation, reward, done, info = context.env.step(combined_actions)
        step_result = {
            "observation": observation,
            "reward": reward,
            "done": done,
            "info": info,
        }
        _record_step_for_results(results, step_result)
        stop_reason = "executed"
    else:
        observation, reward, done, info = context.env.step(EMPTY_ACTIONS)
        step_result = {
            "observation": observation,
            "reward": reward,
            "done": done,
            "info": info,
        }
        stop_reason = "no_candidates"

    if results:
        context.last_correlation_id = results[-1].generated.plan.correlation_id

    payload = {
        "mode": "AUTO",
        "target_stages": stages,
        "count": len(results),
        "stop_reason": stop_reason,
        "generated_tasks": generated_tasks,
        "combined_actions": combined_actions,
        "step_result": step_result,
        "cycles": [result.to_dict() for result in results],
        "time": context.env.time,
    }
    context.last_cycle = payload
    return payload


def _run_single_cycle(
    target_stage: str,
    execute: bool,
    advance_on_reject: bool = False,
) -> Dict[str, Any]:
    if execute:
        result = context.harness.run_and_step(context.env, target_stage=target_stage)
        if not result.passed and advance_on_reject:
            observation, reward, done, info = context.env.step(EMPTY_ACTIONS)
            result.step_result = {
                "observation": observation,
                "reward": reward,
                "done": done,
                "info": info,
            }
    else:
        result = context.harness.run(
            context.env.get_decision_state(),
            target_stage=target_stage,
        )
    context.last_correlation_id = result.generated.plan.correlation_id
    payload = result.to_dict()
    context.last_cycle = payload
    return payload


def _tick_once(target_stage: str) -> Dict[str, Any]:
    target_stage = _normalize_target_stage(target_stage)
    if target_stage == "AUTO":
        return _run_auto_cycle()
    _maybe_generate_periodic_tasks()
    return _run_single_cycle(target_stage, execute=True, advance_on_reject=True)


def _stage_summary(stage: str, decision_state: Dict[str, Any]) -> Dict[str, Any]:
    stage_state = decision_state.get(stage, {})
    incoming_key = "incoming_from_A_uids" if stage == "B" else "incoming_from_B_uids"
    machines = []
    running = 0
    idle = 0
    for equipment_id, machine in sorted(stage_state.get("machines", {}).items()):
        status = str(machine.get("status", "UNKNOWN")).upper()
        if status == "BUSY":
            running += 1
        if status == "IDLE":
            idle += 1
        machines.append(
            {
                "equipment_id": str(equipment_id),
                "stage": stage,
                "status": status,
                "current_batch_uids": list(machine.get("current_batch_uids", [])),
                "finish_time": machine.get("finish_time"),
                "batch_size": machine.get("batch_size"),
            }
        )
    wait = len(stage_state.get("wait_pool_uids", []))
    rework = len(stage_state.get("rework_pool_uids", []))
    incoming = len(stage_state.get(incoming_key, [])) if stage != "A" else 0
    return {
        "label": {
            "A": "Process QA",
            "B": "Clean QA",
            "C": "Packing",
        }[stage],
        "wait": wait,
        "incoming": incoming,
        "rework": rework,
        "running": running,
        "idle": idle,
        "total_wip": wait + rework + incoming,
        "status": "RUN" if running else "READY",
        "focus": bool(context.harness.service.dispatch_candidates(decision_state, stage)),
        "machines": machines,
    }


def _fab_kpis() -> Dict[str, Any]:
    decision_state = context.env.get_decision_state()
    mes_state = context.harness.service.decision_state_to_mes(decision_state)
    wip = mes_state.get("wip", {})
    total_wip = sum(int(stage.get("total", 0)) for stage in wip.values())
    completed = int(decision_state.get("num_completed", 0))
    elapsed = max(1, int(decision_state.get("time", 0)))
    total_machines = 0
    busy_machines = 0
    for stage in STAGES:
        for machine in decision_state.get(stage, {}).get("machines", {}).values():
            total_machines += 1
            if str(machine.get("status", "")).lower() == "busy":
                busy_machines += 1

    stats_a = getattr(context.env.env_A, "stats", {})
    stats_b = getattr(context.env.env_B, "stats", {})
    processed = int(stats_a.get("total_processed", 0)) + int(
        stats_b.get("total_processed", 0)
    )
    reworked = int(stats_a.get("total_reworked", 0)) + int(
        stats_b.get("total_reworked", 0)
    )
    yield_proxy = (processed - reworked) / processed if processed else 1.0
    executed_commands = len(context.harness.store.commands(status="EXECUTED"))
    return {
        "time": decision_state.get("time", 0),
        "total_wip": total_wip,
        "completed": completed,
        "throughput": completed / elapsed,
        "yield_proxy": round(max(0.0, yield_proxy), 4),
        "equipment_utilization": busy_machines / total_machines
        if total_machines
        else 0.0,
        "busy_machines": busy_machines,
        "total_machines": total_machines,
        "processed": processed,
        "reworked": reworked,
        "executed_commands": executed_commands,
        "recommendation_count": len(context.harness.store.recommendations()),
        "event_count": len(context.harness.store.events()),
    }


def _latest_correlation_id() -> Optional[str]:
    if context.last_correlation_id:
        return context.last_correlation_id
    commands = context.harness.store.commands()
    if commands:
        return commands[-1].correlation_id
    events = context.harness.store.events()
    if events:
        return events[-1].correlation_id
    return None


def _decision_chain(correlation_id: Optional[str]) -> Dict[str, Any]:
    if not correlation_id:
        return {
            "correlation_id": None,
            "recommendations": [],
            "events": [],
            "validations": [],
            "commands": [],
            "counts": {"recommendations": 0, "events": 0, "validations": 0, "commands": 0},
        }
    recommendations = context.harness.store.recommendations(correlation_id)
    layer_order = {layer: index for index, layer in enumerate(("L4", "L3", "L1", "L2"))}
    recommendations = sorted(
        recommendations,
        key=lambda rec: layer_order.get(rec.layer_id, 99),
    )
    events = context.harness.store.events(correlation_id)
    validations = context.harness.store.validations(correlation_id)
    commands = context.harness.store.commands(correlation_id)
    validation_status = validations[-1].validation_status if validations else "PENDING"
    return {
        "correlation_id": correlation_id,
        "recommendations": [item.to_dict() for item in recommendations],
        "events": [item.to_dict() for item in events],
        "validations": [item.to_dict() for item in validations],
        "commands": [item.to_dict() for item in commands],
        "validation_status": validation_status,
        "counts": {
            "recommendations": len(recommendations),
            "events": len(events),
            "validations": len(validations),
            "commands": len(commands),
        },
    }


def _live_fab_state() -> Dict[str, Any]:
    decision_state = context.env.get_decision_state()
    stages = {
        stage: _stage_summary(stage, decision_state)
        for stage in STAGES
    }
    equipment = [
        machine
        for stage in STAGES
        for machine in stages[stage]["machines"]
    ]
    correlation_id = _latest_correlation_id()
    recent_events = context.harness.store.events()[-18:]
    return {
        "time": decision_state.get("time", 0),
        "autoplay": {
            "enabled": context.autoplay_enabled,
            "target_stage": context.autoplay_target_stage,
            "generate_every": context.autoplay_generate_every,
        },
        "kpis": _fab_kpis(),
        "stages": stages,
        "equipment": equipment,
        "active_chain": _decision_chain(correlation_id),
        "recent_events": [event.to_dict() for event in recent_events],
        "last_cycle": context.last_cycle,
    }


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    return HTMLResponse(LIVE_MES_HTML)


@app.get("/mes", response_class=HTMLResponse)
def mes_screen() -> HTMLResponse:
    return HTMLResponse(LIVE_MES_HTML)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/decision-state")
def get_decision_state() -> Dict[str, Any]:
    return context.env.get_decision_state()


@app.get("/api/v1/kpis/fab")
def get_fab_kpis() -> Dict[str, Any]:
    return _fab_kpis()


@app.get("/api/v1/wip")
def get_wip() -> Dict[str, Any]:
    mes_state = _mes_state()
    return {"time": mes_state.get("time", 0), "wip": mes_state.get("wip", {})}


@app.get("/api/v1/equipment")
def get_equipment() -> Dict[str, Any]:
    mes_state = _mes_state()
    items = mes_state.get("equipment", [])
    return {"time": mes_state.get("time", 0), "count": len(items), "items": items}


@app.get("/api/v1/lots")
def get_lots() -> Dict[str, Any]:
    mes_state = _mes_state()
    items = mes_state.get("lots", [])
    return {"time": mes_state.get("time", 0), "count": len(items), "items": items}


@app.get("/api/v1/wafers")
def get_wafers() -> Dict[str, Any]:
    mes_state = _mes_state()
    items = mes_state.get("wafers", [])
    return {"time": mes_state.get("time", 0), "count": len(items), "items": items}


@app.get("/api/v1/dispatch/candidates")
def get_dispatch_candidates(stage: str = Query("A")) -> Dict[str, Any]:
    target_stage = _normalize_target_stage(stage, default="A")
    if target_stage == "AUTO":
        raise HTTPException(status_code=400, detail="stage must be A, B, or C")
    items = context.harness.service.dispatch_candidates(
        context.env.get_decision_state(),
        stage=target_stage,
    )
    return {"time": context.env.time, "stage": target_stage, "count": len(items), "items": items}


@app.post("/api/v1/harness/run")
def harness_run(target_stage: str = Query("A")) -> Dict[str, Any]:
    target = _normalize_target_stage(target_stage, default="A")
    if target == "AUTO":
        return _run_auto_cycle()
    return _run_single_cycle(target, execute=False)


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
    target = _normalize_target_stage(payload.get("target_stage"), default="A")
    if target == "AUTO":
        target = _ready_stages("AUTO")[0] if _ready_stages("AUTO") else "A"
    return _run_single_cycle(target, execute=False)


@app.post("/api/v1/commands/track-in/execute")
def execute_track_in(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    target = _normalize_target_stage(payload.get("target_stage"), default="A")
    if target == "AUTO":
        return _run_auto_cycle()
    return _run_single_cycle(target, execute=True)


@app.post("/api/v2/tasks/generate")
def generate_tasks(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    time_point = payload.get("time_point")
    return _generate_tasks(None if time_point is None else int(time_point))


@app.post("/api/v2/harness/run-cycle")
def run_cycle(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    target = _normalize_target_stage(payload.get("target_stage"), default="AUTO")
    if target == "AUTO":
        return _run_auto_cycle()
    return _run_single_cycle(target, execute=True)


@app.post("/api/v2/harness/run-until")
def run_until(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    target = _normalize_target_stage(payload.get("target_stage"), default="AUTO")
    max_cycles = max(1, min(500, int(payload.get("max_cycles", 25))))
    cycles: List[Dict[str, Any]] = []
    stop_reason = "max_cycles"
    for _ in range(max_cycles):
        cycle = _run_auto_cycle() if target == "AUTO" else _run_single_cycle(
            target,
            execute=True,
        )
        cycles.append(cycle)
        if cycle.get("stop_reason") == "no_candidates":
            stop_reason = "no_candidates"
            break
        validation = cycle.get("generated", {}).get("validation", {})
        if validation.get("validation_status") == "REJECTED":
            stop_reason = "rejected"
            break
    return {"count": len(cycles), "stop_reason": stop_reason, "cycles": cycles}


@app.get("/api/v2/decision-chain/{correlation_id}")
def decision_chain(correlation_id: str) -> Dict[str, Any]:
    return _decision_chain(correlation_id)


@app.post("/api/v2/simulation/reset")
def reset_simulation() -> Dict[str, Any]:
    context.reset_runtime()
    return _live_fab_state()


@app.post("/api/v2/simulation/autoplay/start")
def autoplay_start(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    context.autoplay_enabled = True
    context.autoplay_target_stage = _normalize_target_stage(
        payload.get("target_stage"),
        default="AUTO",
    )
    context.autoplay_generate_every = max(1, int(payload.get("generate_every", 20)))
    cycles = max(0, min(50, int(payload.get("bootstrap_cycles", 1))))
    last = None
    for _ in range(cycles):
        last = _tick_once(context.autoplay_target_stage)
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
            _tick_once(context.autoplay_target_stage)
            stepped += 1
    return {
        "enabled": context.autoplay_enabled,
        "target_stage": context.autoplay_target_stage,
        "time": context.env.time,
        "stepped_cycles": stepped,
        "live": _live_fab_state(),
    }


@app.get("/api/v2/fab/live")
def fab_live() -> Dict[str, Any]:
    return _live_fab_state()
