# -*- coding: utf-8 -*-
"""Rule validation for MES recommendation envelopes."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from src.mes.adapters import stage_from_equipment_id, task_uid_from_wafer_id
from src.mes.domain import AIRecommendation, RuleValidationResult


class MESRuleEngine:
    """Validate recommendation envelopes before simulator command execution."""

    def validate_recommendations(
        self,
        decision_state: Dict[str, Any],
        recommendations: Sequence[AIRecommendation],
    ) -> RuleValidationResult:
        if not recommendations:
            return RuleValidationResult("REJECTED", reasons=["NO_RECOMMENDATIONS"])

        envelopes = [self._as_dict(rec) for rec in recommendations]
        correlation_id = str(envelopes[0].get("correlation_id", ""))
        if not correlation_id:
            return RuleValidationResult("REJECTED", reasons=["MISSING_CORRELATION_ID"])

        if any(str(rec.get("correlation_id", "")) != correlation_id for rec in envelopes):
            return RuleValidationResult(
                "REJECTED",
                correlation_id=correlation_id,
                reasons=["CORRELATION_ID_MISMATCH"],
            )

        dispatch_rec = self._find_recommendation(envelopes, {"DISPATCH", "PACK"}, "L1")
        if dispatch_rec is None:
            return RuleValidationResult(
                "REJECTED",
                correlation_id=correlation_id,
                reasons=["MISSING_L1_DISPATCH_RECOMMENDATION"],
            )

        stage_rec = self._find_recommendation(envelopes, {"STAGE_PRIORITY"}, "L3")
        recipe_rec = self._find_recommendation(
            envelopes,
            {"RECIPE", "MAINTENANCE"},
            "L2",
        )
        action = dict(dispatch_rec.get("recommended_action") or {})
        equipment_id = str(action.get("equipment_id", ""))
        stage = str(action.get("stage") or stage_from_equipment_id(equipment_id) or "")
        task_uids = self._extract_task_uids(action)

        reasons: List[str] = []
        if stage not in {"A", "B", "C"}:
            reasons.append("UNKNOWN_STAGE")
        if not equipment_id:
            reasons.append("MISSING_EQUIPMENT_ID")
        if not task_uids:
            reasons.append("MISSING_TASK_UIDS")
        self._check_candidate_consistency(
            stage_rec=stage_rec,
            dispatch_rec=dispatch_rec,
            recipe_rec=recipe_rec,
            action=action,
            reasons=reasons,
        )

        stage_state = decision_state.get(stage, {}) if stage else {}
        machine_state = self._find_machine(stage_state, equipment_id)
        if machine_state is None:
            reasons.append("EQUIPMENT_NOT_FOUND")
        elif not self._is_machine_available(machine_state, decision_state):
            reasons.append("EQUIPMENT_NOT_AVAILABLE")

        available_uids = self._available_task_uids(stage, stage_state)
        missing_uids = [uid for uid in task_uids if uid not in available_uids]
        if missing_uids:
            reasons.append("TASK_NOT_AVAILABLE")

        if reasons:
            return RuleValidationResult(
                "REJECTED",
                correlation_id=correlation_id,
                reasons=reasons,
            )

        command = {
            "command_type": "RESERVE_AND_TRACK_IN",
            "correlation_id": correlation_id,
            "stage": stage,
            "equipment_id": equipment_id,
            "task_uids": task_uids,
            "task_type": action.get("task_type", "new"),
            "dispatch_recommendation_id": dispatch_rec.get("recommendation_id"),
        }
        if action.get("candidate_id"):
            command["candidate_id"] = action.get("candidate_id")
        if action.get("reason"):
            command["reason"] = action.get("reason")
        if recipe_rec is not None:
            command["recipe_recommendation_id"] = recipe_rec.get("recommendation_id")
            command.update(self._recipe_command_fields(recipe_rec))

        return RuleValidationResult(
            "PASSED",
            correlation_id=correlation_id,
            validated_command=command,
        )

    def _as_dict(self, recommendation: AIRecommendation) -> Dict[str, Any]:
        if isinstance(recommendation, AIRecommendation):
            return recommendation.to_dict()
        if isinstance(recommendation, dict):
            return recommendation
        return {}

    def _find_recommendation(
        self,
        recommendations: Iterable[Dict[str, Any]],
        recommendation_types: set,
        layer_id: str,
    ) -> Optional[Dict[str, Any]]:
        for rec in recommendations:
            rec_type = str(rec.get("recommendation_type", ""))
            rec_layer = str(rec.get("layer_id", ""))
            if rec_type in recommendation_types and rec_layer == layer_id:
                return rec
        return None

    def _check_candidate_consistency(
        self,
        stage_rec: Optional[Dict[str, Any]],
        dispatch_rec: Dict[str, Any],
        recipe_rec: Optional[Dict[str, Any]],
        action: Dict[str, Any],
        reasons: List[str],
    ) -> None:
        candidate_id = action.get("candidate_id")
        if candidate_id:
            portfolio_ids = {
                candidate.get("candidate_id")
                for candidate in dispatch_rec.get("candidate_actions", [])
                if isinstance(candidate, dict)
            }
            if portfolio_ids and candidate_id not in portfolio_ids:
                reasons.append("L1_SELECTED_CANDIDATE_NOT_IN_PORTFOLIO")

        if stage_rec is not None:
            stage_action = dict(stage_rec.get("recommended_action") or {})
            selected_candidate_id = stage_action.get("selected_candidate_id")
            if selected_candidate_id and candidate_id and selected_candidate_id != candidate_id:
                reasons.append("L3_L1_CANDIDATE_MISMATCH")

            selected_stage = stage_action.get("selected_stage") or stage_action.get(
                "target_stage"
            )
            if selected_stage and action.get("stage") and selected_stage != action.get("stage"):
                reasons.append("L3_L1_STAGE_MISMATCH")

            selected_group = stage_action.get("selected_group_key")
            action_group = action.get("group_key")
            if isinstance(selected_group, dict) and isinstance(action_group, dict):
                for key, value in selected_group.items():
                    if action_group.get(key) != value:
                        reasons.append("L3_L1_GROUP_MISMATCH")
                        break

        if recipe_rec is not None:
            recipe_action = dict(recipe_rec.get("recommended_action") or {})
            recipe_candidate_id = recipe_action.get("candidate_id")
            if recipe_candidate_id and candidate_id and recipe_candidate_id != candidate_id:
                reasons.append("L2_L1_CANDIDATE_MISMATCH")

    def _find_machine(
        self,
        stage_state: Dict[str, Any],
        equipment_id: str,
    ) -> Optional[Dict[str, Any]]:
        machines = stage_state.get("machines", {})
        if equipment_id in machines:
            return machines[equipment_id]
        suffix = equipment_id.split("_")[-1]
        for machine_id, machine_state in machines.items():
            if str(machine_id).split("_")[-1] == suffix:
                return machine_state
        return None

    def _is_machine_available(
        self,
        machine_state: Dict[str, Any],
        decision_state: Dict[str, Any],
    ) -> bool:
        status = str(machine_state.get("status", ""))
        if status == "idle":
            return True
        if status != "busy":
            return False
        try:
            finish_time = int(machine_state.get("finish_time", -1))
            current_time = int(decision_state.get("time", 0))
        except (TypeError, ValueError):
            return False
        return finish_time <= current_time

    def _available_task_uids(self, stage: str, stage_state: Dict[str, Any]) -> set:
        available = set(int(uid) for uid in stage_state.get("wait_pool_uids", []))
        available.update(int(uid) for uid in stage_state.get("rework_pool_uids", []))
        if stage == "B":
            available.update(int(uid) for uid in stage_state.get("incoming_from_A_uids", []))
        if stage == "C":
            available.update(int(uid) for uid in stage_state.get("incoming_from_B_uids", []))
        return available

    def _extract_task_uids(self, action: Dict[str, Any]) -> List[int]:
        raw_task_uids = action.get("task_uids")
        if isinstance(raw_task_uids, list):
            return [int(uid) for uid in raw_task_uids]

        raw_wafer_ids = action.get("wafer_ids")
        if not isinstance(raw_wafer_ids, list):
            return []
        task_uids = []
        for wafer_id in raw_wafer_ids:
            uid = task_uid_from_wafer_id(str(wafer_id))
            if uid is not None:
                task_uids.append(uid)
        return task_uids

    def _recipe_command_fields(self, recipe_rec: Dict[str, Any]) -> Dict[str, Any]:
        action = dict(recipe_rec.get("recommended_action") or {})
        recipe = action.get("recipe")
        params = action.get("parameters")
        if recipe is None and isinstance(params, dict):
            recipe = [params[key] for key in sorted(params)]
        fields: Dict[str, Any] = {}
        if recipe is not None:
            fields["recipe"] = recipe
        if "replace_consumable" in action:
            fields["replace_consumable"] = bool(action["replace_consumable"])
        if "replace_solution" in action:
            fields["replace_solution"] = bool(action["replace_solution"])
        return fields
