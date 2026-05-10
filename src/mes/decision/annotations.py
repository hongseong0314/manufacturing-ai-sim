# -*- coding: utf-8 -*-
"""L2 candidate annotations and selected process actions."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

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


class CandidateAnnotationMixin:
    def annotate_candidate_portfolio(
        self,
        decision_state: Dict[str, Any],
        candidate_portfolio: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Attach L2 process annotations to every L1 candidate."""
        annotated: List[Dict[str, Any]] = []
        for candidate in candidate_portfolio:
            candidate_copy = dict(candidate)
            candidate_copy["l2_annotation"] = self.process_annotation_for_candidate(
                decision_state,
                candidate_copy,
            )
            annotated.append(candidate_copy)
        return annotated

    def process_annotation_for_candidate(
        self,
        decision_state: Dict[str, Any],
        candidate: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the L2 annotation contract for one candidate."""
        stage = str(candidate.get("stage", "")).upper()
        if stage == "A":
            return self._a_process_annotation(decision_state, candidate)
        if stage == "B":
            return self._b_process_annotation(candidate)
        if stage == "C":
            return self._c_process_annotation(candidate)
        return {
            "candidate_id": candidate.get("candidate_id"),
            "stage": stage,
            "quality_risk": "UNKNOWN",
            "selection_reason": "unknown_stage_process_annotation",
        }

    def process_action_for_selected_candidate(
        self,
        decision_state: Dict[str, Any],
        stage: str,
        dispatch_action: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the final L2 APC action through the factory policy stack."""
        stage = str(stage).upper()
        if stage == "A":
            return self._a_selected_process_action(decision_state, dispatch_action)
        if stage == "B":
            return self._b_selected_process_action(decision_state, dispatch_action)
        return self._c_selected_process_action(dispatch_action)

    def _task_row(self, decision_state: Dict[str, Any], uid: int) -> Dict[str, Any]:
        tasks = decision_state.get("tasks", {})
        row = tasks.get(uid) or tasks.get(str(uid))
        return dict(row) if isinstance(row, dict) else {}

    def _task_rows(
        self,
        decision_state: Dict[str, Any],
        task_uids: List[int],
    ) -> List[Dict[str, Any]]:
        return [row for uid in task_uids if (row := self._task_row(decision_state, uid))]

    def _a_process_annotation(
        self,
        decision_state: Dict[str, Any],
        candidate: Dict[str, Any],
    ) -> Dict[str, Any]:
        task_rows = self._task_rows(decision_state, candidate.get("task_uids", []))
        spec_low, spec_high = self._spec_window(task_rows, "spec_a", (47.1, 52.9))
        target = (spec_low + spec_high) / 2.0
        recipe = [10.0, 2.0, 1.0]
        predicted_qa = target
        return {
            "candidate_id": candidate.get("candidate_id"),
            "stage": "A",
            "recipe_id": "SIM_A_BASE",
            "recipe": recipe,
            "parameters": {"temp": recipe[0], "flow": recipe[1], "duration": recipe[2]},
            "replace_consumable": False,
            "predicted_qa": round(predicted_qa, 4),
            "target_spec": {"low": spec_low, "high": spec_high, "target": target},
            "apc_mode": "L2_PRESELECT_ANNOTATION",
            "apc_policy": "A_BASE_PRESELECT",
            "quality_risk": "LOW" if spec_low <= predicted_qa <= spec_high else "HIGH",
            "selection_reason": "a_candidate_process_annotation",
        }

    def _b_process_annotation(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        recipe = [50.0, 50.0, 30.0]
        return {
            "candidate_id": candidate.get("candidate_id"),
            "stage": "B",
            "recipe_id": "SIM_B_DEFAULT",
            "recipe": recipe,
            "parameters": {"chem_a": recipe[0], "chem_b": recipe[1], "time": recipe[2]},
            "replace_solution": False,
            "predicted_risk": "LOW",
            "apc_mode": "L2_PRESELECT_ANNOTATION",
            "quality_risk": "LOW",
            "selection_reason": "b_candidate_process_annotation",
        }

    def _c_process_annotation(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        features = dict(candidate.get("features", {}) or {})
        compatibility = float(features.get("compatibility", 0.0) or 0.0)
        if compatibility >= 0.9:
            quality_risk = "LOW"
        elif compatibility >= 0.75:
            quality_risk = "MEDIUM"
        else:
            quality_risk = "HIGH"
        return {
            "candidate_id": candidate.get("candidate_id"),
            "stage": "C",
            "recipe_id": "SIM_C_NO_RECIPE",
            "recipe": [],
            "pack_quality_prediction": features.get("avg_quality"),
            "compatibility": compatibility,
            "pack_mode": "STANDARD",
            "quality_risk": quality_risk,
            "apc_mode": "L2_PRESELECT_ANNOTATION",
            "selection_reason": "c_candidate_process_annotation",
        }

    def _a_selected_process_action(
        self,
        decision_state: Dict[str, Any],
        dispatch_action: Dict[str, Any],
    ) -> Dict[str, Any]:
        machine_state = self._machine_state(
            decision_state,
            "A",
            str(dispatch_action.get("equipment_id", "")),
        )
        task_rows = self._task_rows(decision_state, dispatch_action.get("task_uids", []))
        spec_low, spec_high = self._spec_window(task_rows, "spec_a", (47.1, 52.9))
        target = (spec_low + spec_high) / 2.0
        recipe = self.policy_stack.tuner_a.get_recipe(
            task_rows=task_rows,
            machine_state=machine_state,
            queue_info={
                "wait_pool_size": len(decision_state.get("A", {}).get("wait_pool_uids", [])),
                "rework_pool_size": len(decision_state.get("A", {}).get("rework_pool_uids", [])),
            },
            current_time=int(decision_state.get("time", 0) or 0),
        )
        replace_consumable = self.policy_stack.tuner_a.should_replace_consumable(
            machine_state,
        )
        current_u = float(machine_state.get("u", 0))
        current_age = float(machine_state.get("m_age", 0))
        predicted_qa = self._predict_a_qa(
            recipe=recipe,
            current_u=current_u,
            current_age=current_age,
            replace_consumable=replace_consumable,
        )
        return {
            "candidate_id": dispatch_action.get("candidate_id"),
            "recipe_id": self._a_recipe_id(recipe),
            "recipe": recipe,
            "parameters": {"temp": recipe[0], "flow": recipe[1], "duration": recipe[2]},
            "replace_consumable": bool(replace_consumable),
            "apc_mode": "L1L2_COMPOSED",
            "apc_policy": "A_RULE_BASED_TUNER",
            "policy_source": self._l2_policy_source("A"),
            "predicted_qa": round(float(predicted_qa), 4),
            "target_spec": {"low": spec_low, "high": spec_high, "target": target},
            "machine_state": {"u": current_u, "m_age": current_age},
            "quality_risk": "LOW" if spec_low <= predicted_qa <= spec_high else "HIGH",
            "selection_reason": "factory_rule_based_apc_for_selected_candidate",
        }

    def _b_selected_process_action(
        self,
        decision_state: Dict[str, Any],
        dispatch_action: Dict[str, Any],
    ) -> Dict[str, Any]:
        machine_state = self._machine_state(
            decision_state,
            "B",
            str(dispatch_action.get("equipment_id", "")),
        )
        task_rows = self._task_rows(decision_state, dispatch_action.get("task_uids", []))
        recipe = self.policy_stack.tuner_b.get_recipe(
            task_rows=task_rows,
            machine_state=machine_state,
            queue_info={
                "wait_pool_size": len(decision_state.get("B", {}).get("wait_pool_uids", [])),
                "rework_pool_size": len(decision_state.get("B", {}).get("rework_pool_uids", [])),
            },
            current_time=int(decision_state.get("time", 0) or 0),
        )
        return {
            "candidate_id": dispatch_action.get("candidate_id"),
            "recipe_id": "SIM_B_RULE_BASED",
            "recipe": recipe,
            "parameters": {"chem_a": recipe[0], "chem_b": recipe[1], "time": recipe[2]},
            "replace_solution": bool(
                self.policy_stack.tuner_b.should_replace_solution(machine_state)
            ),
            "apc_mode": "L1L2_COMPOSED",
            "apc_policy": "B_RULE_BASED_TUNER",
            "policy_source": self._l2_policy_source("B"),
            "quality_risk": "LOW",
            "selection_reason": "factory_rule_based_apc_for_selected_candidate",
        }

    def _c_selected_process_action(
        self,
        dispatch_action: Dict[str, Any],
    ) -> Dict[str, Any]:
        features = dict(dispatch_action.get("features", {}) or {})
        compatibility = float(features.get("compatibility", 0.0) or 0.0)
        return {
            "candidate_id": dispatch_action.get("candidate_id"),
            "recipe_id": "SIM_C_NO_RECIPE",
            "recipe": [],
            "apc_mode": "L1L2_COMPOSED",
            "apc_policy": "C_RULE_BASED_PACK_QUALITY",
            "policy_source": self._l2_policy_source("C"),
            "pack_quality_prediction": features.get("avg_quality"),
            "compatibility": compatibility,
            "pack_mode": "STANDARD",
            "quality_risk": "LOW" if compatibility >= 0.8 else "MEDIUM",
            "selection_reason": "factory_rule_based_apc_for_selected_candidate",
        }

    def _l2_policy_source(self, stage: str) -> Dict[str, str]:
        if stage == "A":
            policy = str(self.policy_stack.config.get("tuner_A", "rule-based"))
        elif stage == "B":
            policy = str(self.policy_stack.config.get("tuner_B", "rule-based"))
        else:
            policy = "rule-based"
        return {
            "factory": self.policy_stack.factory_name,
            "l2_policy_id": self.policy_stack.l2_policy_id,
            "apc_policy": policy,
        }

    def _a_recipe_id(self, recipe: List[float]) -> str:
        known = {
            (10.0, 2.0, 1.0): "SIM_A_BASE",
            (12.0, 2.5, 1.2): "SIM_A_MEDIUM_APC",
            (15.0, 3.0, 1.5): "SIM_A_STRONG_APC",
            (18.0, 4.0, 2.0): "SIM_A_AGE_APC",
        }
        key = tuple(float(value) for value in recipe)
        return known.get(key, "SIM_A_RULE_BASED")

    def _machine_state(
        self,
        decision_state: Dict[str, Any],
        stage: str,
        equipment_id: str,
    ) -> Dict[str, Any]:
        machines = decision_state.get(stage, {}).get("machines", {})
        if equipment_id in machines and isinstance(machines[equipment_id], dict):
            return machines[equipment_id]
        suffix = equipment_id.split("_")[-1]
        for machine_id, machine_state in machines.items():
            if (
                str(machine_id).split("_")[-1] == suffix
                and isinstance(machine_state, dict)
            ):
                return machine_state
        return {}

    def _predict_a_qa(
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
