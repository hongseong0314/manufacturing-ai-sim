# -*- coding: utf-8 -*-
"""FastAPI surface for the simulator-backed MES MVP."""

from __future__ import annotations

import copy
import os
from collections import Counter
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
            "num_machines_A": 5,
            "num_machines_B": 3,
            "num_machines_C": 3,
            "batch_size_A": 3,
            "batch_size_B": 2,
            "batch_size_C": 4,
            "max_packs_per_step": 3,
            "process_time_A": 20,
            "process_time_B": 8,
            "process_time_C": 2,
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
        self.harness = MESDevelopmentHarness(config=self.env.config, store=self.store)
        self.autoplay_enabled = False
        self.autoplay_target_stage = "AUTO"
        self.autoplay_generate_every = 20
        self.last_generation_time: Optional[int] = None
        self.last_correlation_id: Optional[str] = None
        self.last_cycle: Optional[Dict[str, Any]] = None

    def reset_runtime(self) -> None:
        self.env = _build_default_env()
        self.store.clear_runtime_state()
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
    mes_state = context.harness.service.decision_state_to_mes(
        context.env.get_decision_state()
    )
    context.harness.store.sync_runtime_state(mes_state)
    return mes_state


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
        reserved_machine["finish_time"] = current_time + _stage_process_time(stage)
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
    budget_plan = context.harness.planner.plan(state)
    budget_action = dict(budget_plan.stage_priority.recommended_action or {})
    candidate_by_id = {
        candidate.get("candidate_id"): candidate
        for candidate in budget_plan.candidate_portfolio
        if candidate.get("candidate_id")
    }
    selected_candidate_ids = [
        candidate_id
        for candidate_id in budget_action.get("selected_candidate_ids", [])
        if candidate_id in candidate_by_id
    ]
    stages = [
        stage
        for stage, budget in budget_action.get("dispatch_budgets", {}).items()
        if int(budget or 0) > 0
    ]
    results = []
    working_state = copy.deepcopy(state)
    combined_actions = {"A": {}, "B": {}, "C": {}}

    for candidate_id in selected_candidate_ids:
        candidate = candidate_by_id[candidate_id]
        stage = str(candidate.get("stage", "")).upper()
        if stage not in STAGES:
            continue
        result = context.harness.run(
            working_state,
            target_stage=stage,
            candidate_portfolio=[candidate],
        )
        results.append(result)
        if not result.passed or result.command is None:
            break
        _merge_actions(combined_actions, result.simulator_actions)
        working_state = _reserve_assignment_in_state(
            working_state,
            result.generated.validation.validated_command,
        )

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
        "selection_source": "l3_budget_plan",
        "budget_plan": budget_action,
        "budget_correlation_id": budget_plan.correlation_id,
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
    running_wip = 0
    for equipment_id, machine in sorted(stage_state.get("machines", {}).items()):
        status = str(machine.get("status", "UNKNOWN")).upper()
        if status == "BUSY":
            running += 1
            running_wip += len(machine.get("current_batch_uids", []) or [])
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
        "running_wip": running_wip,
        "total_wip": wait + rework + incoming + running_wip,
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
    recommendation_dicts = [item.to_dict() for item in recommendations]
    return {
        "correlation_id": correlation_id,
        "recommendations": recommendation_dicts,
        "events": [item.to_dict() for item in events],
        "validations": [item.to_dict() for item in validations],
        "commands": [item.to_dict() for item in commands],
        "traceability": _chain_traceability(recommendation_dicts, commands),
        "validation_status": validation_status,
        "counts": {
            "recommendations": len(recommendations),
            "events": len(events),
            "validations": len(validations),
            "commands": len(commands),
        },
    }


