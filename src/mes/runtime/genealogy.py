"""Digital-twin genealogy and execution ledger payload builders."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.mes.adapters import task_uid_from_wafer_id, wafer_id_from_task_uid
from src.mes.runtime.assignment_trace import assignment_trace


def task_genealogy(context: Any, task_uid: int) -> Dict[str, Any]:
    """Return time-ordered digital-twin lineage for one simulator task."""
    uid = int(task_uid)
    task_row = _latest_task_row(context, uid)
    if task_row is None:
        return _not_found({"task_uid": uid}, "TASK_NOT_FOUND")

    assignments = _assignments_for_task(context, uid)
    timeline = [_task_created_record(uid, task_row)]
    timeline.extend(_event_records_for_task(context, uid))
    timeline.extend(_simulator_records_for_task(context, uid))
    timeline = _dedupe_records(_sort_records(timeline))

    related_correlation_ids = _unique(
        item.get("correlation_id")
        for item in timeline
        if item.get("correlation_id")
    )
    trace = (
        assignment_trace(
            context,
            equipment_id=assignments[0].get("equipment_id"),
            task_uid=uid,
            correlation_id=assignments[0].get("correlation_id"),
            candidate_id=assignments[0].get("candidate_id"),
        )
        if assignments
        else {}
    )
    return {
        "found": True,
        "entity_type": "TASK",
        "task_uid": uid,
        "wafer_id": wafer_id_from_task_uid(uid),
        "lot_id": str(task_row.get("job_id") or ""),
        "current_state": task_row,
        "related_correlation_ids": related_correlation_ids,
        "assignments": assignments,
        "timeline": timeline,
        "assignment_trace": _assignment_trace_summary(trace),
    }


def lot_genealogy(context: Any, lot_id: str) -> Dict[str, Any]:
    """Return lot-level rollout across all simulator task rows in the lot."""
    lot_key = str(lot_id)
    task_rows = _task_rows_for_lot(context, lot_key)
    if not task_rows:
        return _not_found({"lot_id": lot_key}, "LOT_NOT_FOUND")

    task_uids = sorted(int(row.get("uid")) for row in task_rows if row.get("uid") is not None)
    command_ids = _unique(
        command.command_id
        for uid in task_uids
        for command in _commands_for_task(context, uid)
    )
    correlations = _unique(
        command.correlation_id
        for uid in task_uids
        for command in _commands_for_task(context, uid)
    )
    timeline = [_task_created_record(int(row["uid"]), row) for row in task_rows]
    for uid in task_uids:
        timeline.extend(_event_records_for_task(context, uid))
        timeline.extend(_simulator_records_for_task(context, uid))

    return {
        "found": True,
        "entity_type": "LOT",
        "lot_id": lot_key,
        "task_count": len(task_uids),
        "task_uids": task_uids,
        "command_ids": command_ids,
        "related_correlation_ids": correlations,
        "timeline": _dedupe_records(_sort_records(timeline)),
    }


def equipment_genealogy(context: Any, equipment_id: str) -> Dict[str, Any]:
    """Return command and event timeline for one equipment id."""
    tool_id = str(equipment_id)
    commands = _commands_for_equipment(context, tool_id)
    timeline = _event_records_for_equipment(context, tool_id)
    timeline.extend(_simulator_records_for_equipment(context, tool_id))
    equipment = _equipment_snapshot(context, tool_id)
    if not commands and not timeline and not equipment:
        return _not_found({"equipment_id": tool_id}, "EQUIPMENT_NOT_FOUND")

    return {
        "found": True,
        "entity_type": "EQUIPMENT",
        "equipment_id": tool_id,
        "stage": _stage_from_equipment(tool_id),
        "current_state": equipment or {},
        "commands": [_command_summary(command) for command in commands],
        "timeline": _dedupe_records(_sort_records(timeline)),
    }


def execution_ledger(context: Any, correlation_id: str) -> Dict[str, Any]:
    """Return the durable decision-to-execution ledger for one correlation id."""
    corr = str(correlation_id)
    commands = context.harness.store.commands(corr)
    events = context.harness.store.events(corr)
    recommendations = context.harness.store.recommendations(corr)
    validations = context.harness.store.validations(corr)
    if not commands and not events and not recommendations and not validations:
        return _not_found({"correlation_id": corr}, "CORRELATION_NOT_FOUND")

    decision_state = _decision_state_for_correlation(context, corr)
    post_state = _post_state_for_correlation(context, corr) or {}
    records = [_event_record(context, event) for event in events]
    return {
        "found": True,
        "correlation_id": corr,
        "command": commands[-1].to_dict() if commands else {},
        "recommendations": [item.to_dict() for item in recommendations],
        "validations": [item.to_dict() for item in validations],
        "records": _dedupe_records(_sort_records(records)),
        "decision_state": _json_safe_state(decision_state),
        "decision_summary": _state_summary(decision_state),
        "post_state": _json_safe_state(post_state),
        "post_summary": _state_summary(post_state),
        "assignment_trace_url": f"/api/v2/assignment-trace?correlation_id={corr}",
    }


def digital_twin_state_at(context: Any, time: int) -> Dict[str, Any]:
    """Return the best available simulator decision state at or before time."""
    requested = int(time)
    selected = _state_at_or_before(context, requested)
    if selected is None:
        return _not_found({"time": requested}, "NO_STATE_SNAPSHOT")
    source, state = selected
    return {
        "found": True,
        "requested_time": requested,
        "source": source,
        "state": _json_safe_state(state),
        "summary": _state_summary(state),
    }


def _assignments_for_task(context: Any, task_uid: int) -> List[Dict[str, Any]]:
    assignments = []
    for command in _commands_for_task(context, task_uid):
        validated = dict(command.validated_command or {})
        corr = command.correlation_id
        decision_state = _decision_state_for_correlation(context, corr)
        assignments.append(
            {
                "command_id": command.command_id,
                "correlation_id": corr,
                "candidate_id": validated.get("candidate_id"),
                "stage": str(validated.get("stage") or _stage_from_equipment(validated.get("equipment_id")) or ""),
                "equipment_id": validated.get("equipment_id"),
                "task_uids": [int(uid) for uid in validated.get("task_uids", [])],
                "recipe_id": validated.get("recipe_id"),
                "recipe": validated.get("recipe"),
                "start": int((decision_state or {}).get("time", 0) or 0),
                "status": command.status,
                "trace_url": f"/api/v2/assignment-trace?correlation_id={corr}",
            }
        )
    return assignments


def _commands_for_task(context: Any, task_uid: int) -> List[Any]:
    commands = []
    for command in reversed(context.harness.store.commands()):
        validated = dict(command.validated_command or {})
        task_uids = {int(uid) for uid in validated.get("task_uids", [])}
        if int(task_uid) in task_uids:
            commands.append(command)
    return commands


def _commands_for_equipment(context: Any, equipment_id: str) -> List[Any]:
    return [
        command
        for command in context.harness.store.commands()
        if str((command.validated_command or {}).get("equipment_id")) == str(equipment_id)
    ]


def _command_summary(command: Any) -> Dict[str, Any]:
    validated = dict(command.validated_command or {})
    return {
        "command_id": command.command_id,
        "correlation_id": command.correlation_id,
        "status": command.status,
        "validation_status": command.validation_status,
        "stage": validated.get("stage") or _stage_from_equipment(validated.get("equipment_id")),
        "equipment_id": validated.get("equipment_id"),
        "task_uids": [int(uid) for uid in validated.get("task_uids", [])],
        "candidate_id": validated.get("candidate_id"),
    }


def _event_records_for_task(context: Any, task_uid: int) -> List[Dict[str, Any]]:
    wafer_id = wafer_id_from_task_uid(task_uid)
    records = []
    for event in context.harness.store.events():
        event_task_uids = _task_uids_from_event(event)
        if int(task_uid) in event_task_uids or wafer_id in set(event.wafer_ids or []):
            records.append(_event_record(context, event))
    return records


def _event_records_for_equipment(context: Any, equipment_id: str) -> List[Dict[str, Any]]:
    return [
        _event_record(context, event)
        for event in context.harness.store.events()
        if str(event.equipment_id or "") == str(equipment_id)
    ]


def _event_record(context: Any, event: Any) -> Dict[str, Any]:
    payload = dict(event.payload or {})
    command = dict(payload.get("command") or {})
    validated = dict(command.get("validated_command") or {})
    validation = dict(payload.get("validation") or {})
    if validation and not validated:
        validated = dict(validation.get("validated_command") or {})
    task_uids = _task_uids_from_event(event)
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "time": _event_time(context, event),
        "correlation_id": event.correlation_id,
        "actor_type": event.actor_type,
        "layer_id": event.layer_id,
        "recommendation_id": event.recommendation_id,
        "command_id": command.get("command_id") or payload.get("command_id"),
        "equipment_id": event.equipment_id or validated.get("equipment_id"),
        "operation_id": event.operation_id or validated.get("stage"),
        "recipe_id": event.recipe_id or validated.get("recipe_id"),
        "wafer_ids": list(event.wafer_ids or []),
        "task_uids": task_uids,
        "payload": payload,
    }


def _simulator_records_for_task(context: Any, task_uid: int) -> List[Dict[str, Any]]:
    return [
        record
        for record in _simulator_records(context)
        if int(task_uid) in {int(uid) for uid in record.get("task_uids", [])}
    ]


def _simulator_records_for_equipment(context: Any, equipment_id: str) -> List[Dict[str, Any]]:
    return [
        record
        for record in _simulator_records(context)
        if str(record.get("equipment_id")) == str(equipment_id)
    ]


def _simulator_records(context: Any) -> List[Dict[str, Any]]:
    env = context.env
    records = []
    for stage, stage_env in (
        ("A", getattr(env, "env_A", None)),
        ("B", getattr(env, "env_B", None)),
        ("C", getattr(env, "env_C", None)),
    ):
        for index, event in enumerate(getattr(stage_env, "event_log", []) or []):
            if not isinstance(event, dict):
                continue
            records.append(_simulator_record(stage, index, event))
    return records


def _simulator_record(stage: str, index: int, event: Dict[str, Any]) -> Dict[str, Any]:
    event_type = str(event.get("event_type") or "").lower()
    mapped_type = {
        "task_assigned": "EQUIPMENT_STARTED",
        "pack_started": "EQUIPMENT_STARTED",
        "task_completed": "EQUIPMENT_FINISHED",
        "pack_completed": "EQUIPMENT_FINISHED",
    }.get(event_type, event_type.upper() or "SIMULATOR_EVENT")
    task_uids = [int(uid) for uid in event.get("task_uids", [])]
    return {
        "event_id": f"SIM_{stage}_{index}",
        "event_type": mapped_type,
        "simulator_event_type": event.get("event_type"),
        "time": int(event.get("timestamp", event.get("start_time", 0)) or 0),
        "correlation_id": "",
        "actor_type": "SIMULATOR",
        "layer_id": None,
        "recommendation_id": None,
        "command_id": None,
        "equipment_id": event.get("machine_id"),
        "operation_id": stage,
        "recipe_id": None,
        "wafer_ids": [wafer_id_from_task_uid(uid) for uid in task_uids],
        "task_uids": task_uids,
        "payload": dict(event),
    }


def _task_created_record(task_uid: int, task_row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "event_id": f"TASK_CREATED_{task_uid}",
        "event_type": "TASK_CREATED",
        "time": int(task_row.get("arrival_time", 0) or 0),
        "correlation_id": "",
        "actor_type": "SIMULATOR",
        "layer_id": None,
        "recommendation_id": None,
        "command_id": None,
        "equipment_id": None,
        "operation_id": task_row.get("location") or "A",
        "recipe_id": None,
        "lot_id": task_row.get("job_id"),
        "wafer_ids": [wafer_id_from_task_uid(task_uid)],
        "task_uids": [task_uid],
        "payload": dict(task_row),
    }


def _task_uids_from_event(event: Any) -> List[int]:
    payload = dict(event.payload or {})
    candidates: List[Any] = []
    candidates.extend(payload.get("task_uids", []) if isinstance(payload.get("task_uids"), list) else [])
    command = dict(payload.get("command") or {})
    validated = dict(command.get("validated_command") or {})
    candidates.extend(validated.get("task_uids", []) if isinstance(validated.get("task_uids"), list) else [])
    validation = dict(payload.get("validation") or {})
    validation_command = dict(validation.get("validated_command") or {})
    candidates.extend(
        validation_command.get("task_uids", [])
        if isinstance(validation_command.get("task_uids"), list)
        else []
    )
    recommended = dict(payload.get("recommended_action") or {})
    candidates.extend(
        recommended.get("task_uids", [])
        if isinstance(recommended.get("task_uids"), list)
        else []
    )
    for wafer_id in event.wafer_ids or []:
        uid = task_uid_from_wafer_id(wafer_id)
        if uid is not None:
            candidates.append(uid)
    return sorted({int(uid) for uid in candidates if str(uid).isdigit()})


def _event_time(context: Any, event: Any) -> int:
    payload = dict(event.payload or {})
    if payload.get("post_time") is not None:
        return int(payload.get("post_time") or 0)
    command = dict(payload.get("command") or {})
    validated = dict(command.get("validated_command") or {})
    if validated.get("start_time") is not None:
        return int(validated.get("start_time") or 0)
    decision_state = _decision_state_for_correlation(context, event.correlation_id)
    return int((decision_state or {}).get("time", 0) or 0)


def _decision_state_for_correlation(context: Any, correlation_id: str) -> Dict[str, Any]:
    snapshots = context.harness.store.feature_snapshots(correlation_id)
    for preferred_layer in ("L4", "PORTFOLIO", "L3", "L1", "L2"):
        for snapshot in snapshots:
            if snapshot.layer_id == preferred_layer:
                return dict(snapshot.decision_state or {})
    if snapshots:
        return dict(snapshots[0].decision_state or {})
    return {}


def _post_state_for_correlation(context: Any, correlation_id: str) -> Dict[str, Any]:
    for event in reversed(context.harness.store.events(correlation_id)):
        payload = dict(event.payload or {})
        state = payload.get("post_decision_state")
        if isinstance(state, dict) and state:
            return dict(state)
    return {}


def _state_at_or_before(context: Any, requested: int) -> Optional[Tuple[str, Dict[str, Any]]]:
    snapshots = _state_snapshots(context)
    eligible = [
        (source, state)
        for source, state in snapshots
        if int(state.get("time", 0) or 0) <= requested
    ]
    if eligible:
        return eligible[-1]
    return snapshots[0] if snapshots else None


def _state_snapshots(context: Any) -> List[Tuple[str, Dict[str, Any]]]:
    snapshots: List[Tuple[str, Dict[str, Any]]] = []
    for snapshot in context.harness.store.feature_snapshots():
        state = dict(snapshot.decision_state or {})
        if state:
            snapshots.append((f"feature_snapshot:{snapshot.feature_snapshot_id}", state))
    for event in context.harness.store.events():
        payload = dict(event.payload or {})
        state = payload.get("post_decision_state")
        if isinstance(state, dict) and state:
            snapshots.append((f"event:{event.event_id}", dict(state)))
    current = context.env.get_decision_state()
    if current:
        snapshots.append(("current_runtime", dict(current)))
    snapshots.sort(key=lambda item: int(item[1].get("time", 0) or 0))
    return snapshots


def _latest_task_row(context: Any, task_uid: int) -> Optional[Dict[str, Any]]:
    for _source, state in reversed(_state_snapshots(context)):
        row = _task_row_from_state(state, task_uid)
        if row is not None:
            return row
    return None


def _task_rows_for_lot(context: Any, lot_id: str) -> List[Dict[str, Any]]:
    rows: Dict[int, Dict[str, Any]] = {}
    for _source, state in _state_snapshots(context):
        for row in (state.get("tasks", {}) or {}).values():
            if isinstance(row, dict) and str(row.get("job_id")) == lot_id:
                uid = row.get("uid")
                if uid is not None:
                    rows[int(uid)] = dict(row)
    return [rows[uid] for uid in sorted(rows)]


def _task_row_from_state(state: Dict[str, Any], task_uid: int) -> Optional[Dict[str, Any]]:
    tasks = state.get("tasks", {}) or {}
    row = tasks.get(int(task_uid))
    if row is None:
        row = tasks.get(str(task_uid))
    return dict(row) if isinstance(row, dict) else None


def _equipment_snapshot(context: Any, equipment_id: str) -> Dict[str, Any]:
    state = context.env.get_decision_state()
    stage = _stage_from_equipment(equipment_id)
    if not stage:
        return {}
    machine = (
        state.get(stage, {})
        .get("machines", {})
        .get(str(equipment_id), {})
    )
    if not isinstance(machine, dict):
        return {}
    item = dict(machine)
    item["equipment_id"] = equipment_id
    item["stage"] = stage
    return item


def _state_summary(decision_state: Dict[str, Any]) -> Dict[str, Any]:
    stages = {}
    for stage in ("A", "B", "C"):
        stage_state = decision_state.get(stage, {}) or {}
        incoming_key = "incoming_from_A_uids" if stage == "B" else "incoming_from_B_uids"
        stages[stage] = {
            "wait": len(stage_state.get("wait_pool_uids", []) or []),
            "incoming": len(stage_state.get(incoming_key, []) or []) if stage != "A" else 0,
            "rework": len(stage_state.get("rework_pool_uids", []) or []),
            "machines": len(stage_state.get("machines", {}) or {}),
        }
    return {
        "time": decision_state.get("time", 0),
        "stages": stages,
        "num_completed": decision_state.get("num_completed", 0),
    }


def _assignment_trace_summary(trace: Dict[str, Any]) -> Dict[str, Any]:
    if not trace or not trace.get("found"):
        return {}
    assignment = dict(trace.get("assignment") or {})
    return {
        "found": True,
        "correlation_id": assignment.get("correlation_id"),
        "command_id": assignment.get("command_id"),
        "candidate_id": assignment.get("candidate_id"),
        "equipment_id": assignment.get("equipment_id"),
        "task_uids": assignment.get("task_uids", []),
        "url": f"/api/v2/assignment-trace?correlation_id={assignment.get('correlation_id')}",
    }


def _stage_from_equipment(equipment_id: Optional[str]) -> str:
    if not equipment_id:
        return ""
    first = str(equipment_id)[0].upper()
    return first if first in {"A", "B", "C"} else ""


def _sort_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        records,
        key=lambda item: (
            int(item.get("time", 0) or 0),
            _event_priority(str(item.get("event_type", ""))),
            str(item.get("event_id", "")),
        ),
    )


def _event_priority(event_type: str) -> int:
    event = event_type.upper()
    order = {
        "TASK_CREATED": 0,
        "OBJECTIVE_SELECTED": 10,
        "STAGE_PRIORITY_UPDATED": 20,
        "DISPATCH_RECOMMENDED": 30,
        "PACK_RECOMMENDED": 30,
        "RECIPE_RECOMMENDED": 40,
        "RULE_VALIDATION_PASSED": 50,
        "RULE_VALIDATION_REJECTED": 50,
        "COMMAND_CREATED": 60,
        "EQUIPMENT_STARTED": 70,
        "COMMAND_EXECUTED": 80,
        "SIMULATOR_ACTION_APPLIED": 90,
        "EQUIPMENT_FINISHED": 100,
    }
    return order.get(event, 500)


def _dedupe_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for record in records:
        key = (
            record.get("event_id"),
            record.get("event_type"),
            tuple(record.get("task_uids", []) or []),
            record.get("equipment_id"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _unique(values: Iterable[Any]) -> List[Any]:
    result = []
    seen = set()
    for value in values:
        if value in (None, "") or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _json_safe_state(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe_state(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_state(item) for item in value]
    return value


def _not_found(lookup: Dict[str, Any], reason: str) -> Dict[str, Any]:
    return {
        "found": False,
        "reason": reason,
        "lookup": lookup,
    }
