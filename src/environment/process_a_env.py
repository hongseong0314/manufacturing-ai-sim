# -*- coding: utf-8 -*-
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.objects import ProcessA_Machine, Task

# Physical model constants.
W1_BASE, W2_BASE, W3_BASE, B_BASE = 0.5, 0.3, 0.2, 45.0
W12_BASE = 0.01
BETA, BETA_K = 0.2, 0.1
GAMMA, GAMMA_K = 1.5, 0.1
DELTA_W1, DELTA_W12, DELTA_B = 0.001, 0.0001, 0.02


class ProcessA_Env:
    """Environment for process A.

    This environment no longer performs internal scheduling.
    Assignment must be provided via external actions.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize process-A machines, queues, and metrics."""
        self.num_machines = config.get("num_machines_A", 10)
        self.process_time = config.get("process_time_A", 15)
        self.batch_size_A = config.get("batch_size_A", 1)
        self.machines = {
            i: ProcessA_Machine(i, batch_size=self.batch_size_A)
            for i in range(self.num_machines)
        }

        self.wait_pool: List[Task] = []
        self.rework_pool: List[Task] = []
        self.deterministic = config.get("deterministic_mode", False)

        self.stats = {
            "total_processed": 0,
            "total_passed": 0,
            "total_reworked": 0,
            "first_pass_rate": 0.0,
            "avg_rework_count": 0.0,
        }
        self.event_log: List[Dict[str, Any]] = []

    def _get_physical_model_params(self, m_age: int) -> Tuple[float, float, float]:
        """Return age-adjusted physical model coefficients."""
        w1 = W1_BASE * (1 - DELTA_W1 * m_age)
        w12 = W12_BASE * (1 - DELTA_W12 * m_age)
        b = B_BASE - DELTA_B * m_age
        return w1, w12, b

    def _run_qa_check(
        self,
        machine: ProcessA_Machine,
        recipe: List[float],
        task: Task,
        current_time: int,
    ) -> bool:
        """Evaluate A-process QA and append history record."""
        s1, s2, s3 = recipe
        w1, w12, b = self._get_physical_model_params(machine.m_age)

        g_s = (w1 * s1 + W2_BASE * s2 + W3_BASE * s3 + b) + (w12 * s1 * s2)
        effectiveness = 1 - BETA * np.tanh(BETA_K * machine.u)
        mean_qa = g_s * effectiveness
        std_dev_noise = GAMMA * np.tanh(GAMMA_K * machine.u)

        if self.deterministic:
            realized_qa = mean_qa
        else:
            realized_qa = np.random.normal(mean_qa, std_dev_noise)

        passed = task.spec_a[0] <= realized_qa <= task.spec_a[1]
        status = "PASS" if passed else "FAIL"
        print(
            f"  QA {status}: Task {task.uid:3d}, realized_qa={realized_qa:.2f}, "
            f"spec=({task.spec_a[0]:.1f}, {task.spec_a[1]:.1f}), g_s={g_s:.2f}"
        )

        task.history.append({"time": current_time, "process": "A", "qa": realized_qa})
        return passed

    def _resolve_machine(self, machine_key: Any) -> Optional[ProcessA_Machine]:
        """Resolve action key (`0`, `\"0\"`, or `\"A_0\"`) to a machine."""
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
        """Normalize raw UID list into integer UIDs."""
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
        """Reset machines, queues, event logs, and aggregate statistics."""
        self.machines = {
            i: ProcessA_Machine(i, batch_size=self.batch_size_A)
            for i in range(self.num_machines)
        }
        self.wait_pool = []
        self.rework_pool = []
        self.event_log = []
        self.stats = {
            "total_processed": 0,
            "total_passed": 0,
            "total_reworked": 0,
            "first_pass_rate": 0.0,
            "avg_rework_count": 0.0,
        }

    def step(
        self,
        current_time: int,
        actions: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[Task]]:
        """Advance process A by one step with externally provided actions.

        Example:
        `{"A_0": {"task_uids": [1, 2], "recipe": [10, 2, 1]}}`
        """
        succeeded_tasks: List[Task] = []
        actions = actions or {}

        # 1) Finish machines and run QA.
        for machine in self.machines.values():
            if machine.status != "busy" or current_time < machine.finish_time:
                continue

            recipe_used = machine.current_recipe if machine.current_recipe else [10, 2, 1]
            finished_batch = machine.finish_processing()

            task_uids = [t.uid for t in finished_batch]
            self.event_log.append(
                {
                    "timestamp": current_time,
                    "event_type": "task_completed",
                    "process": "A",
                    "machine_id": machine.id,
                    "task_uids": task_uids,
                    "end_time": current_time,
                }
            )

            for task in finished_batch:
                if self._run_qa_check(machine, recipe_used, task, current_time):
                    succeeded_tasks.append(task)
                    self.stats["total_passed"] += 1
                else:
                    task.location = "REWORK_A"
                    task.rework_count += 1
                    task.history.append(
                        {"time": current_time, "process": "A", "status": "Rework"}
                    )
                    self.rework_pool.append(task)
                    self.stats["total_reworked"] += 1

            self.stats["total_processed"] += len(finished_batch)

        # 2) Apply externally provided assignments only.
        if actions:
            tasks_to_remove: List[Tuple[str, Task]] = []
            allocated_uids = set()
            wait_pool_by_uid = {task.uid: task for task in self.wait_pool}
            rework_pool_by_uid = {task.uid: task for task in self.rework_pool}

            for machine_key, assignment in actions.items():
                if not isinstance(assignment, dict):
                    continue

                machine = self._resolve_machine(machine_key)
                if machine is None or machine.status != "idle":
                    continue

                task_uids = self._normalize_uids(assignment.get("task_uids", []))
                if not task_uids:
                    continue

                recipe = assignment.get("recipe", [10, 2, 1])
                batch: List[Task] = []
                pending_removals: List[Tuple[str, Task]] = []
                local_uids = set()
                can_assign = True

                for uid in task_uids:
                    if uid in allocated_uids or uid in local_uids:
                        can_assign = False
                        break
                    local_uids.add(uid)

                    rework_task = rework_pool_by_uid.get(uid)
                    if rework_task is not None:
                        batch.append(rework_task)
                        pending_removals.append(("rework", rework_task))
                        continue

                    wait_task = wait_pool_by_uid.get(uid)
                    if wait_task is not None:
                        batch.append(wait_task)
                        pending_removals.append(("wait", wait_task))
                        continue

                    can_assign = False
                    break

                if not can_assign or len(batch) != len(task_uids):
                    continue

                if assignment.get("replace_consumable", False):
                    machine.replace_consumable()

                finish_time = current_time + self.process_time
                machine.start_processing(batch, finish_time, recipe)
                allocated_uids.update(task_uids)
                tasks_to_remove.extend(pending_removals)

                self.event_log.append(
                    {
                        "timestamp": current_time,
                        "event_type": "task_assigned",
                        "process": "A",
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

        return {"succeeded": succeeded_tasks, "rework": self.rework_pool}

    def add_tasks(self, tasks: List[Task]):
        """Append new tasks to A waiting queue."""
        self.wait_pool.extend(tasks)

    def get_state(self) -> Dict[str, Any]:
        """Return compact queue/quality metrics for process A."""
        if self.stats["total_processed"] > 0:
            self.stats["first_pass_rate"] = (
                self.stats["total_passed"] / self.stats["total_processed"]
            )
            self.stats["avg_rework_count"] = (
                self.stats["total_reworked"] / self.stats["total_processed"]
            )
        else:
            self.stats["first_pass_rate"] = 0.0
            self.stats["avg_rework_count"] = 0.0

        return {
            "wait_pool_size": len(self.wait_pool),
            "rework_pool_size": len(self.rework_pool),
            "total_processed": self.stats["total_processed"],
            "total_passed": self.stats["total_passed"],
            "total_reworked": self.stats["total_reworked"],
            "first_pass_rate": self.stats["first_pass_rate"],
            "avg_rework_count": self.stats["avg_rework_count"],
        }