def _chain_traceability(
    recommendations: List[Dict[str, Any]],
    commands: List[Any],
) -> Dict[str, Any]:
    by_layer = {item.get("layer_id"): item for item in recommendations}
    l4 = by_layer.get("L4", {})
    l3 = by_layer.get("L3", {})
    l1 = by_layer.get("L1", {})
    l2 = by_layer.get("L2", {})
    l3_action = dict(l3.get("recommended_action") or {})
    selected_ids = set(l3_action.get("selected_candidate_ids") or [])
    selected_id = l3_action.get("selected_candidate_id")
    if selected_id:
        selected_ids.add(selected_id)
    candidate_actions = [
        candidate
        for candidate in l3.get("candidate_actions", [])
        if isinstance(candidate, dict)
    ]
    selected_candidates = [
        candidate
        for candidate in candidate_actions
        if candidate.get("candidate_id") in selected_ids
    ]
    l2_actions = [
        action
        for action in l2.get("candidate_actions", [])
        if isinstance(action, dict)
    ]
    command_dict = commands[-1].to_dict() if commands else {}
    validated_command = command_dict.get("validated_command", {})
    return {
        "objective_id": l4.get("objective_id"),
        "l4_policy_id": l4.get("policy_id"),
        "l3_policy_id": l3.get("policy_id"),
        "objective_weights": dict((l4.get("recommended_action") or {}).get("weights") or {}),
        "stage_priorities": dict(l3_action.get("stage_priorities") or {}),
        "dispatch_budgets": dict(l3_action.get("dispatch_budgets") or {}),
        "budget_candidate_ids": dict(l3_action.get("budget_candidate_ids") or {}),
        "selected_candidate_id": selected_id,
        "selected_candidate_ids": list(l3_action.get("selected_candidate_ids") or []),
        "selected_group_key": dict(l3_action.get("selected_group_key") or {}),
        "candidate_count": len(candidate_actions),
        "selected_candidates": selected_candidates,
        "l2_annotation_count": len(l2_actions),
        "l2_annotations": l2_actions,
        "final_l1_action": dict(l1.get("recommended_action") or {}),
        "final_l2_action": dict(l2.get("recommended_action") or {}),
        "command": validated_command,
    }


def _live_fab_state() -> Dict[str, Any]:
    decision_state = context.env.get_decision_state()
    _mes_state()
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


def _stage_env(stage: str) -> Any:
    return {"A": context.env.env_A, "B": context.env.env_B, "C": context.env.env_C}[stage]


def _stage_from_equipment_id(equipment_id: str) -> str:
    stage = str(equipment_id or "").split("_", 1)[0].upper()
    if stage not in STAGES:
        raise HTTPException(status_code=404, detail=f"unknown equipment: {equipment_id}")
    return stage


def _canonical_equipment_id(equipment_id: str) -> str:
    raw = str(equipment_id or "").strip()
    stage = _stage_from_equipment_id(raw)
    suffix = raw.split("_", 1)[1] if "_" in raw else raw[1:]
    return f"{stage}_{suffix}" if suffix else raw.upper()


def _recipe_label(stage: str, recipe: List[Any]) -> str:
    names = {
        "A": ("pressure", "speed", "dwell"),
        "B": ("clean", "rinse", "dry"),
    }.get(stage, tuple(f"p{i + 1}" for i in range(len(recipe))))
    return ", ".join(
        f"{name}={value:g}" if isinstance(value, (int, float)) else f"{name}={value}"
        for name, value in zip(names, recipe)
    )


def _target_window(target_specs: List[Dict[str, Any]]) -> Optional[List[float]]:
    lows: List[float] = []
    highs: List[float] = []
    for spec in target_specs or []:
        try:
            lows.append(float(spec["low"]))
            highs.append(float(spec["high"]))
        except (KeyError, TypeError, ValueError):
            continue
    if not lows or not highs:
        return None
    return [
        round(sum(lows) / len(lows), 3),
        round(sum(highs) / len(highs), 3),
    ]


def _machine_material_state(stage: str, source: Dict[str, Any]) -> Dict[str, Any]:
    if stage == "A":
        primary_key = "u"
        secondary_key = "m_age"
        primary_value = source.get("u", source.get("u_after_start", 0))
        secondary_value = source.get("m_age", source.get("m_age_after_start", 0))
        primary_label = "Consumable use"
        secondary_label = "Machine age"
    else:
        primary_key = "v"
        secondary_key = "b_age"
        primary_value = source.get("v", source.get("v_after_start", 0))
        secondary_value = source.get("b_age", source.get("b_age_after_start", 0))
        primary_label = "Solution use"
        secondary_label = "Bath age"
    try:
        primary_value = int(primary_value)
    except (TypeError, ValueError):
        primary_value = 0
    try:
        secondary_value = int(secondary_value)
    except (TypeError, ValueError):
        secondary_value = 0
    return {
        "primary_key": primary_key,
        "primary_label": primary_label,
        "primary_value": primary_value,
        "secondary_key": secondary_key,
        "secondary_label": secondary_label,
        "secondary_value": secondary_value,
        "state_label": f"{primary_key}={primary_value} / {secondary_key}={secondary_value}",
    }


