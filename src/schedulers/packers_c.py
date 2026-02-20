# -*- coding: utf-8 -*-
"""Packers for process C."""

from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.objects import Task


class BasePacker:
    """Packing policy interface for process C."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        try:
            batch_size = int(config.get("batch_size_C", config.get("N_pack", 4)))
        except (TypeError, ValueError):
            batch_size = 4
        self.batch_size = max(1, batch_size)
        self.N_pack = self.batch_size
        self.max_wait_time = config.get("max_wait_time", 30)
        # Keep queue threshold consistent with batch rule.
        try:
            min_queue_size = int(config.get("min_queue_size", self.batch_size))
        except (TypeError, ValueError):
            min_queue_size = self.batch_size
        self.min_queue_size = min(max(1, min_queue_size), self.batch_size)

    def should_pack(
        self,
        wait_pool: List[Task],
        current_time: int,
        last_pack_time: int,
    ) -> Tuple[bool, str]:
        """Return `(should_pack, reason)` for the current queue state."""
        raise NotImplementedError

    def select_pack(self, wait_pool: List[Task], current_time: int) -> Optional[List[Task]]:
        """Select a concrete pack (task list) from queue candidates."""
        raise NotImplementedError


class FIFOPacker(BasePacker):
    def should_pack(
        self,
        wait_pool: List[Task],
        current_time: int,
        last_pack_time: int,
    ) -> Tuple[bool, str]:
        if len(wait_pool) < self.min_queue_size:
            return False, "queue_too_small"

        if wait_pool:
            oldest_task = min(wait_pool, key=lambda task: getattr(task, "arrival_time", 0))
            wait_duration = current_time - getattr(oldest_task, "arrival_time", 0)
            if wait_duration > self.max_wait_time:
                return True, "timeout"

        if len(wait_pool) >= self.batch_size:
            return True, "batch_ready"

        return False, "waiting"

    def select_pack(self, wait_pool: List[Task], current_time: int) -> Optional[List[Task]]:
        if len(wait_pool) < self.batch_size:
            return None
        pack = wait_pool[: self.batch_size]
        print(f"    [FIFO] Pack selected: {[task.uid for task in pack]}")
        return pack


class RandomPacker(BasePacker):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.random_seed = config.get("random_seed", None)

    def should_pack(
        self,
        wait_pool: List[Task],
        current_time: int,
        last_pack_time: int,
    ) -> Tuple[bool, str]:
        if len(wait_pool) < self.min_queue_size:
            return False, "queue_too_small"

        if wait_pool:
            oldest_task = min(wait_pool, key=lambda task: getattr(task, "arrival_time", 0))
            wait_duration = current_time - getattr(oldest_task, "arrival_time", 0)
            if wait_duration > self.max_wait_time:
                return True, "timeout"

        if len(wait_pool) >= self.batch_size:
            return True, "batch_ready"

        return False, "waiting"

    def select_pack(self, wait_pool: List[Task], current_time: int) -> Optional[List[Task]]:
        if len(wait_pool) < self.batch_size:
            return None

        if self.random_seed is not None:
            np.random.seed(self.random_seed)

        indices = np.random.choice(len(wait_pool), self.batch_size, replace=False)
        pack = [wait_pool[i] for i in sorted(indices)]
        print(f"    [RANDOM] Pack selected: {[task.uid for task in pack]}")
        return pack


class GreedyScorePacker(BasePacker):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.alpha_quality = config.get("alpha_quality", 1.0)
        self.beta_compat = config.get("beta_compat", 0.5)
        self.gamma_margin = config.get("gamma_margin", 0.3)
        self.delta_time = config.get("delta_time", 0.2)
        self.compatibility_matrix = self._init_compatibility_matrix()
        self.K_candidates = config.get("K_candidates", 15)

    def _init_compatibility_matrix(self) -> Dict[Tuple[str, str], float]:
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

    def should_pack(
        self,
        wait_pool: List[Task],
        current_time: int,
        last_pack_time: int,
    ) -> Tuple[bool, str]:
        if len(wait_pool) < self.min_queue_size:
            return False, "queue_too_small"

        if wait_pool:
            oldest_task = min(wait_pool, key=lambda task: getattr(task, "arrival_time", 0))
            wait_duration = current_time - getattr(oldest_task, "arrival_time", 0)
            if wait_duration > self.max_wait_time:
                return True, "timeout"

        if len(wait_pool) >= self.batch_size:
            return True, "batch_ready"

        return False, "waiting"

    def select_pack(self, wait_pool: List[Task], current_time: int) -> Optional[List[Task]]:
        if len(wait_pool) < self.batch_size:
            return None

        top_k = min(self.K_candidates, len(wait_pool))
        candidates = sorted(
            wait_pool,
            key=lambda task: getattr(task, "realized_qa_B", 50),
            reverse=True,
        )[:top_k]

        best_score = -float("inf")
        best_combo = None
        for combo in combinations(candidates, self.batch_size):
            score = self._compute_score(list(combo), current_time)
            if score > best_score:
                best_score = score
                best_combo = list(combo)

        if best_combo:
            print(
                f"    [GREEDY] Pack selected: {[task.uid for task in best_combo]}, "
                f"score={best_score:.2f}"
            )
            return best_combo
        return None

    def _compute_score(self, tasks: List[Task], current_time: int) -> float:
        quality_score = np.mean([getattr(task, "realized_qa_B", 50) for task in tasks])
        compat_score = self._compute_compatibility(tasks)
        margin_score = np.mean([getattr(task, "margin_value", 0.5) for task in tasks]) * 100
        time_penalty = self._compute_time_penalty(tasks, current_time)

        return (
            self.alpha_quality * quality_score
            + self.beta_compat * compat_score * 100
            + self.gamma_margin * margin_score
            - self.delta_time * time_penalty
        )

    def _compute_compatibility(self, tasks: List[Task]) -> float:
        if len(tasks) < 2:
            return 1.0

        compat_product = 1.0
        for i, task_i in enumerate(tasks):
            for task_j in tasks[i + 1 :]:
                compat_product *= self._get_pairwise_compat(task_i, task_j)

        n_pairs = len(tasks) * (len(tasks) - 1) / 2
        if n_pairs > 0:
            return compat_product ** (1 / n_pairs)
        return 1.0

    def _get_pairwise_compat(self, task_i: Task, task_j: Task) -> float:
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

    def _compute_time_penalty(self, tasks: List[Task], current_time: int) -> float:
        max_due = max([getattr(task, "due_date", current_time + 100) for task in tasks])
        return max(0, current_time - max_due)
