# -*- coding: utf-8 -*-
"""Recipe tuners for process B."""

from typing import Any, Dict, List, Tuple


class BaseRecipeTuner:
    """Recipe tuner interface for process B."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def get_recipe(
        self,
        task_rows: List[Dict[str, Any]],
        machine_state: Dict[str, Any],
        queue_info: Dict[str, Any],
        current_time: int,
    ) -> List[float]:
        """Return recipe vector for the selected batch and machine state."""
        raise NotImplementedError


class FIFOTuner(BaseRecipeTuner):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.default_recipe = list(config.get("default_recipe_B", [50.0, 50.0, 30.0]))

    def get_recipe(
        self,
        task_rows: List[Dict[str, Any]],
        machine_state: Dict[str, Any],
        queue_info: Dict[str, Any],
        current_time: int,
    ) -> List[float]:
        return list(self.default_recipe)


class RuleBasedTuner(BaseRecipeTuner):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.v_fresh = config.get("v_fresh_threshold", 5)
        self.v_medium = config.get("v_medium_threshold", 15)
        self.b_age_new = config.get("b_age_new_threshold", 10)
        self.b_age_medium = config.get("b_age_medium_threshold", 50)
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

    def _solution_state(self, v: float) -> str:
        if v <= self.v_fresh:
            return "fresh"
        if v <= self.v_medium:
            return "medium"
        return "old"

    def _machine_state(self, b_age: int) -> str:
        if b_age <= self.b_age_new:
            return "new"
        if b_age <= self.b_age_medium:
            return "medium"
        return "old"

    def _adjust_by_spec(self, recipe: List[float], spec_b: Tuple[float, float]) -> List[float]:
        min_b, max_b = spec_b
        mid_spec = (float(min_b) + float(max_b)) / 2.0
        if mid_spec > 60:
            factor = 1.1
        elif mid_spec < 40:
            factor = 0.9
        else:
            factor = 1.0
        return [float(value) * factor for value in recipe]

    def get_recipe(
        self,
        task_rows: List[Dict[str, Any]],
        machine_state: Dict[str, Any],
        queue_info: Dict[str, Any],
        current_time: int,
    ) -> List[float]:
        solution_state = self._solution_state(float(machine_state.get("v", 0)))
        machine_age_state = self._machine_state(int(machine_state.get("b_age", 0)))
        recipe = list(self.recipe_library.get((solution_state, machine_age_state), [50.0, 50.0, 30.0]))
        if not task_rows:
            return recipe

        spec_b_raw = task_rows[0].get("spec_b", (20.0, 80.0))
        spec_b = (float(spec_b_raw[0]), float(spec_b_raw[1]))
        return self._adjust_by_spec(recipe, spec_b)


class RLBasedTuner(BaseRecipeTuner):
    """RL placeholder tuner for process B."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.fallback = RuleBasedTuner(config)

    def get_recipe(
        self,
        task_rows: List[Dict[str, Any]],
        machine_state: Dict[str, Any],
        queue_info: Dict[str, Any],
        current_time: int,
    ) -> List[float]:
        return self.fallback.get_recipe(task_rows, machine_state, queue_info, current_time)