def _machine_quality_series(stage: str, equipment_id: str) -> List[Dict[str, Any]]:
    series: List[Dict[str, Any]] = []
    env = _stage_env(stage)
    for index, event in enumerate(getattr(env, "event_log", []) or []):
        if str(event.get("event_type", "")) != "task_completed":
            continue
        if str(event.get("machine_id", "")) != equipment_id:
            continue

        raw_values = event.get("quality_values") or []
        quality_values: List[float] = []
        for raw_value in raw_values:
            try:
                quality_values.append(round(float(raw_value), 4))
            except (TypeError, ValueError):
                continue
        if event.get("avg_quality") is not None:
            try:
                quality = round(float(event["avg_quality"]), 4)
            except (TypeError, ValueError):
                quality = None
        else:
            quality = (
                round(sum(quality_values) / len(quality_values), 4)
                if quality_values
                else None
            )
        if quality is None:
            continue

        task_uids = [int(uid) for uid in event.get("task_uids", [])]
        recipe = list(event.get("recipe") or [])
        target_window = _target_window(event.get("target_specs", []))
        series.append(
            {
                "point_id": f"{equipment_id}-{event.get('timestamp', 0)}-{index}",
                "time": int(event.get("timestamp", event.get("end_time", 0)) or 0),
                "step": int(event.get("timestamp", event.get("end_time", 0)) or 0),
                "stage": stage,
                "equipment_id": equipment_id,
                "task_uids": task_uids,
                "task_codes": [_task_code(uid) for uid in task_uids],
                "quality": quality,
                "quality_values": quality_values,
                "recipe": recipe,
                "recipe_label": _recipe_label(stage, recipe),
                "material_state": _machine_material_state(stage, event),
                "target_window": target_window,
                "pass_count": int(event.get("pass_count", 0) or 0),
                "fail_count": int(event.get("fail_count", 0) or 0),
                "passed": bool(event.get("passed", False)),
                "event_type": "task_completed",
            }
        )
    return sorted(series, key=lambda point: (point["time"], point["point_id"]))


def _machine_recent_assignments(stage: str, equipment_id: str) -> List[Dict[str, Any]]:
    env = _stage_env(stage)
    assignments: List[Dict[str, Any]] = []
    for event in getattr(env, "event_log", []) or []:
        if str(event.get("event_type", "")) != "task_assigned":
            continue
        if str(event.get("machine_id", "")) != equipment_id:
            continue
        task_uids = [int(uid) for uid in event.get("task_uids", [])]
        recipe = list(event.get("recipe") or [])
        assignments.append(
            {
                "time": int(event.get("timestamp", event.get("start_time", 0)) or 0),
                "start": int(event.get("start_time", event.get("timestamp", 0)) or 0),
                "end": int(event.get("end_time", 0) or 0),
                "task_uids": task_uids,
                "task_codes": [_task_code(uid) for uid in task_uids],
                "task_type": event.get("task_type", "external_action"),
                "recipe": recipe,
                "recipe_label": _recipe_label(stage, recipe),
                "material_state": _machine_material_state(stage, event),
            }
        )
    return sorted(assignments, key=lambda item: item["time"], reverse=True)[:8]


def _task_rows_for_uids(
    decision_state: Dict[str, Any],
    task_uids: List[int],
) -> List[Dict[str, Any]]:
    tasks = decision_state.get("tasks", {})
    rows: List[Dict[str, Any]] = []
    if not isinstance(tasks, dict):
        return rows
    for uid in task_uids:
        row = tasks.get(uid) or tasks.get(str(uid))
        if isinstance(row, dict):
            rows.append(dict(row))
    return rows


