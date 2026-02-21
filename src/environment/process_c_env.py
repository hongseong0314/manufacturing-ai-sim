# -*- coding: utf-8 -*-
"""Process C environment (packing/finalization)."""

import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.objects import ProcessC_Machine, Task


class ProcessC_Env:
    """State-transition environment for process C (packing/finalization)."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize process-C queueing/packing state."""
        self.config = config
        try:
            num_machines = int(config.get("num_machines_C", 1))
        except (TypeError, ValueError):
            num_machines = 1
        self.num_machines = max(1, num_machines)
        try:
            batch_size = int(config.get("batch_size_C", config.get("N_pack", 4)))
        except (TypeError, ValueError):
            batch_size = 4
        self.batch_size_C = max(1, batch_size)
        try:
            max_packs = int(config.get("max_packs_per_step", 1))
        except (TypeError, ValueError):
            max_packs = 1
        self.max_packs_per_step = max(1, max_packs)
        self.machines: Dict[int, ProcessC_Machine] = {
            i: ProcessC_Machine(i, batch_size=self.batch_size_C)
            for i in range(self.num_machines)
        }

        self.wait_pool: List[Task] = []
        self.completed_tasks: List[Task] = []

        self.N_pack = self.batch_size_C
        self.max_wait_time = config.get("max_wait_time", 30)
        try:
            min_queue = int(config.get("min_queue_size", self.batch_size_C))
        except (TypeError, ValueError):
            min_queue = self.batch_size_C
        self.min_queue_size = min(max(1, min_queue), self.batch_size_C)

        self.last_pack_time = 0
        self.pack_count = 0
        self.deterministic = config.get("deterministic_mode", False)

        self.stats = {
            "total_packs": 0,
            "total_tasks_packed": 0,
            "avg_quality": 0.0,
            "avg_compat": 0.0,
            "avg_wait_time": 0.0,
        }
        self.event_log: List[Dict[str, Any]] = []
        self.compatibility_matrix = self._init_compatibility_matrix()
        self.capabilities = self._build_capabilities()
        self._warn_on_semantic_mismatch()

    def _init_compatibility_matrix(self) -> Dict[Tuple[str, str], float]:
        """Build material/color compatibility lookup table."""
        return {
            # Material
            ("plastic", "plastic"): 1.0,
            ("plastic", "metal"): 0.5,
            ("plastic", "composite"): 0.7,
            ("metal", "metal"): 1.0,
            ("metal", "plastic"): 0.5,
            ("metal", "composite"): 0.8,
            ("composite", "plastic"): 0.7,
            ("composite", "metal"): 0.8,
            ("composite", "composite"): 1.0,
            # Color
            ("red", "red"): 1.0,
            ("red", "blue"): 0.7,
            ("red", "green"): 0.6,
            ("blue", "red"): 0.7,
            ("blue", "blue"): 1.0,
            ("blue", "green"): 0.7,
            ("green", "red"): 0.6,
            ("green", "blue"): 0.7,
            ("green", "green"): 1.0,
        }

    def _build_capabilities(self) -> Dict[str, Any]:
        """Return runtime capability flags exposed to decision-state consumers."""
        multi_machine_active = self.num_machines > 1 and self.max_packs_per_step > 1
        return {
            "single_pack_per_step": self.max_packs_per_step == 1,
            "multi_machine_active": multi_machine_active,
            "max_packs_per_step": self.max_packs_per_step,
        }

    def _warn_on_semantic_mismatch(self):
        """Emit one-time warnings for potentially misleading C config options."""
        if self.num_machines > 1 and self.max_packs_per_step == 1:
            warnings.warn(
                (
                    "ProcessC_Env: num_machines_C > 1 but current runtime is single-pack-per-step. "
                    "Set max_packs_per_step > 1 to activate multi-machine packing."
                ),
                RuntimeWarning,
                stacklevel=2,
            )

        raw_process_time_c = self.config.get("process_time_C", 0)
        try:
            process_time_c = int(raw_process_time_c)
        except (TypeError, ValueError):
            process_time_c = 0
        if process_time_c != 0:
            warnings.warn(
                (
                    "ProcessC_Env: process_time_C is configured but not active in the current "
                    "instant-pack C transition model."
                ),
                RuntimeWarning,
                stacklevel=2,
            )

    def reset(self):
        """Reset machines, queue, stats, and event logs."""
        self.machines = {
            i: ProcessC_Machine(i, batch_size=self.batch_size_C)
            for i in range(self.num_machines)
        }
        self.wait_pool = []
        self.completed_tasks = []
        self.pack_count = 0
        self.last_pack_time = 0
        self.event_log = []
        self.stats = {
            "total_packs": 0,
            "total_tasks_packed": 0,
            "avg_quality": 0.0,
            "avg_compat": 0.0,
            "avg_wait_time": 0.0,
        }

    def add_tasks(self, tasks: List[Task], current_time: Optional[int] = None):
        """Add tasks to C queue and emit queue arrival events."""
        queue_time = 0 if current_time is None else int(current_time)
        for task in tasks:
            task.location = "QUEUE_C"
            task.arrival_time = queue_time
            self.event_log.append(
                {
                    "timestamp": queue_time,
                    "event_type": "task_queued",
                    "process": "C",
                    "machine_id": "C_QUEUE",
                    "task_uids": [task.uid],
                    "start_time": queue_time,
                    "end_time": queue_time,
                }
            )
        self.wait_pool.extend(tasks)

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

    def _extract_pack_requests(self, actions: Dict[str, Any]) -> List[Tuple[str, List[int], str]]:
        """Extract pack requests from supported action formats in stable order."""
        # Legacy single-machine style:
        # {"task_uids": [...], "reason": "..."}
        if "task_uids" in actions:
            return [
                (
                    "C_0",
                    self._normalize_uids(actions.get("task_uids", [])),
                    actions.get("reason", "external_action"),
                )
            ]

        requests: List[Tuple[str, List[int], str]] = []
        # Dict insertion order is preserved in Python 3.7+.
        for machine_key, assignment in actions.items():
            if not isinstance(assignment, dict):
                continue
            task_uids = self._normalize_uids(assignment.get("task_uids", []))
            if not task_uids:
                continue
            requests.append(
                (
                    str(machine_key),
                    task_uids,
                    assignment.get("reason", "external_action"),
                )
            )
        return requests

    def _try_complete_pack(
        self,
        current_time: int,
        machine_id: str,
        task_uids: List[int],
        reason: str,
    ) -> List[Task]:
        """Try to complete a single pack request and return packed tasks."""
        if not task_uids:
            return []
        if len(task_uids) != len(set(task_uids)):
            return []

        uid_to_task = {task.uid: task for task in self.wait_pool}
        selected_pack: List[Task] = []
        for uid in task_uids:
            task = uid_to_task.get(uid)
            if task is None:
                return []
            selected_pack.append(task)

        print(f"\n  t={current_time}: Packing start (reason: {reason})")
        for task in selected_pack:
            self.wait_pool.remove(task)

        pack_info = self._create_pack_info(selected_pack, current_time)
        for task in selected_pack:
            task.location = "COMPLETED"
            task.pack_id = self.pack_count
            task.history.append(
                {
                    "time": current_time,
                    "process": "C",
                    "status": "PACKED",
                    "pack_id": self.pack_count,
                    "pack_quality": pack_info["avg_quality"],
                    "pack_compat": pack_info["avg_compat"],
                    "wait_time": current_time - getattr(task, "arrival_time", 0),
                }
            )

        self.completed_tasks.extend(selected_pack)
        self.event_log.append(
            {
                "timestamp": current_time,
                "event_type": "pack_completed",
                "process": "C",
                "machine_id": machine_id,
                "task_uids": [t.uid for t in selected_pack],
                "pack_id": self.pack_count,
                "start_time": current_time,
                "end_time": current_time,
            }
        )

        self.pack_count += 1
        self.last_pack_time = current_time
        self._update_stats(pack_info)

        print(f"    [OK] Pack #{self.pack_count - 1} completed!")
        print(f"       - Avg Quality: {pack_info['avg_quality']:.2f}")
        print(f"       - Compatibility: {pack_info['avg_compat']:.2f}")
        print(f"       - Tasks: {[t.uid for t in selected_pack]}")
        return selected_pack

    def step(
        self,
        current_time: int,
        actions: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Advance process C by one step.

        Example:
        `{"C_0": {"task_uids": [11, 12, 13, 14], "reason": "batch_ready"}}`
        """
        completed_packs: List[Task] = []
        actions = actions or {}

        pack_requests = self._extract_pack_requests(actions)
        if pack_requests:
            step_pack_budget = min(self.max_packs_per_step, self.num_machines)
            processed_packs = 0
            used_uids = set()
            for machine_id, task_uids, reason in pack_requests:
                if processed_packs >= step_pack_budget:
                    break
                if not task_uids:
                    continue
                if any(uid in used_uids for uid in task_uids):
                    continue

                selected_pack = self._try_complete_pack(
                    current_time=current_time,
                    machine_id=machine_id,
                    task_uids=task_uids,
                    reason=reason,
                )
                if not selected_pack:
                    continue
                completed_packs.extend(selected_pack)
                used_uids.update(task.uid for task in selected_pack)
                processed_packs += 1

        if self.wait_pool:
            oldest_arrival = min(
                [getattr(task, "arrival_time", 0) for task in self.wait_pool],
                default=current_time,
            )
            max_wait = current_time - oldest_arrival
            print(f"    [Queue] waiting {len(self.wait_pool)} tasks, max wait {max_wait}")

        return {
            "completed": completed_packs,
            "pack_count": self.pack_count,
            "queue_size": len(self.wait_pool),
        }

    def _get_pairwise_compat(self, task_i: Task, task_j: Task) -> float:
        """Compute average compatibility score for one task pair."""
        mat_i = getattr(task_i, "material_type", "plastic")
        mat_j = getattr(task_j, "material_type", "plastic")
        key_mat = (mat_i, mat_j) if (mat_i, mat_j) in self.compatibility_matrix else (mat_j, mat_i)
        mat_compat = self.compatibility_matrix.get(key_mat, 0.7)

        color_i = getattr(task_i, "color", "red")
        color_j = getattr(task_j, "color", "red")
        key_color = (
            (color_i, color_j)
            if (color_i, color_j) in self.compatibility_matrix
            else (color_j, color_i)
        )
        color_compat = self.compatibility_matrix.get(key_color, 0.7)

        return (mat_compat + color_compat) / 2

    def _compute_compatibility(self, tasks: List[Task]) -> float:
        """Compute geometric-mean compatibility over all task pairs."""
        if len(tasks) < 2:
            return 1.0

        compat_product = 1.0
        for i, task_i in enumerate(tasks):
            for task_j in tasks[i + 1 :]:
                compat_product *= self._get_pairwise_compat(task_i, task_j)

        n_pairs = len(tasks) * (len(tasks) - 1) / 2
        if n_pairs <= 0:
            return 1.0
        return compat_product ** (1 / n_pairs)

    def _create_pack_info(self, pack: List[Task], current_time: int) -> Dict[str, Any]:
        """Build aggregate metrics for one completed pack."""
        avg_quality = np.mean([getattr(task, "realized_qa_B", 50) for task in pack])
        avg_compat = self._compute_compatibility(pack)
        wait_times = [current_time - getattr(task, "arrival_time", current_time) for task in pack]
        avg_wait = np.mean(wait_times) if wait_times else 0

        return {
            "pack_id": self.pack_count,
            "avg_quality": avg_quality,
            "avg_compat": avg_compat,
            "avg_wait_time": avg_wait,
            "task_count": len(pack),
        }

    def _update_stats(self, pack_info: Dict[str, Any]):
        """Update running averages using one pack summary."""
        n = self.stats["total_packs"]
        self.stats["total_packs"] += 1
        self.stats["total_tasks_packed"] += pack_info["task_count"]

        self.stats["avg_quality"] = (
            (self.stats["avg_quality"] * n + pack_info["avg_quality"]) / (n + 1)
        )
        self.stats["avg_compat"] = (
            (self.stats["avg_compat"] * n + pack_info["avg_compat"]) / (n + 1)
        )
        self.stats["avg_wait_time"] = (
            (self.stats["avg_wait_time"] * n + pack_info["avg_wait_time"]) / (n + 1)
        )

    def get_state(self) -> Dict[str, Any]:
        """Return compact queue/packing metrics for process C."""
        return {
            "queue_size": len(self.wait_pool),
            "completed_packs": self.pack_count,
            "total_tasks_packed": self.stats["total_tasks_packed"],
            "avg_quality": self.stats["avg_quality"],
            "avg_compat": self.stats["avg_compat"],
            "avg_wait_time": self.stats["avg_wait_time"],
        }
