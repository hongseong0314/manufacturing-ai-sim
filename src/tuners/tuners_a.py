# -*- coding: utf-8 -*-
"""Recipe tuners for process A."""

from typing import Any, Dict, List


class BaseRecipeTuner:
    """Recipe tuner interface for process A."""

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

    def should_replace_consumable(self, machine_state: Dict[str, Any]) -> bool:
        """Return True if consumable should be replaced before the next batch.

        Override this method to implement custom replacement policies
        (e.g., quality-triggered, predictive maintenance, schedule-based).
        Base implementation never replaces; concrete tuners provide logic.
        """
        _ = machine_state
        return False


class FIFOTuner(BaseRecipeTuner):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.default_recipe = list(config.get("default_recipe_A", [10.0, 2.0, 1.0]))

    def get_recipe(
        self,
        task_rows: List[Dict[str, Any]],
        machine_state: Dict[str, Any],
        queue_info: Dict[str, Any],
        current_time: int,
    ) -> List[float]:
        return list(self.default_recipe)

    def should_replace_consumable(self, machine_state: Dict[str, Any]) -> bool:
        u = float(machine_state.get("u", 0))
        threshold = self.config.get("consumable_replace_threshold", 10)
        return u >= threshold


class AdaptiveTuner(BaseRecipeTuner):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.u_fresh = config.get("u_fresh_threshold", 3)
        self.u_medium = config.get("u_medium_threshold", 7)
        self.recipe_library = {
            "fresh": list(config.get("recipe_a_fresh", [10.0, 2.0, 1.0])),
            "medium": list(config.get("recipe_a_medium", [12.0, 2.5, 1.2])),
            "old": list(config.get("recipe_a_old", [15.0, 3.0, 1.5])),
        }

    def _state_from_u(self, u: float) -> str:
        if u <= self.u_fresh:
            return "fresh"
        if u <= self.u_medium:
            return "medium"
        return "old"

    def get_recipe(
        self,
        task_rows: List[Dict[str, Any]],
        machine_state: Dict[str, Any],
        queue_info: Dict[str, Any],
        current_time: int,
    ) -> List[float]:
        machine_u = float(machine_state.get("u", 0))
        state_key = self._state_from_u(machine_u)
        return list(self.recipe_library.get(state_key, self.recipe_library["fresh"]))

    def should_replace_consumable(self, machine_state: Dict[str, Any]) -> bool:
        u = float(machine_state.get("u", 0))
        threshold = self.config.get("consumable_replace_threshold", 10)
        return u >= threshold


class RLBasedTuner(BaseRecipeTuner):
    """RL placeholder tuner for process A."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.fallback = FIFOTuner(config)

    def get_recipe(
        self,
        task_rows: List[Dict[str, Any]],
        machine_state: Dict[str, Any],
        queue_info: Dict[str, Any],
        current_time: int,
    ) -> List[float]:
        return self.fallback.get_recipe(task_rows, machine_state, queue_info, current_time)

    def should_replace_consumable(self, machine_state: Dict[str, Any]) -> bool:
        return self.fallback.should_replace_consumable(machine_state)
