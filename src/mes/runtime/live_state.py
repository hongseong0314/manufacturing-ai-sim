"""Live fab state and KPI payload builders."""

from __future__ import annotations

from typing import Any, Dict

from src.mes.runtime.common import STAGES
from src.mes.runtime.decision_trace import decision_chain, latest_correlation_id


def mes_state(context: Any) -> Dict[str, Any]:
    state = context.harness.service.decision_state_to_mes(
        context.env.get_decision_state()
    )
    context.harness.store.sync_runtime_state(state)
    return state


def stage_summary(context: Any, stage: str, decision_state: Dict[str, Any]) -> Dict[str, Any]:
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


def fab_kpis(context: Any) -> Dict[str, Any]:
    decision_state = context.env.get_decision_state()
    current_mes_state = context.harness.service.decision_state_to_mes(decision_state)
    wip = current_mes_state.get("wip", {})
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


def live_fab_state(context: Any) -> Dict[str, Any]:
    decision_state = context.env.get_decision_state()
    mes_state(context)
    stages = {
        stage: stage_summary(context, stage, decision_state)
        for stage in STAGES
    }
    equipment = [
        machine
        for stage in STAGES
        for machine in stages[stage]["machines"]
    ]
    correlation_id = latest_correlation_id(context)
    recent_events = context.harness.store.events()[-18:]
    return {
        "time": decision_state.get("time", 0),
        "autoplay": {
            "enabled": context.autoplay_enabled,
            "target_stage": context.autoplay_target_stage,
            "generate_every": context.autoplay_generate_every,
        },
        "kpis": fab_kpis(context),
        "stages": stages,
        "equipment": equipment,
        "active_chain": decision_chain(context, correlation_id),
        "recent_events": [event.to_dict() for event in recent_events],
        "last_cycle": context.last_cycle,
    }
