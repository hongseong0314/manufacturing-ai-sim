# -*- coding: utf-8 -*-
"""Schedulers for process B."""

from typing import Any, Dict, List, Optional, Tuple

from src.objects import ProcessB_Machine, Task


class BaseScheduler:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.process_time = config.get("process_time_B", 4)

    def should_schedule(self) -> bool:
        raise NotImplementedError

    def get_recipe(
        self,
        task: Task,
        machine: ProcessB_Machine,
        queue_info: Dict[str, Any],
    ) -> List[float]:
        raise NotImplementedError

    def select_task(
        self,
        wait_pool: List[Task],
        rework_pool: List[Task],
    ) -> Optional[Tuple[Task, str]]:
        raise NotImplementedError

    def select_batch(
        self,
        wait_pool: List[Task],
        rework_pool: List[Task],
        batch_size: int,
    ) -> Optional[Tuple[List[Task], str]]:
        raise NotImplementedError


class FIFOBaseline(BaseScheduler):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.default_recipe = config.get("default_recipe_B", [50.0, 50.0, 30.0])

    def should_schedule(self) -> bool:
        return True

    def get_recipe(
        self,
        task: Task,
        machine: ProcessB_Machine,
        queue_info: Dict[str, Any],
    ) -> List[float]:
        return self.default_recipe

    def select_task(
        self,
        wait_pool: List[Task],
        rework_pool: List[Task],
    ) -> Optional[Tuple[Task, str]]:
        if rework_pool:
            return rework_pool.pop(0), "rework"
        if wait_pool:
            return wait_pool.pop(0), "new"
        return None, None

    def select_batch(
        self,
        wait_pool: List[Task],
        rework_pool: List[Task],
        batch_size: int,
    ) -> Optional[Tuple[List[Task], str]]:
        batch: List[Task] = []
        task_type = None

        while len(batch) < batch_size and rework_pool:
            batch.append(rework_pool.pop(0))
            task_type = "rework"

        while len(batch) < batch_size and wait_pool:
            batch.append(wait_pool.pop(0))
            if task_type is None:
                task_type = "new"

        if not batch:
            return None, None
        return batch, task_type


class RuleBasedScheduler(BaseScheduler):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.v_fresh = 5
        self.v_medium = 15
        self.v_old = 20

        self.b_age_new = 10
        self.b_age_medium = 50
        self.b_age_old = 100

        self.recipe_library = {
            ("fresh", "new"): [40.0, 45.0, 25.0],
            ("fresh", "medium"): [50.0, 50.0, 30.0],
            ("fresh", "old"): [60.0, 55.0, 35.0],
            ("medium", "new"): [50.0, 50.0, 30.0],
            ("medium", "medium"): [55.0, 55.0, 35.0],
            ("medium", "old"): [65.0, 60.0, 40.0],
            ("old", "new"): [60.0, 55.0, 35.0],
            ("old", "medium"): [70.0, 65.0, 45.0],
            ("old", "old"): [80.0, 70.0, 50.0],
        }

    def should_schedule(self) -> bool:
        return True

    def _get_solution_state(self, v: float) -> str:
        if v <= self.v_fresh:
            return "fresh"
        if v <= self.v_medium:
            return "medium"
        return "old"

    def _get_machine_state(self, b_age: int) -> str:
        if b_age <= self.b_age_new:
            return "new"
        if b_age <= self.b_age_medium:
            return "medium"
        return "old"

    def get_recipe(
        self,
        task: Task,
        machine: ProcessB_Machine,
        queue_info: Dict[str, Any],
    ) -> List[float]:
        solution_state = self._get_solution_state(machine.v)
        machine_state = self._get_machine_state(machine.b_age)
        base_recipe = self.recipe_library.get((solution_state, machine_state), [50.0, 50.0, 30.0])
        return self._adjust_by_spec(base_recipe, task.spec_b)

    def _adjust_by_spec(self, recipe: List[float], spec_b: Tuple[float, float]) -> List[float]:
        min_b, max_b = spec_b
        mid_spec = (min_b + max_b) / 2.0

        if mid_spec > 60:
            adjustment = 1.1
        elif mid_spec < 40:
            adjustment = 0.9
        else:
            adjustment = 1.0
        return [value * adjustment for value in recipe]

    def select_task(
        self,
        wait_pool: List[Task],
        rework_pool: List[Task],
    ) -> Optional[Tuple[Task, str]]:
        if rework_pool:
            return rework_pool.pop(0), "rework"
        if wait_pool:
            return wait_pool.pop(0), "new"
        return None, None

    def select_batch(
        self,
        wait_pool: List[Task],
        rework_pool: List[Task],
        batch_size: int,
    ) -> Optional[Tuple[List[Task], str]]:
        batch: List[Task] = []
        task_type = None

        while len(batch) < batch_size and rework_pool:
            batch.append(rework_pool.pop(0))
            task_type = "rework"

        while len(batch) < batch_size and wait_pool:
            batch.append(wait_pool.pop(0))
            if task_type is None:
                task_type = "new"

        if not batch:
            return None, None
        return batch, task_type


class RLBasedScheduler(BaseScheduler):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.fallback = RuleBasedScheduler(config)

    def should_schedule(self) -> bool:
        return True

    def get_recipe(
        self,
        task: Task,
        machine: ProcessB_Machine,
        queue_info: Dict[str, Any],
    ) -> List[float]:
        return self.fallback.get_recipe(task, machine, queue_info)

    def select_task(
        self,
        wait_pool: List[Task],
        rework_pool: List[Task],
    ) -> Optional[Tuple[Task, str]]:
        return self.fallback.select_task(wait_pool, rework_pool)

    def select_batch(
        self,
        wait_pool: List[Task],
        rework_pool: List[Task],
        batch_size: int,
    ) -> Optional[Tuple[List[Task], str]]:
        return self.fallback.select_batch(wait_pool, rework_pool, batch_size)
