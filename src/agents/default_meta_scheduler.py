# -*- coding: utf-8 -*-
"""Default meta scheduler implementation."""

from typing import Any, Dict, List

from src.agents.meta_scheduler import BaseMetaScheduler
from src.objects import Task
from src.schedulers.packers_c import BasePacker
from src.schedulers.schedulers_a import BaseScheduler as BaseSchedulerA
from src.schedulers.schedulers_b import BaseScheduler as BaseSchedulerB
from src.tuners.tuners_a import BaseRecipeTuner as BaseRecipeTunerA
from src.tuners.tuners_b import BaseRecipeTuner as BaseRecipeTunerB


class DefaultMetaScheduler(BaseMetaScheduler):
    """Baseline meta scheduler that combines assignment + recipe tuning."""

    def __init__(
        self,
        scheduler_a: BaseSchedulerA,
        scheduler_b: BaseSchedulerB,
        tuner_a: BaseRecipeTunerA,
        tuner_b: BaseRecipeTunerB,
        packer_c: BasePacker,
    ):
        self.scheduler_a = scheduler_a
        self.scheduler_b = scheduler_b
        self.tuner_a = tuner_a
        self.tuner_b = tuner_b
        self.packer_c = packer_c

    @staticmethod
    def _dedupe_preserve_order(uids: List[int]) -> List[int]:
        """Return unique UIDs while preserving first-seen order."""
        seen = set()
        ordered: List[int] = []
        for uid in uids:
            if uid in seen:
                continue
            seen.add(uid)
            ordered.append(uid)
        return ordered

    def _plan_ab_process(
        self,
        process_state: Dict[str, Any],
        tasks_state: Dict[int, Dict[str, Any]],
        scheduler: Any,
        tuner: Any,
        current_time: int,
    ) -> Dict[str, Dict[str, Any]]:
        """Plan machine assignments for process A or B."""
        planned: Dict[str, Dict[str, Any]] = {}
        allocated_uids = set()

        incoming_uids = list(process_state.get("incoming_uids", []))
        wait_pool_uids = self._dedupe_preserve_order(incoming_uids + list(process_state.get("wait_pool_uids", [])))
        rework_pool_uids = list(process_state.get("rework_pool_uids", []))
        machines = process_state.get("machines", {})

        for machine_id, machine_state in sorted(machines.items()):
            status = machine_state.get("status")
            try:
                finish_time = int(machine_state.get("finish_time", -1))
            except (TypeError, ValueError):
                finish_time = -1
            machine_available = status == "idle" or (status == "busy" and finish_time <= current_time)
            if not machine_available:
                continue

            wait_candidates = [uid for uid in wait_pool_uids if uid not in allocated_uids]
            rework_candidates = [uid for uid in rework_pool_uids if uid not in allocated_uids]
            if not wait_candidates and not rework_candidates:
                continue

            queue_info = {
                "wait_pool_size": len(wait_candidates),
                "rework_pool_size": len(rework_candidates),
                "rework_queue_size": len(rework_candidates),
            }
            batch_size = int(machine_state.get("batch_size", 1))
            selected_uids, task_type = scheduler.select_batch(
                wait_candidates,
                rework_candidates,
                batch_size,
            )
            if not selected_uids:
                continue

            task_rows = [tasks_state[uid] for uid in selected_uids if uid in tasks_state]
            if len(task_rows) != len(selected_uids):
                continue

            recipe = tuner.get_recipe(
                task_rows=task_rows,
                machine_state=machine_state,
                queue_info=queue_info,
                current_time=current_time,
            )
            planned[machine_id] = {
                "task_uids": selected_uids,
                "recipe": recipe,
                "task_type": task_type or "new",
            }
            allocated_uids.update(selected_uids)

        return planned

    def _snapshot_to_task(self, row: Dict[str, Any]) -> Task:
        """Convert decision-state task snapshot back to `Task` object."""
        spec_a_raw = row.get("spec_a", (45.0, 55.0))
        spec_b_raw = row.get("spec_b", (20.0, 80.0))
        task = Task(
            uid=int(row.get("uid")),
            job_id=str(row.get("job_id", "UNKNOWN")),
            due_date=int(row.get("due_date", 0)),
            spec_a=(float(spec_a_raw[0]), float(spec_a_raw[1])),
            spec_b=(float(spec_b_raw[0]), float(spec_b_raw[1])),
            arrival_time=int(row.get("arrival_time", 0)),
        )
        task.location = row.get("location", "QUEUE_C")
        task.rework_count = int(row.get("rework_count", 0))
        task.material_type = row.get("material_type", "plastic")
        task.color = row.get("color", "red")
        task.margin_value = float(row.get("margin_value", 0.5))
        task.realized_qa_A = float(row.get("realized_qa_A", -1.0))
        task.realized_qa_B = float(row.get("realized_qa_B", -1.0))
        return task

    def _plan_c_process(self, c_state: Dict[str, Any], tasks_state: Dict[int, Dict[str, Any]], current_time: int) -> Dict[str, Dict[str, Any]]:
        """Plan C packing actions using queue + incoming B handoff hints."""
        planned: Dict[str, Dict[str, Any]] = {}
        wait_pool_uids = list(c_state.get("wait_pool_uids", []))
        incoming_uids = list(c_state.get("incoming_from_B_uids", []))
        candidate_uids = self._dedupe_preserve_order(wait_pool_uids + incoming_uids)
        if not candidate_uids:
            return planned

        wait_pool_tasks: List[Task] = []
        wait_uid_set = set(wait_pool_uids)
        incoming_uid_set = set(incoming_uids)
        for uid in candidate_uids:
            row = tasks_state.get(uid)
            if row is None:
                continue
            row_for_c = dict(row)
            if uid in incoming_uid_set and uid not in wait_uid_set:
                # Incoming tasks from B become visible in C queue in this same step.
                row_for_c["arrival_time"] = current_time
                row_for_c["location"] = "QUEUE_C"
            wait_pool_tasks.append(self._snapshot_to_task(row_for_c))

        if not wait_pool_tasks:
            return planned

        should_pack, reason = self.packer_c.should_pack(
            wait_pool_tasks,
            current_time,
            int(c_state.get("last_pack_time", 0)),
        )
        force_timeout_pack = False
        if not should_pack and wait_pool_tasks:
            oldest_arrival = min(getattr(task, "arrival_time", current_time) for task in wait_pool_tasks)
            force_timeout_pack = current_time - oldest_arrival > self.packer_c.max_wait_time

        if not should_pack and not force_timeout_pack:
            return planned

        selected_pack = self.packer_c.select_pack(list(wait_pool_tasks), current_time)
        if not selected_pack:
            return planned

        machine_id = "C_0"
        machines = c_state.get("machines", {})
        if machines:
            machine_id = sorted(machines.keys())[0]

        planned[machine_id] = {
            "task_uids": [task.uid for task in selected_pack],
            "reason": reason if should_pack else "timeout_fallback",
        }
        return planned

    def decide(self, state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Generate V1 actions for A/B/C from decision state snapshot."""
        actions: Dict[str, Dict[str, Any]] = {"A": {}, "B": {}, "C": {}}
        tasks_state = state.get("tasks", {})
        current_time = int(state.get("time", 0))
        b_state = dict(state.get("B", {}))
        b_state["incoming_uids"] = list(b_state.get("incoming_from_A_uids", []))

        actions["A"] = self._plan_ab_process(
            process_state=state.get("A", {}),
            tasks_state=tasks_state,
            scheduler=self.scheduler_a,
            tuner=self.tuner_a,
            current_time=current_time,
        )
        actions["B"] = self._plan_ab_process(
            process_state=b_state,
            tasks_state=tasks_state,
            scheduler=self.scheduler_b,
            tuner=self.tuner_b,
            current_time=current_time,
        )
        actions["C"] = self._plan_c_process(
            c_state=state.get("C", {}),
            tasks_state=tasks_state,
            current_time=current_time,
        )

        return actions
