"""Equipment detail payloads for A/B APC and C packing quality."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from src.mes.runtime.common import (
    canonical_equipment_id,
    stage_env,
    stage_from_equipment_id,
    task_code,
    task_rows_for_uids,
)


def recipe_label(stage: str, recipe: List[Any]) -> str:
    names = {
        "A": ("pressure", "speed", "dwell"),
        "B": ("clean", "rinse", "dry"),
    }.get(stage, tuple(f"p{i + 1}" for i in range(len(recipe))))
    return ", ".join(
        f"{name}={value:g}" if isinstance(value, (int, float)) else f"{name}={value}"
        for name, value in zip(names, recipe)
    )


def target_window(target_specs: List[Dict[str, Any]]) -> Optional[List[float]]:
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


def machine_material_state(stage: str, source: Dict[str, Any]) -> Dict[str, Any]:
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


def machine_quality_series(context: Any, stage: str, equipment_id: str) -> List[Dict[str, Any]]:
    series: List[Dict[str, Any]] = []
    env = stage_env(context, stage)
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
        series.append(
            {
                "point_id": f"{equipment_id}-{event.get('timestamp', 0)}-{index}",
                "time": int(event.get("timestamp", event.get("end_time", 0)) or 0),
                "step": int(event.get("timestamp", event.get("end_time", 0)) or 0),
                "stage": stage,
                "equipment_id": equipment_id,
                "task_uids": task_uids,
                "task_codes": [task_code(uid) for uid in task_uids],
                "quality": quality,
                "quality_values": quality_values,
                "recipe": recipe,
                "recipe_label": recipe_label(stage, recipe),
                "material_state": machine_material_state(stage, event),
                "target_window": target_window(event.get("target_specs", [])),
                "pass_count": int(event.get("pass_count", 0) or 0),
                "fail_count": int(event.get("fail_count", 0) or 0),
                "passed": bool(event.get("passed", False)),
                "event_type": "task_completed",
            }
        )
    return sorted(series, key=lambda point: (point["time"], point["point_id"]))


def machine_recent_assignments(context: Any, stage: str, equipment_id: str) -> List[Dict[str, Any]]:
    env = stage_env(context, stage)
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
                "task_codes": [task_code(uid) for uid in task_uids],
                "task_type": event.get("task_type", "external_action"),
                "recipe": recipe,
                "recipe_label": recipe_label(stage, recipe),
                "material_state": machine_material_state(stage, event),
            }
        )
    return sorted(assignments, key=lambda item: item["time"], reverse=True)[:8]


def _count_values(rows: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    counts = Counter(str(row.get(key, "UNKNOWN")) for row in rows)
    return dict(sorted(counts.items()))


def c_composition_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
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


def c_pack_series(context: Any, equipment_id: str, decision_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    series: List[Dict[str, Any]] = []
    env = stage_env(context, "C")
    for index, event in enumerate(getattr(env, "event_log", []) or []):
        if str(event.get("event_type", "")) != "pack_completed":
            continue
        if str(event.get("machine_id", "")) != equipment_id:
            continue
        task_uids = [int(uid) for uid in event.get("task_uids", [])]
        rows = task_rows_for_uids(decision_state, task_uids)
        metrics = c_composition_metrics(rows)
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
            "task_codes": [task_code(uid) for uid in task_uids],
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


def c_pack_kpis(series: List[Dict[str, Any]], machine_state: Dict[str, Any]) -> Dict[str, Any]:
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


def c_current_pack(decision_state: Dict[str, Any], machine_state: Dict[str, Any]) -> Dict[str, Any]:
    task_uids = [int(uid) for uid in machine_state.get("current_batch_uids", []) or []]
    rows = task_rows_for_uids(decision_state, task_uids)
    metrics = c_composition_metrics(rows)
    return {
        "task_uids": task_uids,
        "task_codes": [task_code(uid) for uid in task_uids],
        **metrics,
    }


def quality_kpis(series: List[Dict[str, Any]], machine_state: Dict[str, Any]) -> Dict[str, Any]:
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


def equipment_detail(context: Any, equipment_id: str) -> Dict[str, Any]:
    canonical_id = canonical_equipment_id(equipment_id)
    stage = stage_from_equipment_id(canonical_id)

    decision_state = context.env.get_decision_state()
    machine_state = decision_state.get(stage, {}).get("machines", {}).get(canonical_id)
    if machine_state is None:
        raise HTTPException(status_code=404, detail=f"unknown equipment: {equipment_id}")

    if stage == "C":
        pack_series = c_pack_series(context, canonical_id, decision_state)
        current_pack = c_current_pack(decision_state, machine_state)
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
            "kpis": c_pack_kpis(pack_series, machine_state),
            "pack_series": pack_series,
            "quality_series": pack_series,
            "current_pack": current_pack,
            "recent_assignments": [],
        }

    series = machine_quality_series(context, stage, canonical_id)
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
        "material_state": machine_material_state(stage, machine_state),
        "apc": {
            "goal": "Control recipe settings toward the product quality window",
            "quality_axis": {"x": "step", "y": "quality_value"},
            "aggregation": "batch average when multiple samples finish together",
            "recipe_parameters": recipe_parameters,
        },
        "kpis": quality_kpis(series, machine_state),
        "quality_series": series,
        "recent_assignments": machine_recent_assignments(context, stage, canonical_id),
    }
