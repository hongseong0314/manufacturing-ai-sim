# -*- coding: utf-8 -*-
from typing import Any, Dict, List, Optional, Set

from src.data_generator import DataGenerator
from src.environment.process_a_env import ProcessA_Env
from src.environment.process_b_env import ProcessB_Env
from src.environment.process_c_env import ProcessC_Env
from src.objects import Task
from src.schedulers.packers_c import FIFOPacker, GreedyScorePacker, RandomPacker
from src.schedulers.schedulers_a import AdaptiveScheduler, FIFOScheduler, RLBasedScheduler as ARLBasedScheduler
from src.schedulers.schedulers_b import (
    FIFOBaseline,
    RLBasedScheduler as BRLBasedScheduler,
    RuleBasedScheduler,
)


class ManufacturingEnv:
    """Top-level orchestrator integrating process A/B/C.

    Decision policy lives here:
    - Build default actions using schedulers/packer when process action is omitted.
    - Respect external process actions as an explicit override.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = self._normalize_config(config)
        self.time = 0
        self.data_generator = DataGenerator()
        self._periodic_enabled = True

        self.env_A = ProcessA_Env(self.config)
        self.env_B = ProcessB_Env(self.config)
        self.env_C = ProcessC_Env(self.config)

        self.scheduler_A = self._build_scheduler_a(self.config)
        self.scheduler_B = self._build_scheduler_b(self.config)
        self.packer_C = self._build_packer_c(self.config)

        self.completed_tasks: List[Task] = []

    def _normalize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
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

    def _build_scheduler_a(self, config: Dict[str, Any]):
        scheduler_type = config.get("scheduler_A", "fifo")
        if scheduler_type == "fifo":
            return FIFOScheduler(config)
        if scheduler_type == "adaptive":
            return AdaptiveScheduler(config)
        if scheduler_type == "rl":
            return ARLBasedScheduler(config)
        return FIFOScheduler(config)

    def _build_scheduler_b(self, config: Dict[str, Any]):
        scheduler_type = config.get("scheduler_B", "rule-based")
        if scheduler_type == "fifo":
            return FIFOBaseline(config)
        if scheduler_type == "rule-based":
            return RuleBasedScheduler(config)
        if scheduler_type == "rl":
            return BRLBasedScheduler(config)
        return RuleBasedScheduler(config)

    def _build_packer_c(self, config: Dict[str, Any]):
        packing_strategy = config.get("packing_C", "greedy")
        if packing_strategy == "fifo":
            return FIFOPacker(config)
        if packing_strategy == "random":
            return RandomPacker(config)
        if packing_strategy == "greedy":
            return GreedyScorePacker(config)
        return GreedyScorePacker(config)

    def _plan_batch_actions(self, env, scheduler) -> Dict[str, Dict[str, Any]]:
        planned: Dict[str, Dict[str, Any]] = {}
        allocated_uids: Set[int] = set()

        for machine in env.machines.values():
            if machine.status != "idle":
                continue

            wait_candidates = [task for task in env.wait_pool if task.uid not in allocated_uids]
            rework_candidates = [task for task in env.rework_pool if task.uid not in allocated_uids]

            if not wait_candidates and not rework_candidates:
                continue

            queue_info = {
                "wait_pool_size": len(wait_candidates),
                "rework_pool_size": len(rework_candidates),
                "rework_queue_size": len(rework_candidates),
            }

            # Use copied pools so planner decision does not mutate env state.
            batch, task_type = scheduler.select_batch(
                list(wait_candidates),
                list(rework_candidates),
                machine.batch_size,
            )
            if not batch:
                continue

            recipe = scheduler.get_recipe(batch[0], machine, queue_info)
            task_uids = [task.uid for task in batch]
            allocated_uids.update(task_uids)

            planned[machine.id] = {
                "task_uids": task_uids,
                "recipe": recipe,
                "task_type": task_type or "planned",
            }

        return planned

    def _plan_actions_a(self) -> Dict[str, Dict[str, Any]]:
        return self._plan_batch_actions(self.env_A, self.scheduler_A)

    def _plan_actions_b(self) -> Dict[str, Dict[str, Any]]:
        return self._plan_batch_actions(self.env_B, self.scheduler_B)

    def _plan_actions_c(self) -> Dict[str, Dict[str, Any]]:
        should_pack, reason = self.packer_C.should_pack(
            self.env_C.wait_pool,
            self.time,
            self.env_C.last_pack_time,
        )
        force_timeout_pack = False
        if not should_pack and self.env_C.wait_pool:
            oldest_arrival = min(
                getattr(task, "arrival_time", self.time) for task in self.env_C.wait_pool
            )
            force_timeout_pack = (
                self.time - oldest_arrival > self.packer_C.max_wait_time
            )

        if not should_pack and not force_timeout_pack:
            return {}

        # Use copied pool so planner decision does not mutate env state.
        selected_pack = self.packer_C.select_pack(list(self.env_C.wait_pool), self.time)
        if not selected_pack:
            return {}

        machine_id = "C_0"
        if self.env_C.machines:
            machine_id = next(iter(self.env_C.machines.values())).id

        return {
            machine_id: {
                "task_uids": [task.uid for task in selected_pack],
                "reason": reason if should_pack else "timeout_fallback",
            }
        }

    def _step_a(self, incoming_actions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        # External action is authoritative for this process.
        if "A" in incoming_actions:
            return self.env_A.step(self.time, incoming_actions.get("A") or {})

        # Phase 1: complete ongoing work at this tick.
        results_a = self.env_A.step(self.time, {})
        # Phase 2: plan and assign at the same tick to avoid artificial 1-tick idle gaps.
        planned_a = self._plan_actions_a()
        if planned_a:
            self.env_A.step(self.time, planned_a)
        return results_a

    def _step_b(self, incoming_actions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        if "B" in incoming_actions:
            return self.env_B.step(self.time, incoming_actions.get("B") or {})

        results_b = self.env_B.step(self.time, {})
        planned_b = self._plan_actions_b()
        if planned_b:
            self.env_B.step(self.time, planned_b)
        return results_b

    def _step_c(self, incoming_actions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        if "C" in incoming_actions:
            return self.env_C.step(self.time, incoming_actions.get("C") or {})
        planned_c = self._plan_actions_c()
        return self.env_C.step(self.time, planned_c)

    def step(self, actions: Optional[Dict[str, Dict[str, Any]]] = None):
        incoming_actions = actions if isinstance(actions, dict) else {}

        # 1) Process A step.
        results_A = self._step_a(incoming_actions)
        if results_A["succeeded"]:
            self.env_B.add_tasks(results_A["succeeded"])

        # 2) Process B step.
        results_B = self._step_b(incoming_actions)
        if results_B["succeeded"]:
            self.env_C.add_tasks(results_B["succeeded"], current_time=self.time)

        # 3) Process C step.
        results_C = self._step_c(incoming_actions)
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
        return {
            "time": self.time,
            "A_state": self.env_A.get_state(),
            "B_state": self.env_B.get_state(),
            "C_state": self.env_C.get_state(),
            "num_completed": len(self.completed_tasks),
        }

    def _calculate_reward(self, res_A, res_B, res_C) -> float:
        return len(res_C.get("completed", []))

    def _check_if_done(self) -> bool:
        return self.time >= self.config.get("max_steps", 1000)


if __name__ == "__main__":
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
    obs = env.reset()

    print("\n--- Initial state (t=0) ---")

    done = False
    total_reward = 0

    while not done:
        # Empty action means "use default external scheduler/packer decisions"
        # configured in ManufacturingEnv.
        obs, reward, done, _ = env.step({})
        total_reward += reward
        print(
            f"--- t={obs['time']} | Action: auto(planner) "
            f"| Reward: {reward} | Total Reward: {total_reward} "
            f"| Completed: {obs['num_completed']} ---"
        )

    print("\n--- Simulation finished ---")
    print(f"Final completed tasks: {obs['num_completed']}")
