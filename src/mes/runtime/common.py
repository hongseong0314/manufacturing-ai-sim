"""Shared runtime formatting and validation helpers."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import HTTPException


STAGES = ("A", "B", "C")
EMPTY_ACTIONS = {"A": {}, "B": {}, "C": {}}


def normalize_target_stage(value: Any, default: str = "AUTO") -> str:
    stage = str(value or default).upper()
    if stage not in {*STAGES, "AUTO"}:
        raise HTTPException(status_code=400, detail=f"unknown target_stage: {value}")
    return stage


def stage_env(context: Any, stage: str) -> Any:
    return {"A": context.env.env_A, "B": context.env.env_B, "C": context.env.env_C}[stage]


def stage_from_equipment_id(equipment_id: str) -> str:
    stage = str(equipment_id or "").split("_", 1)[0].upper()
    if stage not in STAGES:
        raise HTTPException(status_code=404, detail=f"unknown equipment: {equipment_id}")
    return stage


def canonical_equipment_id(equipment_id: str) -> str:
    raw = str(equipment_id or "").strip()
    stage = stage_from_equipment_id(raw)
    suffix = raw.split("_", 1)[1] if "_" in raw else raw[1:]
    return f"{stage}_{suffix}" if suffix else raw.upper()


def stage_process_time(context: Any, stage: str) -> int:
    key = f"process_time_{stage}"
    try:
        duration = int(context.env.config.get(key, 1))
    except (TypeError, ValueError):
        duration = 1
    return max(1, duration)


def task_code(uid: Any) -> str:
    try:
        return f"T{int(uid)}"
    except (TypeError, ValueError):
        return f"T{uid}"


def task_label(task_uids: List[int], max_items: int = 3) -> str:
    if not task_uids:
        return "-"
    shown = [task_code(uid) for uid in task_uids[:max_items]]
    if len(task_uids) > max_items:
        shown.append(f"+{len(task_uids) - max_items}")
    return ",".join(shown)


def task_rows_for_uids(
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
