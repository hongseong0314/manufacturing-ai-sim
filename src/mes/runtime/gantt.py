"""Gantt payload builders for MES control-room views."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.mes.runtime.common import (
    STAGES,
    stage_env,
    stage_process_time,
    task_label,
)
from src.mes.runtime.live_state import stage_summary


def flow_summary(context: Any, decision_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    labels = {
        "A": "Process QA",
        "B": "Clean QA",
        "C": "Packing",
    }
    summaries = []
    for stage in STAGES:
        summary = stage_summary(context, stage, decision_state)
        equipment_count = len(summary["machines"])
        running = int(summary["running"])
        stats = getattr(stage_env(context, stage), "stats", {})
        summaries.append(
            {
                "stage": stage,
                "label": labels[stage],
                "equipment_count": equipment_count,
                "running": running,
                "idle": int(summary["idle"]),
                "utilization": running / equipment_count if equipment_count else 0.0,
                "wip": int(summary["total_wip"]),
                "wait": int(summary["wait"]),
                "incoming": int(summary["incoming"]),
                "rework": int(summary["rework"]),
                "processed": int(stats.get("total_processed", 0)),
                "passed": int(stats.get("total_passed", 0)),
                "reworked": int(stats.get("total_reworked", 0)),
                "completed": int(stats.get("total_tasks_packed", 0))
                if stage == "C"
                else int(stats.get("total_passed", 0)),
                "status": summary["status"],
                "focus": bool(summary["focus"]),
            }
        )
    return summaries


def bar_status(start: int, end: int, now: int) -> str:
    if now >= end:
        return "completed"
    if start <= now < end:
        return "active"
    return "planned"


def stacked_task_bars(
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
        task_text = task_label(visible_uids)
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


def event_to_gantt_bars(context: Any, stage: str, now: int) -> List[Dict[str, Any]]:
    bars: List[Dict[str, Any]] = []
    started_pack_ids = {
        event.get("pack_id")
        for event in getattr(stage_env(context, stage), "event_log", []) or []
        if str(event.get("event_type", "")) == "pack_started"
    }
    for index, event in enumerate(getattr(stage_env(context, stage), "event_log", []) or []):
        event_type = str(event.get("event_type", ""))
        if event_type == "task_assigned":
            start = int(event.get("start_time", event.get("timestamp", 0)) or 0)
            end = int(event.get("end_time", start + stage_process_time(context, stage)) or start)
            end = max(start + 1, end)
            machine_id = str(event.get("machine_id", f"{stage}_0"))
            task_uids = [int(uid) for uid in event.get("task_uids", [])]
            task_type = str(event.get("task_type", "new"))
            status = bar_status(start, end, now)
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
                    "label": task_label(task_uids),
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
            end = max(start + stage_process_time(context, "C"), raw_end)
            machine_id = str(event.get("machine_id", "C_0"))
            task_uids = [int(uid) for uid in event.get("task_uids", [])]
            pack_id = event.get("pack_id", index)
            status = bar_status(start, end, now)
            bars.extend(
                stacked_task_bars(
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


def planned_gantt_bars(context: Any, decision_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    now = int(decision_state.get("time", 0) or 0)
    bars: List[Dict[str, Any]] = []
    for stage in STAGES:
        for index, candidate in enumerate(
            context.harness.service.dispatch_candidates(decision_state, stage=stage)
        ):
            machine_id = str(candidate.get("equipment_id", f"{stage}_{index}"))
            task_uids = [int(uid) for uid in candidate.get("task_uids", [])]
            end = now + stage_process_time(context, stage)
            task_type = str(candidate.get("task_type", "new"))
            bars.extend(
                stacked_task_bars(
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


def gantt_rows(decision_state: Dict[str, Any]) -> List[Dict[str, Any]]:
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


def gantt_horizon(
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


def filter_bars_for_horizon(
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


def attach_assignment_trace_keys(context: Any, bars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach command/correlation/candidate ids to bars when a command matches."""
    trace_rows = []
    for command in reversed(context.harness.store.commands()):
        validated = dict(command.validated_command or {})
        equipment_id = str(validated.get("equipment_id", ""))
        stage = str(validated.get("stage") or equipment_id.split("_", 1)[0]).upper()
        task_uids = {
            int(uid)
            for uid in validated.get("task_uids", [])
            if str(uid).lstrip("-").isdigit()
        }
        if not equipment_id or not task_uids:
            continue
        trace_rows.append(
            {
                "stage": stage,
                "machine_id": equipment_id,
                "task_uids": task_uids,
                "correlation_id": command.correlation_id,
                "command_id": command.command_id,
                "candidate_id": validated.get("candidate_id"),
            }
        )

    if not trace_rows:
        return bars

    enriched = []
    for bar in bars:
        item = dict(bar)
        bar_tasks = {
            int(uid)
            for uid in (bar.get("batch_task_uids") or bar.get("task_uids") or [])
            if str(uid).lstrip("-").isdigit()
        }
        for trace in trace_rows:
            if trace["stage"] != str(bar.get("stage", "")).upper():
                continue
            if trace["machine_id"] != str(bar.get("machine_id", "")):
                continue
            if not bar_tasks or not (bar_tasks & trace["task_uids"]):
                continue
            item.update(
                {
                    "correlation_id": trace["correlation_id"],
                    "command_id": trace["command_id"],
                    "candidate_id": trace["candidate_id"],
                    "traceable": True,
                }
            )
            break
        enriched.append(item)
    return enriched


def stage_gantt_view(
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


def gantt_state(context: Any, lookback: int = 36, lookahead: int = 12) -> Dict[str, Any]:
    decision_state = context.env.get_decision_state()
    now = int(decision_state.get("time", 0) or 0)
    bars: List[Dict[str, Any]] = []
    for stage in STAGES:
        bars.extend(event_to_gantt_bars(context, stage, now))
    bars.extend(planned_gantt_bars(context, decision_state))
    bars = attach_assignment_trace_keys(context, bars)
    rows = gantt_rows(decision_state)
    horizon = gantt_horizon(now, lookback=lookback, lookahead=lookahead)
    visible_bars = filter_bars_for_horizon(bars, horizon)
    return {
        "time": now,
        "horizon": horizon,
        "flow": flow_summary(context, decision_state),
        "rows": rows,
        "bars": sorted(
            visible_bars,
            key=lambda bar: (bar["stage"], bar["machine_id"], bar["start"], bar["end"]),
        ),
        "total_bar_count": len(bars),
        "visible_bar_count": len(visible_bars),
        "stage_views": {
            stage: stage_gantt_view(stage, rows, visible_bars)
            for stage in STAGES
        },
        "legend": {
            "active": "Running now",
            "completed": "Finished",
            "planned": "Next eligible dispatch",
            "rework": "Rework processing",
        },
    }
