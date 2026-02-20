# -*- coding: utf-8 -*-
from typing import Any, Dict, Iterable, List, Optional, Set

from src.data_generator import DataGenerator
from src.environment.process_a_env import ProcessA_Env
from src.environment.process_b_env import ProcessB_Env
from src.environment.process_c_env import ProcessC_Env
from src.objects import Task


class ManufacturingEnv:
    """Top-level orchestrator integrating process A/B/C.

    Strict External control:
    - This environment only applies actions and advances state transitions.
    - Scheduling/packing decisions must be provided from outside (e.g., Meta Scheduler).
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize process environments and normalize cross-process config."""
        self.config = self._normalize_config(config)
        self.time = 0
        self.data_generator = DataGenerator()
        self._periodic_enabled = True

        self.env_A = ProcessA_Env(self.config)
        self.env_B = ProcessB_Env(self.config)
        self.env_C = ProcessC_Env(self.config)

        self.completed_tasks: List[Task] = []

    def _normalize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize cross-process config keys and safe defaults."""
        normalized = dict(config)
        try:
            batch_size_c = int(normalized.get("batch_size_C", normalized.get("N_pack", 4)))
        except (TypeError, ValueError):
            batch_size_c = 4
        if batch_size_c <= 0:
            batch_size_c = 1
        normalized["batch_size_C"] = batch_size_c
        normalized["N_pack"] = batch_size_c

        try:
            raw_min_queue = int(normalized.get("min_queue_size", batch_size_c))
        except (TypeError, ValueError):
            raw_min_queue = batch_size_c
        if raw_min_queue <= 0:
            raw_min_queue = 1
        normalized["min_queue_size"] = min(raw_min_queue, batch_size_c)
        return normalized

    def _normalize_action_uids(self, raw_uids: Any) -> List[int]:
        """Normalize a raw UID list into integer UIDs."""
        if not isinstance(raw_uids, list):
            return []
        normalized: List[int] = []
        for raw_uid in raw_uids:
            try:
                normalized.append(int(raw_uid))
            except (TypeError, ValueError):
                continue
        return normalized

    def _sanitize_actions_for_process(
        self,
        raw_actions: Dict[str, Any],
        wait_uids: Set[int],
        rework_uids: Optional[Set[int]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Drop invalid or duplicate UIDs for a process action payload.

        The sanitizer keeps only UIDs that currently exist in the target process
        wait/rework pools, which makes pre-planned incoming actions safe.
        """
        if not isinstance(raw_actions, dict):
            return {}

        valid_rework = rework_uids or set()
        sanitized: Dict[str, Dict[str, Any]] = {}
        globally_used: Set[int] = set()

        for machine_key, assignment in raw_actions.items():
            if not isinstance(assignment, dict):
                continue

            requested_uids = self._normalize_action_uids(assignment.get("task_uids", []))
            local_seen: Set[int] = set()
            valid_uids: List[int] = []
            for uid in requested_uids:
                if uid in local_seen or uid in globally_used:
                    continue
                if uid in wait_uids or uid in valid_rework:
                    valid_uids.append(uid)
                    local_seen.add(uid)

            if not valid_uids:
                continue

            cleaned = dict(assignment)
            cleaned["task_uids"] = valid_uids
            sanitized[str(machine_key)] = cleaned
            globally_used.update(valid_uids)

        return sanitized

    def _finishing_now_uids(self, machines: Dict[Any, Any]) -> List[int]:
        """Collect UIDs from machines that finish at current global time."""
        finishing_uids: List[int] = []
        for machine in machines.values():
            if getattr(machine, "status", "") != "busy":
                continue
            try:
                finish_time = int(getattr(machine, "finish_time", -1))
            except (TypeError, ValueError):
                finish_time = -1
            if finish_time > self.time:
                continue
            for task in getattr(machine, "current_batch", []):
                finishing_uids.append(task.uid)
        return finishing_uids

    def step(self, actions: Optional[Dict[str, Dict[str, Any]]] = None):
        """Advance A->B->C by one global step using external actions.

        Example action payload (V1):
        {
            "A": {"A_0": {"task_uids": [1, 2], "recipe": [10.0, 2.0, 1.0]}},
            "B": {"B_0": {"task_uids": [3], "recipe": [50.0, 50.0, 30.0]}},
            "C": {"C_0": {"task_uids": [4, 5], "reason": "batch_ready"}},
        }
        """
        incoming_actions = actions if isinstance(actions, dict) else {}
        a_actions = incoming_actions.get("A") or {}
        b_actions = incoming_actions.get("B") or {}
        c_actions = incoming_actions.get("C") or {}

        # 1) Process A step.
        results_A = self.env_A.step(self.time, a_actions)
        if results_A["succeeded"]:
            self.env_B.add_tasks(results_A["succeeded"])

        # 2) Process B step.
        b_wait_uids = {task.uid for task in self.env_B.wait_pool}
        b_rework_uids = {task.uid for task in self.env_B.rework_pool}
        sanitized_b_actions = self._sanitize_actions_for_process(
            b_actions,
            wait_uids=b_wait_uids,
            rework_uids=b_rework_uids,
        )
        results_B = self.env_B.step(self.time, sanitized_b_actions)
        if results_B["succeeded"]:
            self.env_C.add_tasks(results_B["succeeded"], current_time=self.time)

        # 3) Process C step.
        c_wait_uids = {task.uid for task in self.env_C.wait_pool}
        sanitized_c_actions = self._sanitize_actions_for_process(
            c_actions,
            wait_uids=c_wait_uids,
        )
        results_C = self.env_C.step(self.time, sanitized_c_actions)
        if results_C["completed"]:
            for task in results_C["completed"]:
                if task.location != "COMPLETED":
                    task.location = "COMPLETED"
            self.completed_tasks.extend(results_C["completed"])
            print(
                f"t={self.time}: Pack #{results_C['pack_count'] - 1} completed, "
                f"{len(results_C['completed'])} tasks finalized "
                f"(Total: {len(self.completed_tasks)})"
            )

        # 4) Periodic new job generation.
        if getattr(self, "_periodic_enabled", True) and self.time > 0 and self.time % 30 == 0:
            new_tasks = self.data_generator.generate_new_jobs(self.time)
            self.env_A.add_tasks(new_tasks)

        # 5) Advance time and return.
        self.time += 1
        obs = self._get_observation()
        reward = self._calculate_reward(results_A, results_B, results_C)
        done = self._check_if_done()
        return obs, reward, done, {}

    def reset(
        self,
        seed_initial_tasks: bool = True,
        initial_tasks: Optional[List[Task]] = None,
    ):
        """Reset full manufacturing environment.

        Args:
        - `seed_initial_tasks=True`: generate default initial arrivals for A.
        - `initial_tasks`: explicit initial set (takes precedence when provided).
        """
        self.time = 0
        self.data_generator = DataGenerator()
        self.completed_tasks = []

        self.env_A.reset()
        self.env_B.reset()
        self.env_C.reset()

        self._periodic_enabled = bool(seed_initial_tasks)

        if initial_tasks is not None:
            self.env_A.add_tasks(initial_tasks)
        elif seed_initial_tasks:
            generated_tasks = self.data_generator.generate_new_jobs(self.time)
            self.env_A.add_tasks(generated_tasks)

        return self._get_observation()

    def _get_observation(self) -> Dict[str, Any]:
        """Return compact runtime observation used by scripts/tests."""
        return {
            "time": self.time,
            "A_state": self.env_A.get_state(),
            "B_state": self.env_B.get_state(),
            "C_state": self.env_C.get_state(),
            "num_completed": len(self.completed_tasks),
        }

    def _iter_machine_tasks(self, machines: Dict[Any, Any]) -> Iterable[Task]:
        """Yield tasks currently being processed by the provided machines."""
        for machine in machines.values():
            for task in getattr(machine, "current_batch", []):
                yield task

    def _snapshot_task(self, task: Task) -> Dict[str, Any]:
        """Create scheduler-facing immutable snapshot for a single task."""
        return {
            "uid": task.uid,
            "job_id": getattr(task, "job_id", ""),
            "due_date": getattr(task, "due_date", 0),
            "spec_a": tuple(getattr(task, "spec_a", (45.0, 55.0))),
            "spec_b": tuple(getattr(task, "spec_b", (20.0, 80.0))),
            "location": getattr(task, "location", ""),
            "rework_count": int(getattr(task, "rework_count", 0)),
            "arrival_time": int(getattr(task, "arrival_time", 0)),
            "material_type": getattr(task, "material_type", "plastic"),
            "color": getattr(task, "color", "red"),
            "margin_value": float(getattr(task, "margin_value", 0.5)),
            "realized_qa_A": float(getattr(task, "realized_qa_A", -1.0)),
            "realized_qa_B": float(getattr(task, "realized_qa_B", -1.0)),
        }

    def _snapshot_machines_a(self) -> Dict[str, Dict[str, Any]]:
        """Snapshot A machine states."""
        snapshot: Dict[str, Dict[str, Any]] = {}
        for machine in self.env_A.machines.values():
            snapshot[str(machine.id)] = {
                "status": machine.status,
                "finish_time": machine.finish_time,
                "batch_size": machine.batch_size,
                "u": getattr(machine, "u", 0),
                "m_age": getattr(machine, "m_age", 0),
                "current_batch_uids": [task.uid for task in machine.current_batch],
            }
        return snapshot

    def _snapshot_machines_b(self) -> Dict[str, Dict[str, Any]]:
        """Snapshot B machine states."""
        snapshot: Dict[str, Dict[str, Any]] = {}
        for machine in self.env_B.machines.values():
            snapshot[str(machine.id)] = {
                "status": machine.status,
                "finish_time": machine.finish_time,
                "batch_size": machine.batch_size,
                "v": getattr(machine, "v", 0),
                "b_age": getattr(machine, "b_age", 0),
                "current_batch_uids": [task.uid for task in machine.current_batch],
            }
        return snapshot

    def _snapshot_machines_c(self) -> Dict[str, Dict[str, Any]]:
        """Snapshot C machine states."""
        snapshot: Dict[str, Dict[str, Any]] = {}
        for machine in self.env_C.machines.values():
            snapshot[str(machine.id)] = {
                "status": machine.status,
                "finish_time": machine.finish_time,
                "batch_size": machine.batch_size,
                "current_batch_uids": [task.uid for task in machine.current_batch],
            }
        return snapshot

    def _collect_all_tasks(self) -> Dict[int, Dict[str, Any]]:
        """Collect de-duplicated task snapshots across all queues/machines."""
        ordered_sources: List[Iterable[Task]] = [
            self.env_A.wait_pool,
            self.env_A.rework_pool,
            self._iter_machine_tasks(self.env_A.machines),
            self.env_B.wait_pool,
            self.env_B.rework_pool,
            self._iter_machine_tasks(self.env_B.machines),
            self.env_C.wait_pool,
            self._iter_machine_tasks(self.env_C.machines),
            self.env_C.completed_tasks,
            self.completed_tasks,
        ]

        seen: Dict[int, Dict[str, Any]] = {}
        for source in ordered_sources:
            for task in source:
                if task.uid in seen:
                    continue
                seen[task.uid] = self._snapshot_task(task)
        return seen

    def get_decision_state(self) -> Dict[str, Any]:
        """Return scheduler-facing state snapshot for external decision making.

        Returned structure (compact):
        - top: `time`, `max_steps`, `num_completed`, `tasks`
        - per process: `machines`, queue UID lists, queue stats
        - flow hints: `incoming_from_A_uids` and `incoming_from_B_uids`
        """
        tasks = self._collect_all_tasks()
        a_wait_uids = [task.uid for task in self.env_A.wait_pool]
        a_rework_uids = [task.uid for task in self.env_A.rework_pool]
        b_wait_uids = [task.uid for task in self.env_B.wait_pool]
        b_rework_uids = [task.uid for task in self.env_B.rework_pool]
        c_wait_uids = [task.uid for task in self.env_C.wait_pool]
        a_finishing_now_uids = self._finishing_now_uids(self.env_A.machines)
        b_finishing_now_uids = self._finishing_now_uids(self.env_B.machines)

        return {
            "time": self.time,
            "max_steps": self.config.get("max_steps", 1000),
            "num_completed": len(self.completed_tasks),
            "tasks": tasks,
            "A": {
                "machines": self._snapshot_machines_a(),
                "wait_pool_uids": a_wait_uids,
                "rework_pool_uids": a_rework_uids,
                "finishing_now_uids": a_finishing_now_uids,
                "queue_stats": {
                    "wait_pool_size": len(a_wait_uids),
                    "rework_pool_size": len(a_rework_uids),
                },
            },
            "B": {
                "machines": self._snapshot_machines_b(),
                "wait_pool_uids": b_wait_uids,
                "rework_pool_uids": b_rework_uids,
                "finishing_now_uids": b_finishing_now_uids,
                "incoming_from_A_uids": a_finishing_now_uids,
                "queue_stats": {
                    "wait_pool_size": len(b_wait_uids),
                    "rework_pool_size": len(b_rework_uids),
                },
            },
            "C": {
                "machines": self._snapshot_machines_c(),
                "wait_pool_uids": c_wait_uids,
                "incoming_from_B_uids": b_finishing_now_uids,
                "queue_stats": {"wait_pool_size": len(c_wait_uids)},
                "last_pack_time": self.env_C.last_pack_time,
                "pack_count": self.env_C.pack_count,
            },
        }

    def _calculate_reward(self, _res_A, _res_B, res_C) -> float:
        return len(res_C.get("completed", []))

    def _check_if_done(self) -> bool:
        """Stop condition based on max step horizon."""
        return self.time >= self.config.get("max_steps", 1000)


if __name__ == "__main__":
    from src.agents.factory import build_meta_scheduler

    env_config = {
        "num_machines_A": 2,
        "num_machines_B": 1,
        "num_machines_C": 1,
        "process_time_A": 15,
        "process_time_B": 10,
        "process_time_C": 20,
        "max_steps": 50,
    }

    env = ManufacturingEnv(env_config)
    meta = build_meta_scheduler(env.config)
    obs = env.reset()

    print("\n--- Initial state (t=0) ---")

    done = False
    total_reward = 0

    while not done:
        state = env.get_decision_state()
        actions = meta.decide(state)
        obs, reward, done, _ = env.step(actions)
        total_reward += reward
        print(
            f"--- t={obs['time']} | Reward: {reward} | Total Reward: {total_reward} "
            f"| Completed: {obs['num_completed']} ---"
        )

    print("\n--- Simulation finished ---")
    print(f"Final completed tasks: {obs['num_completed']}")