def _count_values(rows: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    counts = Counter(str(row.get(key, "UNKNOWN")) for row in rows)
    return dict(sorted(counts.items()))


def _c_composition_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    material_counts = _count_values(rows, "material_type")
    color_counts = _count_values(rows, "color")
    batch_size = len(rows)
    material_match_count = max(material_counts.values()) if material_counts else 0
    color_match_count = max(color_counts.values()) if color_counts else 0
    denominator = max(1, batch_size * 2)
    composition_quality = round(
        ((material_match_count + color_match_count) / denominator) * 100,
        4,
    )
    dominant_material = (
        max(material_counts.items(), key=lambda item: item[1])[0]
        if material_counts
        else "UNKNOWN"
    )
    dominant_color = (
        max(color_counts.items(), key=lambda item: item[1])[0]
        if color_counts
        else "UNKNOWN"
    )
    return {
        "material_counts": material_counts,
        "color_counts": color_counts,
        "material_match_count": material_match_count,
        "color_match_count": color_match_count,
        "dominant_material": dominant_material,
        "dominant_color": dominant_color,
        "composition_quality": composition_quality,
        "avg_compatibility": round(composition_quality / 100, 4),
        "composition_label": (
            f"{dominant_material} {material_match_count}/{batch_size} · "
            f"{dominant_color} {color_match_count}/{batch_size}"
            if batch_size
            else "empty"
        ),
    }


def _c_pack_series(
    equipment_id: str,
    decision_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    series: List[Dict[str, Any]] = []
    env = _stage_env("C")
    for index, event in enumerate(getattr(env, "event_log", []) or []):
        if str(event.get("event_type", "")) != "pack_completed":
            continue
        if str(event.get("machine_id", "")) != equipment_id:
            continue
        task_uids = [int(uid) for uid in event.get("task_uids", [])]
        rows = _task_rows_for_uids(decision_state, task_uids)
        metrics = _c_composition_metrics(rows)
        quality = round(float(event.get("pack_quality", metrics["composition_quality"])), 4)
        avg_compatibility = round(float(event.get("avg_compat", metrics["avg_compatibility"])), 4)
        avg_wait_time = round(float(event.get("avg_wait_time", 0.0) or 0.0), 4)
        point = {
            "point_id": f"{equipment_id}-pack-{event.get('pack_id', index)}",
            "time": int(event.get("timestamp", event.get("end_time", 0)) or 0),
            "step": int(event.get("timestamp", event.get("end_time", 0)) or 0),
            "stage": "C",
            "equipment_id": equipment_id,
            "pack_id": event.get("pack_id", index),
            "task_uids": task_uids,
            "task_codes": [_task_code(uid) for uid in task_uids],
            "quality": quality,
            "quality_values": [quality],
            "composition_quality": quality,
            "avg_compatibility": avg_compatibility,
            "avg_wait_time": avg_wait_time,
            "material_counts": dict(event.get("material_counts") or metrics["material_counts"]),
            "color_counts": dict(event.get("color_counts") or metrics["color_counts"]),
            "material_match_count": int(
                event.get("material_match_count", metrics["material_match_count"]) or 0
            ),
            "color_match_count": int(
                event.get("color_match_count", metrics["color_match_count"]) or 0
            ),
            "dominant_material": event.get("dominant_material", metrics["dominant_material"]),
            "dominant_color": event.get("dominant_color", metrics["dominant_color"]),
            "composition_label": metrics["composition_label"],
            "reason": event.get("reason", "pack_completed"),
            "target_window": [0.0, 100.0],
            "passed": quality >= 50.0,
            "event_type": "pack_completed",
        }
        series.append(point)
    return sorted(series, key=lambda point: (point["time"], point["point_id"]))


def _c_pack_kpis(
    series: List[Dict[str, Any]],
    machine_state: Dict[str, Any],
) -> Dict[str, Any]:
    packed_tasks = sum(len(point.get("task_uids", [])) for point in series)
    qualities = [float(point.get("composition_quality", 0.0) or 0.0) for point in series]
    compatibilities = [float(point.get("avg_compatibility", 0.0) or 0.0) for point in series]
    material_mix = Counter()
    color_mix = Counter()
    for point in series:
        material_mix.update(point.get("material_counts", {}))
        color_mix.update(point.get("color_counts", {}))
    return {
        "packs_completed": len(series),
        "packed_tasks": packed_tasks,
        "avg_quality": round(sum(qualities) / len(qualities), 3) if qualities else None,
        "latest_quality": qualities[-1] if qualities else None,
        "avg_compatibility": (
            round(sum(compatibilities) / len(compatibilities), 4)
            if compatibilities
            else 0.0
        ),
        "active_wip": len(machine_state.get("current_batch_uids", []) or []),
        "sample_count": packed_tasks,
        "material_mix": dict(sorted(material_mix.items())),
        "color_mix": dict(sorted(color_mix.items())),
        "yield_rate": 1.0,
        "processed": packed_tasks,
        "passed": packed_tasks,
        "failed": 0,
    }


def _c_current_pack(
    decision_state: Dict[str, Any],
    machine_state: Dict[str, Any],
) -> Dict[str, Any]:
    task_uids = [int(uid) for uid in machine_state.get("current_batch_uids", []) or []]
    rows = _task_rows_for_uids(decision_state, task_uids)
    metrics = _c_composition_metrics(rows)
    return {
        "task_uids": task_uids,
        "task_codes": [_task_code(uid) for uid in task_uids],
        **metrics,
    }


def _quality_kpis(series: List[Dict[str, Any]], machine_state: Dict[str, Any]) -> Dict[str, Any]:
    processed = sum(len(point.get("task_uids", [])) for point in series)
    passed = sum(int(point.get("pass_count", 0) or 0) for point in series)
    failed = sum(int(point.get("fail_count", 0) or 0) for point in series)
    samples = [
        float(value)
        for point in series
        for value in point.get("quality_values", [])
    ]
    avg_quality = round(sum(samples) / len(samples), 3) if samples else None
    latest_quality = series[-1]["quality"] if series else None
    yield_rate = round(passed / processed, 4) if processed else 1.0
    return {
        "processed": processed,
        "passed": passed,
        "failed": failed,
        "yield_rate": yield_rate,
        "avg_quality": avg_quality,
        "latest_quality": latest_quality,
        "active_wip": len(machine_state.get("current_batch_uids", []) or []),
        "sample_count": len(samples),
    }


def _equipment_detail(equipment_id: str) -> Dict[str, Any]:
    canonical_id = _canonical_equipment_id(equipment_id)
    stage = _stage_from_equipment_id(canonical_id)

    decision_state = context.env.get_decision_state()
    machine_state = decision_state.get(stage, {}).get("machines", {}).get(canonical_id)
    if machine_state is None:
        raise HTTPException(status_code=404, detail=f"unknown equipment: {equipment_id}")

    if stage == "C":
        pack_series = _c_pack_series(canonical_id, decision_state)
        current_pack = _c_current_pack(decision_state, machine_state)
        return {
            "time": decision_state.get("time", 0),
            "equipment_id": canonical_id,
            "stage": stage,
            "process_label": "Packing / Material Compatibility",
            "status": str(machine_state.get("status", "UNKNOWN")).upper(),
            "batch_size": machine_state.get("batch_size"),
            "current_batch_uids": list(machine_state.get("current_batch_uids", [])),
            "finish_time": machine_state.get("finish_time"),
            "material_state": {
                "primary_key": "material_match",
                "primary_label": "Material match",
                "primary_value": current_pack["material_match_count"],
                "secondary_key": "color_match",
                "secondary_label": "Color match",
                "secondary_value": current_pack["color_match_count"],
                "state_label": current_pack["composition_label"],
            },
            "apc": {
                "goal": "Pack wafers with matching material and color composition",
                "quality_axis": {"x": "pack", "y": "composition_quality"},
                "aggregation": "dominant material count and dominant color count over batch size",
                "recipe_parameters": ["material_type", "color"],
            },
            "kpis": _c_pack_kpis(pack_series, machine_state),
            "pack_series": pack_series,
            "quality_series": pack_series,
            "current_pack": current_pack,
            "recent_assignments": [],
        }

    series = _machine_quality_series(stage, canonical_id)
    process_label = {
        "A": "Machining APC / Process QA",
        "B": "Cleaning APC / Clean QA",
    }[stage]
    recipe_parameters = {
        "A": ["pressure", "speed", "dwell"],
        "B": ["clean", "rinse", "dry"],
    }[stage]
    return {
        "time": decision_state.get("time", 0),
        "equipment_id": canonical_id,
        "stage": stage,
        "process_label": process_label,
        "status": str(machine_state.get("status", "UNKNOWN")).upper(),
        "batch_size": machine_state.get("batch_size"),
        "current_batch_uids": list(machine_state.get("current_batch_uids", [])),
        "finish_time": machine_state.get("finish_time"),
        "material_state": _machine_material_state(stage, machine_state),
        "apc": {
            "goal": "Control recipe settings toward the product quality window",
            "quality_axis": {"x": "step", "y": "quality_value"},
            "aggregation": "batch average when multiple samples finish together",
            "recipe_parameters": recipe_parameters,
        },
        "kpis": _quality_kpis(series, machine_state),
        "quality_series": series,
        "recent_assignments": _machine_recent_assignments(stage, canonical_id),
    }


def _stage_process_time(stage: str) -> int:
    key = f"process_time_{stage}"
    try:
        duration = int(context.env.config.get(key, 1))
    except (TypeError, ValueError):
        duration = 1
    return max(1, duration)


def _flow_summary(decision_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    labels = {
        "A": "Process QA",
        "B": "Clean QA",
        "C": "Packing",
    }
    summaries = []
    for stage in STAGES:
        stage_summary = _stage_summary(stage, decision_state)
        equipment_count = len(stage_summary["machines"])
        running = int(stage_summary["running"])
        stats = getattr(_stage_env(stage), "stats", {})
        summaries.append(
            {
                "stage": stage,
                "label": labels[stage],
                "equipment_count": equipment_count,
                "running": running,
                "idle": int(stage_summary["idle"]),
                "utilization": running / equipment_count if equipment_count else 0.0,
                "wip": int(stage_summary["total_wip"]),
                "wait": int(stage_summary["wait"]),
                "incoming": int(stage_summary["incoming"]),
                "rework": int(stage_summary["rework"]),
                "processed": int(stats.get("total_processed", 0)),
                "passed": int(stats.get("total_passed", 0)),
                "reworked": int(stats.get("total_reworked", 0)),
                "completed": int(stats.get("total_tasks_packed", 0))
                if stage == "C"
                else int(stats.get("total_passed", 0)),
                "status": stage_summary["status"],
                "focus": bool(stage_summary["focus"]),
            }
        )
    return summaries


def _bar_status(start: int, end: int, now: int) -> str:
    if now >= end:
        return "completed"
    if start <= now < end:
        return "active"
    return "planned"


def _task_code(uid: Any) -> str:
    try:
        return f"T{int(uid)}"
    except (TypeError, ValueError):
        return f"T{uid}"


def _task_label(task_uids: List[int], max_items: int = 3) -> str:
    if not task_uids:
        return "-"
    shown = [_task_code(uid) for uid in task_uids[:max_items]]
    if len(task_uids) > max_items:
        shown.append(f"+{len(task_uids) - max_items}")
    return ",".join(shown)


def _stacked_task_bars(
    *,
    stage: str,
    machine_id: str,
    task_uids: List[int],
    start: int,
    end: int,
    status: str,
    event_type: str,
    task_type: str,
    source: str,
    bar_id_prefix: str,
    label_prefix: str = "",
    batch_id: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Build one visual sub-bar per task so batch work is readable."""
    if not task_uids:
        task_uids = []
    stack_size = max(1, len(task_uids))
    rows = []
    iterable = task_uids or [None]
    for stack_index, uid in enumerate(iterable):
        visible_uids = [int(uid)] if uid is not None else []
        task_text = _task_label(visible_uids)
        label = f"{label_prefix} {task_text}".strip() if label_prefix else task_text
        rows.append(
            {
                "bar_id": f"{bar_id_prefix}-{uid if uid is not None else stack_index}",
                "stage": stage,
                "machine_id": machine_id,
                "row_id": f"{stage}:{machine_id}",
                "task_uids": visible_uids,
                "batch_task_uids": task_uids,
                "batch_id": batch_id,
                "start": start,
                "end": end,
                "duration": end - start,
                "status": status,
                "event_type": event_type,
                "task_type": task_type,
                "label": label,
                "source": source,
                "stack_index": stack_index,
                "stack_size": stack_size,
            }
        )
    return rows


def _event_to_gantt_bars(stage: str, now: int) -> List[Dict[str, Any]]:
    bars: List[Dict[str, Any]] = []
    started_pack_ids = {
        event.get("pack_id")
        for event in getattr(_stage_env(stage), "event_log", []) or []
        if str(event.get("event_type", "")) == "pack_started"
    }
    for index, event in enumerate(getattr(_stage_env(stage), "event_log", []) or []):
        event_type = str(event.get("event_type", ""))
        if event_type == "task_assigned":
            start = int(event.get("start_time", event.get("timestamp", 0)) or 0)
            end = int(event.get("end_time", start + _stage_process_time(stage)) or start)
            end = max(start + 1, end)
            machine_id = str(event.get("machine_id", f"{stage}_0"))
            task_uids = [int(uid) for uid in event.get("task_uids", [])]
            task_type = str(event.get("task_type", "new"))
            status = _bar_status(start, end, now)
            if task_type == "rework":
                status = "rework_active" if status == "active" else "rework"
            bars.append(
                {
                    "bar_id": f"{stage}-{machine_id}-{start}-{index}",
                    "stage": stage,
                    "machine_id": machine_id,
                    "row_id": f"{stage}:{machine_id}",
                    "task_uids": task_uids,
                    "start": start,
                    "end": end,
                    "duration": end - start,
                    "status": status,
                    "event_type": event_type,
                    "task_type": task_type,
                    "label": _task_label(task_uids),
                    "source": "event_log",
                    "stack_index": 0,
                    "stack_size": 1,
                }
            )
        elif event_type in {"pack_started", "pack_completed"}:
            if event_type == "pack_completed" and event.get("pack_id") in started_pack_ids:
                continue
            start = int(event.get("start_time", event.get("timestamp", 0)) or 0)
            raw_end = int(event.get("end_time", start) or start)
            end = max(start + _stage_process_time("C"), raw_end)
            machine_id = str(event.get("machine_id", "C_0"))
            task_uids = [int(uid) for uid in event.get("task_uids", [])]
            pack_id = event.get("pack_id", index)
            status = _bar_status(start, end, now)
            bars.extend(
                _stacked_task_bars(
                    stage=stage,
                    machine_id=machine_id,
                    task_uids=task_uids,
                    start=start,
                    end=end,
                    status=status,
                    event_type=event_type,
                    task_type="pack",
                    source="event_log",
                    bar_id_prefix=f"{stage}-{machine_id}-pack-{pack_id}",
                    label_prefix=f"P{pack_id}",
                    batch_id=pack_id,
                )
            )
    return bars


def _planned_gantt_bars(decision_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    now = int(decision_state.get("time", 0) or 0)
    bars: List[Dict[str, Any]] = []
    for stage in STAGES:
        for index, candidate in enumerate(
            context.harness.service.dispatch_candidates(decision_state, stage=stage)
        ):
            machine_id = str(candidate.get("equipment_id", f"{stage}_{index}"))
            task_uids = [int(uid) for uid in candidate.get("task_uids", [])]
            end = now + _stage_process_time(stage)
            task_type = str(candidate.get("task_type", "new"))
            bars.extend(
                _stacked_task_bars(
                    stage=stage,
                    machine_id=machine_id,
                    task_uids=task_uids,
                    start=now,
                    end=end,
                    status="planned_rework" if task_type == "rework" else "planned",
                    event_type="next_dispatch_candidate",
                    task_type=task_type,
                    source="dispatch_candidate",
                    bar_id_prefix=f"planned-{stage}-{machine_id}-{index}",
                    label_prefix="Next",
                )
            )
    return bars


def _gantt_rows(decision_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for stage in STAGES:
        machines = decision_state.get(stage, {}).get("machines", {})
        for equipment_id in sorted(machines):
            rows.append(
                {
                    "row_id": f"{stage}:{equipment_id}",
                    "stage": stage,
                    "machine_id": str(equipment_id),
                    "label": str(equipment_id),
                    "display_stage": stage,
                    "row_type": "equipment",
                }
            )
    return rows


def _gantt_horizon(
    now: int,
    lookback: int = 36,
    lookahead: int = 12,
) -> Dict[str, Any]:
    lookback = max(6, min(240, int(lookback)))
    lookahead = max(4, min(120, int(lookahead)))
    start = max(0, now - lookback)
    end = max(now + lookahead, start + 12)
    span = max(1, end - start)
    target_ticks = 10
    step = max(1, round(span / target_ticks))
    ticks = list(range(start, end + 1, step))
    if ticks[-1] != end:
        ticks.append(end)
    return {
        "start": start,
        "end": end,
        "span": span,
        "ticks": ticks,
        "lookback": lookback,
        "lookahead": lookahead,
    }


def _filter_bars_for_horizon(
    bars: List[Dict[str, Any]],
    horizon: Dict[str, Any],
) -> List[Dict[str, Any]]:
    start = int(horizon["start"])
    end = int(horizon["end"])
    return [
        bar
        for bar in bars
        if int(bar["end"]) >= start and int(bar["start"]) <= end
    ]


def _stage_gantt_view(
    stage: str,
    rows: List[Dict[str, Any]],
    bars: List[Dict[str, Any]],
) -> Dict[str, Any]:
    stage_rows = [row for row in rows if row["stage"] == stage]
    stage_bars = [bar for bar in bars if bar["stage"] == stage]
    by_machine: Dict[str, List[Dict[str, Any]]] = {}
    for bar in stage_bars:
        by_machine.setdefault(bar["machine_id"], []).append(bar)
    for items in by_machine.values():
        items.sort(key=lambda item: (item["start"], item["end"], item["bar_id"]))
    return {
        "stage": stage,
        "rows": stage_rows,
        "bars": stage_bars,
        "machine_schedule": by_machine,
        "bar_count": len(stage_bars),
    }


def _gantt_state(lookback: int = 36, lookahead: int = 12) -> Dict[str, Any]:
    decision_state = context.env.get_decision_state()
    now = int(decision_state.get("time", 0) or 0)
    bars: List[Dict[str, Any]] = []
    for stage in STAGES:
        bars.extend(_event_to_gantt_bars(stage, now))
    bars.extend(_planned_gantt_bars(decision_state))
    rows = _gantt_rows(decision_state)
    horizon = _gantt_horizon(now, lookback=lookback, lookahead=lookahead)
    visible_bars = _filter_bars_for_horizon(bars, horizon)
    return {
        "time": now,
        "horizon": horizon,
        "flow": _flow_summary(decision_state),
        "rows": rows,
        "bars": sorted(
            visible_bars,
            key=lambda bar: (bar["stage"], bar["machine_id"], bar["start"], bar["end"]),
        ),
        "total_bar_count": len(bars),
        "visible_bar_count": len(visible_bars),
        "stage_views": {
            stage: _stage_gantt_view(stage, rows, visible_bars)
            for stage in STAGES
        },
        "legend": {
            "active": "Running now",
            "completed": "Finished",
            "planned": "Next eligible dispatch",
            "rework": "Rework processing",
        },
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
    items = context.harness.store.equipment()
    return {
        "time": mes_state.get("time", 0),
        "count": len(items),
        "items": [item.to_dict() for item in items],
    }


@app.get("/api/v1/lots")
def get_lots() -> Dict[str, Any]:
    mes_state = _mes_state()
    items = context.harness.store.lots()
    return {
        "time": mes_state.get("time", 0),
        "count": len(items),
        "items": [item.to_dict() for item in items],
    }


@app.get("/api/v1/wafers")
def get_wafers(lot_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    mes_state = _mes_state()
    items = context.harness.store.wafers(lot_id)
    return {
        "time": mes_state.get("time", 0),
        "lot_id": lot_id,
        "count": len(items),
        "items": [item.to_dict() for item in items],
    }


@app.get("/api/v1/recipes")
def get_recipes(operation_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    mes_state = _mes_state()
    items = context.harness.store.recipes(operation_id)
    return {
        "time": mes_state.get("time", 0),
        "operation_id": operation_id,
        "count": len(items),
        "items": [item.to_dict() for item in items],
    }


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


@app.get("/api/v2/equipment/{equipment_id}/detail")
def equipment_detail(equipment_id: str) -> Dict[str, Any]:
    return _equipment_detail(equipment_id)


@app.get("/api/v2/gantt")
def gantt(
    lookback: int = Query(36, ge=6, le=240),
    lookahead: int = Query(12, ge=4, le=120),
) -> Dict[str, Any]:
    return _gantt_state(lookback=lookback, lookahead=lookahead)


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
