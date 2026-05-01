# -*- coding: utf-8 -*-
"""Adapters between the simulator kernel and MES-facing DTOs."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from src.mes.domain import Equipment, FeatureSnapshot, Lot, Wafer
from src.mes.recommendations import make_id


SIM_STATUS_TO_MES = {
    "idle": "IDLE",
    "busy": "RUN",
}


def stage_from_equipment_id(equipment_id: str) -> Optional[str]:
    """Return A/B/C from simulator equipment ids like `A_0`."""
    if not equipment_id:
        return None
    first = str(equipment_id)[0].upper()
    return first if first in {"A", "B", "C"} else None


def wafer_id_from_task_uid(uid: int) -> str:
    return f"WAFER_{int(uid)}"


def task_uid_from_wafer_id(wafer_id: str) -> Optional[int]:
    suffix = str(wafer_id).split("_")[-1]
    if not suffix.isdigit():
        return None
    return int(suffix)


class SimulatorMESAdapter:
    """Convert simulator state/action payloads into MES shell structures."""

    def decision_state_to_mes(self, decision_state: Dict[str, Any]) -> Dict[str, Any]:
        tasks = self._task_rows(decision_state.get("tasks", {}))
        lots = self._lots_from_tasks(tasks)
        wafers = [self._wafer_from_task(row, idx) for idx, row in enumerate(tasks)]
        equipment = self._equipment_from_state(decision_state)
        return {
            "time": decision_state.get("time", 0),
            "lots": [lot.to_dict() for lot in lots],
            "wafers": [wafer.to_dict() for wafer in wafers],
            "equipment": [tool.to_dict() for tool in equipment],
            "wip": self._wip_from_state(decision_state),
            "queues": self._queues_from_state(decision_state),
            "kpis": {
                "num_completed": decision_state.get("num_completed", 0),
                "max_steps": decision_state.get("max_steps", 0),
            },
        }

    def feature_snapshot_from_state(
        self,
        decision_state: Dict[str, Any],
        layer_id: str,
        correlation_id: Optional[str] = None,
        features: Optional[Dict[str, Any]] = None,
    ) -> FeatureSnapshot:
        """Persistable snapshot envelope for a layer decision."""
        resolved_correlation_id = correlation_id or make_id("CORR")
        return FeatureSnapshot(
            feature_snapshot_id=make_id(f"FS_{layer_id}"),
            correlation_id=resolved_correlation_id,
            layer_id=layer_id,
            source="simulator",
            decision_state=decision_state,
            features=dict(features or {}),
        )

    def command_to_simulator_actions(
        self,
        command: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """Convert a validated MES command into `ManufacturingEnv.step` actions."""
        stage = command.get("stage") or stage_from_equipment_id(
            str(command.get("equipment_id", ""))
        )
        equipment_id = str(command.get("equipment_id", ""))
        task_uids = [int(uid) for uid in command.get("task_uids", [])]
        if stage not in {"A", "B", "C"} or not equipment_id or not task_uids:
            return {"A": {}, "B": {}, "C": {}}

        assignment: Dict[str, Any] = {
            "task_uids": task_uids,
            "task_type": command.get("task_type", "new"),
        }
        if stage == "A":
            assignment["recipe"] = command.get("recipe", [10, 2, 1])
            assignment["replace_consumable"] = bool(
                command.get("replace_consumable", False)
            )
        elif stage == "B":
            assignment["recipe"] = command.get("recipe", [50.0, 50.0, 30.0])
            assignment["replace_solution"] = bool(command.get("replace_solution", False))
        else:
            assignment["reason"] = command.get("reason", "mes_validated")

        actions: Dict[str, Dict[str, Any]] = {"A": {}, "B": {}, "C": {}}
        actions[stage][equipment_id] = assignment
        return actions

    def _task_rows(self, tasks_by_uid: Any) -> List[Dict[str, Any]]:
        if not isinstance(tasks_by_uid, dict):
            return []
        rows = [row for row in tasks_by_uid.values() if isinstance(row, dict)]
        return sorted(rows, key=lambda row: int(row.get("uid", 0)))

    def _lots_from_tasks(self, task_rows: Iterable[Dict[str, Any]]) -> List[Lot]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for row in task_rows:
            lot_id = str(row.get("job_id", "UNKNOWN"))
            group = grouped.setdefault(
                lot_id,
                {
                    "quantity": 0,
                    "due_date": int(row.get("due_date", 0)),
                    "rework_count": 0,
                    "statuses": [],
                    "product_id": str(row.get("material_type", "PRODUCT_DEFAULT")),
                },
            )
            group["quantity"] += 1
            group["rework_count"] = max(
                int(group["rework_count"]),
                int(row.get("rework_count", 0)),
            )
            group["statuses"].append(self._status_from_location(row))

        lots = []
        for lot_id, group in sorted(grouped.items()):
            lots.append(
                Lot(
                    lot_id=lot_id,
                    product_id=group["product_id"],
                    status=self._rollup_status(group["statuses"]),
                    due_date=int(group["due_date"]),
                    quantity=int(group["quantity"]),
                    rework_count=int(group["rework_count"]),
                )
            )
        return lots

    def _wafer_from_task(self, row: Dict[str, Any], slot_no: int) -> Wafer:
        uid = int(row.get("uid", 0))
        return Wafer(
            wafer_id=wafer_id_from_task_uid(uid),
            lot_id=str(row.get("job_id", "UNKNOWN")),
            slot_no=slot_no,
            status=self._status_from_location(row),
            current_operation_id=self._operation_from_location(str(row.get("location", ""))),
            qa_results={
                "A": row.get("realized_qa_A", -1.0),
                "B": row.get("realized_qa_B", -1.0),
            },
            task_uid=uid,
        )

    def _equipment_from_state(self, decision_state: Dict[str, Any]) -> List[Equipment]:
        equipment: List[Equipment] = []
        tasks = decision_state.get("tasks", {})
        for stage in ("A", "B", "C"):
            stage_state = decision_state.get(stage, {})
            machines = stage_state.get("machines", {})
            for equipment_id, machine in sorted(machines.items()):
                if not isinstance(machine, dict):
                    continue
                current_batch = list(machine.get("current_batch_uids", []))
                current_lot_id = self._lot_for_uid(tasks, current_batch[0]) if current_batch else ""
                equipment.append(
                    Equipment(
                        equipment_id=str(equipment_id),
                        equipment_group_id=stage,
                        status=SIM_STATUS_TO_MES.get(
                            str(machine.get("status", "")).lower(),
                            str(machine.get("status", "UNKNOWN")).upper(),
                        ),
                        current_lot_id=current_lot_id,
                        capable_operations=[stage],
                        batch_size=int(machine.get("batch_size", 1)),
                        health_state=self._health_state(machine),
                        last_event_time=machine.get("finish_time"),
                    )
                )
        return equipment

    def _wip_from_state(self, decision_state: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
        wip: Dict[str, Dict[str, int]] = {}
        for stage in ("A", "B", "C"):
            stage_state = decision_state.get(stage, {})
            wait = len(stage_state.get("wait_pool_uids", []))
            rework = len(stage_state.get("rework_pool_uids", []))
            incoming = len(stage_state.get(f"incoming_from_{self._upstream(stage)}_uids", []))
            wip[stage] = {
                "wait": wait,
                "rework": rework,
                "incoming": incoming,
                "total": wait + rework + incoming,
            }
        return wip

    def _queues_from_state(self, decision_state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        queues: Dict[str, Dict[str, Any]] = {}
        for stage in ("A", "B", "C"):
            stage_state = decision_state.get(stage, {})
            queues[stage] = {
                "wait_pool_uids": list(stage_state.get("wait_pool_uids", [])),
                "rework_pool_uids": list(stage_state.get("rework_pool_uids", [])),
                "queue_stats": dict(stage_state.get("queue_stats", {})),
            }
        return queues

    def _health_state(self, machine: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: value
            for key, value in machine.items()
            if key not in {"status", "batch_size", "current_batch_uids"}
        }

    def _lot_for_uid(self, tasks_by_uid: Any, uid: Any) -> str:
        if not isinstance(tasks_by_uid, dict):
            return ""
        row = tasks_by_uid.get(uid) or tasks_by_uid.get(str(uid))
        return str(row.get("job_id", "")) if isinstance(row, dict) else ""

    def _status_from_location(self, row: Dict[str, Any]) -> str:
        location = str(row.get("location", ""))
        if location == "COMPLETED":
            return "COMPLETED"
        if "REWORK" in location:
            return "REWORK"
        if location.startswith("PROC_"):
            return "PROCESSING"
        return "WAIT"

    def _operation_from_location(self, location: str) -> str:
        if location.endswith("_A") or location == "QUEUE_A":
            return "A"
        if location.endswith("_B") or location == "QUEUE_B":
            return "B"
        if location.endswith("_C") or location == "QUEUE_C":
            return "C"
        if location.startswith("PROC_"):
            return stage_from_equipment_id(location.replace("PROC_", "")) or "UNKNOWN"
        return "UNKNOWN"

    def _rollup_status(self, statuses: Iterable[str]) -> str:
        ordered = ["PROCESSING", "REWORK", "WAIT", "COMPLETED"]
        status_set = set(statuses)
        for status in ordered:
            if status in status_set:
                return status
        return "WAIT"

    def _upstream(self, stage: str) -> str:
        return {"A": "", "B": "A", "C": "B"}.get(stage, "")

