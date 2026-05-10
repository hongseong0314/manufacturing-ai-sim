# -*- coding: utf-8 -*-
"""Recipe tuners for process A."""

import math
from typing import Any, Dict, List

from src.environment.process_a_env import (
    BETA,
    BETA_K,
    B_BASE,
    DELTA_B,
    DELTA_W1,
    DELTA_W12,
    W12_BASE,
    W1_BASE,
    W2_BASE,
    W3_BASE,
)


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


class RuleBasedTuner(BaseRecipeTuner):
    """Rule-based APC tuner for process A.

    This is intentionally deterministic: evaluate a small recipe grid against
    the batch spec window and machine state, then choose the lowest-risk recipe.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.recipes = [
            list(config.get("recipe_a_base", [10.0, 2.0, 1.0])),
            list(config.get("recipe_a_medium", [12.0, 2.5, 1.2])),
            list(config.get("recipe_a_strong", [15.0, 3.0, 1.5])),
            list(config.get("recipe_a_age", [18.0, 4.0, 2.0])),
        ]

    def get_recipe(
        self,
        task_rows: List[Dict[str, Any]],
        machine_state: Dict[str, Any],
        queue_info: Dict[str, Any],
        current_time: int,
    ) -> List[float]:
        _ = queue_info, current_time
        spec_low, spec_high = self._spec_window(task_rows, "spec_a", (47.1, 52.9))
        target = (spec_low + spec_high) / 2.0
        current_u = float(machine_state.get("u", 0))
        current_age = float(machine_state.get("m_age", 0))
        replace_consumable = self.should_replace_consumable(machine_state)

        candidates = []
        for recipe in self.recipes:
            predicted_qa = self._predict_qa(
                recipe=recipe,
                current_u=current_u,
                current_age=current_age,
                replace_consumable=replace_consumable,
            )
            in_spec = spec_low <= predicted_qa <= spec_high
            distance = (
                abs(predicted_qa - target)
                if in_spec
                else min(abs(predicted_qa - spec_low), abs(predicted_qa - spec_high)) + 100.0
            )
            recipe_penalty = 0.02 * sum(recipe)
            candidates.append((distance + recipe_penalty, recipe))
        return list(min(candidates, key=lambda item: item[0])[1])

    def should_replace_consumable(self, machine_state: Dict[str, Any]) -> bool:
        u = float(machine_state.get("u", 0))
        threshold = self.config.get("rule_based_consumable_replace_threshold", 5)
        return u >= threshold

    def _spec_window(
        self,
        task_rows: List[Dict[str, Any]],
        key: str,
        default: tuple[float, float],
    ) -> tuple[float, float]:
        lows = []
        highs = []
        for row in task_rows:
            spec = row.get(key)
            if not isinstance(spec, (list, tuple)) or len(spec) != 2:
                continue
            lows.append(float(spec[0]))
            highs.append(float(spec[1]))
        if not lows or not highs:
            return default
        return max(lows), min(highs)

    def _predict_qa(
        self,
        recipe: List[float],
        current_u: float,
        current_age: float,
        replace_consumable: bool,
    ) -> float:
        s1, s2, s3 = recipe
        expected_u = 1.0 if replace_consumable else current_u + 1.0
        expected_age = current_age + 1.0
        w1 = W1_BASE * (1 - DELTA_W1 * expected_age)
        w12 = W12_BASE * (1 - DELTA_W12 * expected_age)
        b = B_BASE - DELTA_B * expected_age
        g_s = (w1 * s1 + W2_BASE * s2 + W3_BASE * s3 + b) + (w12 * s1 * s2)
        effectiveness = 1 - BETA * math.tanh(BETA_K * expected_u)
        return float(g_s * effectiveness)


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
