"""Assignment-level trace resolver for MES developer inspection."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.mes.runtime.candidate_portfolio import candidate_portfolio
from src.mes.runtime.common import stage_process_time


def assignment_trace(
    context: Any,
    equipment_id: Optional[str] = None,
    task_uid: Optional[int] = None,
    correlation_id: Optional[str] = None,
    candidate_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve one executed assignment back to its layered MES decision chain."""
    lookup = {
        "equipment_id": equipment_id,
        "task_uid": task_uid,
        "correlation_id": correlation_id,
        "candidate_id": candidate_id,
    }
    command = _find_command(
        context,
        equipment_id=equipment_id,
        task_uid=task_uid,
        correlation_id=correlation_id,
        candidate_id=candidate_id,
    )
    if command is None:
        return _not_found(lookup, "NO_MATCHING_COMMAND")

    corr = command.correlation_id
    recommendations = context.harness.store.recommendations(corr)
    by_layer = {recommendation.layer_id: recommendation for recommendation in recommendations}
    validation = _latest_or_none(context.harness.store.validations(corr))
    portfolio = candidate_portfolio(context, corr)
    decision_state = _decision_state_for_trace(context, corr)
    validated = dict(command.validated_command or {})
    stage = str(validated.get("stage") or _stage_from_equipment(validated.get("equipment_id")) or "").upper()
    task_uids = [int(uid) for uid in validated.get("task_uids", [])]
    start = int((decision_state or {}).get("time", 0) or 0)
    end = start + _process_duration(context, stage)
    assignment = {
        "stage": stage,
        "equipment_id": validated.get("equipment_id"),
        "task_uids": task_uids,
        "task_type": validated.get("task_type"),
        "candidate_id": validated.get("candidate_id"),
        "correlation_id": corr,
        "command_id": command.command_id,
        "start": start,
        "end": end,
    }
    layers = {
        "L4": _recommendation_payload(by_layer.get("L4")),
        "L3": _recommendation_payload(by_layer.get("L3")),
        "L1": _recommendation_payload(by_layer.get("L1")),
        "L2": _recommendation_payload(by_layer.get("L2")),
        "RULE_ENGINE": validation.to_dict() if validation is not None else {},
        "COMMAND": command.to_dict(),
    }
    return {
        "found": True,
        "lookup": lookup,
        "assignment": assignment,
        "decision_state": decision_state or {},
        "state_summary": _state_summary(decision_state or {}),
        "task_snapshots": _task_snapshots(decision_state or {}, task_uids),
        "machine_snapshot": _machine_snapshot(decision_state or {}, stage, validated.get("equipment_id")),
        "layers": layers,
        "candidate_portfolio": portfolio,
        "simulator_action": _simulator_action_for_assignment(command, stage, validated.get("equipment_id")),
        "raw": {
            "recommendations": [recommendation.to_dict() for recommendation in recommendations],
            "validations": [
                item.to_dict() for item in context.harness.store.validations(corr)
            ],
            "commands": [item.to_dict() for item in context.harness.store.commands(corr)],
        },
    }


def _find_command(
    context: Any,
    equipment_id: Optional[str],
    task_uid: Optional[int],
    correlation_id: Optional[str],
    candidate_id: Optional[str],
) -> Optional[Any]:
    commands = list(reversed(context.harness.store.commands(correlation_id)))
    for command in commands:
        validated = dict(command.validated_command or {})
        if candidate_id and str(validated.get("candidate_id")) != str(candidate_id):
            continue
        if equipment_id and str(validated.get("equipment_id")) != str(equipment_id):
            continue
        if task_uid is not None:
            task_uids = {int(uid) for uid in validated.get("task_uids", [])}
            if int(task_uid) not in task_uids:
                continue
        return command
    return None


def _decision_state_for_trace(context: Any, correlation_id: str) -> Dict[str, Any]:
    snapshots = context.harness.store.feature_snapshots(correlation_id)
    for preferred_layer in ("L4", "PORTFOLIO", "L3", "L1", "L2"):
        for snapshot in snapshots:
            if snapshot.layer_id == preferred_layer:
                return dict(snapshot.decision_state or {})
    if snapshots:
        return dict(snapshots[0].decision_state or {})
    return {}


def _recommendation_payload(recommendation: Optional[Any]) -> Dict[str, Any]:
    return recommendation.to_dict() if recommendation is not None else {}


def _latest_or_none(items: List[Any]) -> Optional[Any]:
    return items[-1] if items else None


def _stage_from_equipment(equipment_id: Optional[str]) -> Optional[str]:
    if not equipment_id:
        return None
    return str(equipment_id).split("_", 1)[0].upper()


def _process_duration(context: Any, stage: str) -> int:
    if stage not in {"A", "B", "C"}:
        return 1
    try:
        return int(stage_process_time(context, stage))
    except Exception:
        return 1


def _task_snapshots(decision_state: Dict[str, Any], task_uids: List[int]) -> List[Dict[str, Any]]:
    tasks = decision_state.get("tasks", {}) or {}
    rows = []
    for uid in task_uids:
        row = tasks.get(uid)
        if row is None:
            row = tasks.get(str(uid))
        if isinstance(row, dict):
            item = dict(row)
            item.setdefault("uid", uid)
            rows.append(item)
    return rows


def _machine_snapshot(
    decision_state: Dict[str, Any],
    stage: str,
    equipment_id: Optional[str],
) -> Dict[str, Any]:
    if not stage or not equipment_id:
        return {}
    machine = (
        decision_state.get(stage, {})
        .get("machines", {})
        .get(str(equipment_id), {})
    )
    item = dict(machine or {})
    item.setdefault("equipment_id", equipment_id)
    item.setdefault("stage", stage)
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
        "kpis": dict(decision_state.get("kpis", {}) or {}),
    }


def _simulator_action_for_assignment(
    command: Any,
    stage: str,
    equipment_id: Optional[str],
) -> Dict[str, Any]:
    actions = dict(command.simulator_actions or {})
    if stage and equipment_id:
        return dict(actions.get(stage, {}).get(str(equipment_id), {}) or {})
    return actions


def _not_found(lookup: Dict[str, Any], reason: str) -> Dict[str, Any]:
    return {
        "found": False,
        "reason": reason,
        "lookup": lookup,
        "assignment": {},
        "decision_state": {},
        "state_summary": {},
        "task_snapshots": [],
        "machine_snapshot": {},
        "layers": {},
        "candidate_portfolio": {},
        "simulator_action": {},
    }
