# -*- coding: utf-8 -*-
"""Process B environment (inspection)."""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.objects import ProcessB_Machine, Task


class ProcessB_Env:
    # Physical model params.
    C1_BASE = 0.4
    C2 = 0.3
    C3 = 0.2
    D_BASE = 40.0
    C12_BASE = 0.01
    DELTA_C = 0.001
    DELTA_D = 0.02

    ALPHA = 0.15
    ALPHA_K = 0.1
    BETA = 1.5
    BETA_K = 0.1

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.num_machines = config.get("num_machines_B", 5)
        self.process_time = config.get("process_time_B", 4)
        self.batch_size_B = config.get("batch_size_B", 1)

        self.machines: Dict[int, ProcessB_Machine] = {
            i: ProcessB_Machine(i, batch_size=self.batch_size_B)
            for i in range(self.num_machines)
        }

        self.wait_pool: List[Task] = []
        self.rework_pool: List[Task] = []
        self.deterministic = config.get("deterministic_mode", False)

        self.stats = {
            "total_processed": 0,
            "total_passed": 0,
            "total_reworked": 0,
            "solution_replacements": 0,
            "first_pass_rate": 0.0,
            "avg_rework_count": 0.0,
        }
        self.event_log: List[Dict[str, Any]] = []

    def _resolve_machine(self, machine_key: Any) -> Optional[ProcessB_Machine]:
        machine_idx: Optional[int] = None

        if isinstance(machine_key, int):
            machine_idx = machine_key
        elif isinstance(machine_key, str):
            suffix = machine_key.split("_")[-1] if "_" in machine_key else machine_key
            if suffix.isdigit():
                machine_idx = int(suffix)

        if machine_idx is None:
            return None
        return self.machines.get(machine_idx)

    def _normalize_uids(self, raw_uids: Any) -> List[int]:
        if not isinstance(raw_uids, list):
            return []
        normalized: List[int] = []
        for raw_uid in raw_uids:
            try:
                normalized.append(int(raw_uid))
            except (TypeError, ValueError):
                return []
        return normalized

    def reset(self):
        self.machines = {
            i: ProcessB_Machine(i, batch_size=self.batch_size_B)
            for i in range(self.num_machines)
        }
        self.wait_pool = []
        self.rework_pool = []
        self.event_log = []
        self.stats = {
            "total_processed": 0,
            "total_passed": 0,
            "total_reworked": 0,
            "solution_replacements": 0,
            "first_pass_rate": 0.0,
            "avg_rework_count": 0.0,
        }

    def add_tasks(self, tasks: List[Task]):
        for task in tasks:
            task.location = "QUEUE_B"
        self.wait_pool.extend(tasks)

    def _run_qa_check(
        self,
        machine: ProcessB_Machine,
        recipe: List[float],
        task: Task,
        current_time: int,
    ) -> Dict[str, Any]:
        try:
            r1, r2, r3 = [float(x) for x in recipe]
        except (ValueError, TypeError):
            r1, r2, r3 = 50.0, 50.0, 30.0

        base_quality = (r1 + r2 + r3) / 3.0
        effectiveness = max(0.1, 1.0 - self.ALPHA * (machine.v / 30.0))
        mean_qa = 50.0 + (base_quality - 40.0) * 0.5 * effectiveness
        mean_qa = max(50.0, min(100.0, mean_qa))

        if self.deterministic:
            realized_qa = mean_qa
        else:
            std_dev = self.BETA * 0.1
            realized_qa = np.random.normal(mean_qa, std_dev)
            realized_qa = max(50.0, min(100.0, realized_qa))

        degradation = 1.0 - (machine.b_age / 1000.0) * 0.1
        realized_qa *= degradation
        realized_qa = max(50.0, min(100.0, realized_qa))

        min_b, max_b = task.spec_b
        passed = min_b < realized_qa < max_b

        return {
            "passed": passed,
            "realized_qa": realized_qa,
            "mean_qa": mean_qa,
            "effectiveness": effectiveness,
        }

    def step(
        self,
        current_time: int,
        actions: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        succeeded_tasks: List[Task] = []
        rework_tasks: List[Task] = []
        solution_replacements_this_step = 0
        actions = actions or {}

        # 1) Finish inspection for busy machines.
        for machine in self.machines.values():
            if machine.status != "busy" or current_time < machine.finish_time:
                continue

            recipe_used = machine.current_recipe if machine.current_recipe else [0.0, 0.0, 0.0]
            finished_batch = machine.finish_processing()

            task_uids = [t.uid for t in finished_batch]
            self.event_log.append(
                {
                    "timestamp": current_time,
                    "event_type": "task_completed",
                    "process": "B",
                    "machine_id": machine.id,
                    "task_uids": task_uids,
                    "end_time": current_time,
                }
            )

            for task in finished_batch:
                qa_result = self._run_qa_check(machine, recipe_used, task, current_time)

                if qa_result["passed"]:
                    succeeded_tasks.append(task)
                    task.location = "QUEUE_C"
                    task.realized_qa_B = qa_result["realized_qa"]
                    self.stats["total_passed"] += 1
                    print(
                        f"  t={current_time}: Task {task.uid:3d} inspection PASS "
                        f"(qa={qa_result['realized_qa']:.2f})"
                    )
                else:
                    rework_tasks.append(task)
                    task.location = "REWORK_B"
                    task.rework_count += 1
                    self.rework_pool.append(task)
                    self.stats["total_reworked"] += 1
                    print(
                        f"  t={current_time}: Task {task.uid:3d} inspection FAIL "
                        f"(qa={qa_result['realized_qa']:.2f})"
                    )

                task.history.append(
                    {
                        "time": current_time,
                        "process": "B",
                        "realized_qa": qa_result["realized_qa"],
                        "passed": qa_result["passed"],
                        "recipe": recipe_used,
                        "rework_count": task.rework_count,
                    }
                )

            self.stats["total_processed"] += len(finished_batch)

            if machine.v >= 20:
                machine.replace_solution()
                solution_replacements_this_step += 1
                self.stats["solution_replacements"] += 1
                print(f"  t={current_time}: Machine {machine.id} solution replaced")

        # 2) Apply externally provided assignments only.
        tasks_to_remove: List[Tuple[str, Task]] = []
        if actions:
            allocated_uids = set()

            for machine_key, assignment in actions.items():
                if not isinstance(assignment, dict):
                    continue

                machine = self._resolve_machine(machine_key)
                if machine is None or machine.status != "idle":
                    continue

                task_uids = self._normalize_uids(assignment.get("task_uids", []))
                if not task_uids:
                    continue

                recipe = assignment.get("recipe", [50.0, 50.0, 30.0])
                batch: List[Task] = []
                pending_removals: List[Tuple[str, Task]] = []
                local_uids = set()
                can_assign = True

                for uid in task_uids:
                    if uid in allocated_uids or uid in local_uids:
                        can_assign = False
                        break
                    local_uids.add(uid)

                    rework_task = next(
                        (task for task in self.rework_pool if task.uid == uid),
                        None,
                    )
                    if rework_task is not None:
                        batch.append(rework_task)
                        pending_removals.append(("rework", rework_task))
                        continue

                    wait_task = next(
                        (task for task in self.wait_pool if task.uid == uid),
                        None,
                    )
                    if wait_task is not None:
                        batch.append(wait_task)
                        pending_removals.append(("wait", wait_task))
                        continue

                    can_assign = False
                    break

                if not can_assign or len(batch) != len(task_uids):
                    continue

                finish_time = current_time + self.process_time
                machine.start_processing(batch, finish_time, recipe)
                allocated_uids.update(task_uids)
                tasks_to_remove.extend(pending_removals)

                self.event_log.append(
                    {
                        "timestamp": current_time,
                        "event_type": "task_assigned",
                        "process": "B",
                        "machine_id": machine.id,
                        "task_uids": task_uids,
                        "start_time": current_time,
                        "end_time": finish_time,
                        "task_type": assignment.get("task_type", "external_action"),
                    }
                )

        for pool_type, task in tasks_to_remove:
            try:
                if pool_type == "rework":
                    self.rework_pool.remove(task)
                else:
                    self.wait_pool.remove(task)
            except ValueError:
                pass

        # 3) Update aggregate stats.
        if self.stats["total_processed"] > 0:
            self.stats["first_pass_rate"] = (
                self.stats["total_passed"] / self.stats["total_processed"]
            )
            total_rework_count = sum(t.rework_count for t in succeeded_tasks + rework_tasks)
            total_count = len(succeeded_tasks) + len(rework_tasks)
            if total_count > 0:
                self.stats["avg_rework_count"] = total_rework_count / total_count

        return {
            "succeeded": succeeded_tasks,
            "rework": rework_tasks,
            "completed_this_step": len(succeeded_tasks),
            "rework_count_this_step": len(rework_tasks),
            "solution_replacements": solution_replacements_this_step,
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            "wait_pool_size": len(self.wait_pool),
            "rework_pool_size": len(self.rework_pool),
            "idle_machines": sum(1 for m in self.machines.values() if m.status == "idle"),
            "busy_machines": sum(1 for m in self.machines.values() if m.status == "busy"),
            "first_pass_rate": self.stats["first_pass_rate"],
            "total_passed": self.stats["total_passed"],
            "total_reworked": self.stats["total_reworked"],
        }
