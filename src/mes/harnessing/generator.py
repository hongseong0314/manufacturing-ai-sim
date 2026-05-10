# -*- coding: utf-8 -*-
"""L1/L2 generator for MES decision chains."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.mes.domain import RuleValidationResult
from src.mes.recommendations import create_recommendation
from src.mes.services import MESDecisionService
from src.mes.harnessing.artifacts import GeneratedCycle, GeneratedDecision, HarnessPlan


class MESGeneratorAgent:
    """Generate dispatch/recipe recommendations and simulator actions."""

    def __init__(self, service: Optional[MESDecisionService] = None):
        self.service = service or MESDecisionService()

    def generate(
        self,
        decision_state: Dict[str, Any],
        plan: HarnessPlan,
    ) -> GeneratedDecision:
        candidates = [
            candidate
            for candidate in plan.candidate_portfolio
            if str(candidate.get("stage", "")).upper() == plan.target_stage
        ]
        if not candidates:
            candidates = self.service.dispatch_candidates(
                decision_state,
                stage=plan.target_stage,
            )
        if not candidates:
            empty_validation = RuleValidationResult(
                "REJECTED",
                correlation_id=plan.correlation_id,
                reasons=["NO_DISPATCH_CANDIDATES"],
            )
            return GeneratedDecision(
                plan=plan,
                recommendations=plan.recommendations,
                validation=empty_validation,
                simulator_actions={"A": {}, "B": {}, "C": {}},
                feature_snapshots=list(plan.feature_snapshots),
            )

        l1_snapshot = self.service.create_feature_snapshot(
            decision_state,
            layer_id="L1",
            correlation_id=plan.correlation_id,
            features={
                "target_stage": plan.target_stage,
                "candidate_count": len(candidates),
                "selected_candidate_id": plan.stage_priority.recommended_action.get(
                    "selected_candidate_id"
                ),
            },
        )
        dispatch_action = self._select_l1_action_from_plan(plan, candidates)
        dispatch = create_recommendation(
            recommendation_type="DISPATCH" if plan.target_stage != "C" else "PACK",
            layer_id="L1",
            objective_id=plan.objective.objective_id,
            policy_id=self.service.policy_stack.l1_policy_id,
            model_id="mes-generator",
            model_version="0.1.0",
            feature_snapshot_id=l1_snapshot.feature_snapshot_id,
            correlation_id=plan.correlation_id,
            parent_recommendation_id=plan.stage_priority.recommendation_id,
            candidate_actions=candidates,
            recommended_action=dispatch_action,
            score=1.0,
            confidence=1.0,
            reasons=[
                "selected_by_l3_from_l1_portfolio"
                if plan.stage_priority.recommended_action.get("selected_candidate_id")
                else "selected_first_rule_eligible_candidate"
            ],
        )

        recipe_action = self._default_recipe_action(
            plan.target_stage,
            dispatch_action=dispatch_action,
            decision_state=decision_state,
        )
        l2_snapshot = self.service.create_feature_snapshot(
            decision_state,
            layer_id="L2",
            correlation_id=plan.correlation_id,
            features={
                "target_stage": plan.target_stage,
                "dispatch_recommendation_id": dispatch.recommendation_id,
                "equipment_id": dispatch_action.get("equipment_id"),
                "apc_policy": recipe_action.get("apc_policy"),
                "preselect_annotation_count": len(
                    self._candidate_l2_annotations(candidates)
                ),
            },
        )
        recipe = create_recommendation(
            recommendation_type="RECIPE",
            layer_id="L2",
            objective_id=plan.objective.objective_id,
            policy_id=self.service.policy_stack.l2_policy_id,
            model_id="mes-generator",
            model_version="0.1.0",
            feature_snapshot_id=l2_snapshot.feature_snapshot_id,
            correlation_id=plan.correlation_id,
            parent_recommendation_id=dispatch.recommendation_id,
            candidate_actions=self._candidate_l2_actions(candidates, recipe_action),
            recommended_action=recipe_action,
            score=1.0,
            confidence=1.0,
            reasons=[recipe_action.get("selection_reason", "default_recipe_for_simulator_stage")],
        )

        recommendations = [plan.objective, plan.stage_priority, dispatch, recipe]
        validation = self.service.validate_recommendations(
            decision_state,
            recommendations,
        )
        simulator_actions = self.service.simulator_actions_from_validation(validation)
        return GeneratedDecision(
            plan=plan,
            recommendations=recommendations,
            validation=validation,
            simulator_actions=simulator_actions,
            feature_snapshots=list(plan.feature_snapshots) + [l1_snapshot, l2_snapshot],
        )

    def _select_l1_action_from_plan(
        self,
        plan: HarnessPlan,
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        selected_candidate_id = plan.stage_priority.recommended_action.get(
            "selected_candidate_id"
        )
        if selected_candidate_id:
            for candidate in candidates:
                if candidate.get("candidate_id") == selected_candidate_id:
                    return dict(candidate)
        selected_group_key = plan.stage_priority.recommended_action.get(
            "selected_group_key"
        )
        if isinstance(selected_group_key, dict) and selected_group_key:
            for candidate in candidates:
                group_key = candidate.get("group_key")
                if isinstance(group_key, dict) and self._group_contains(
                    group_key,
                    selected_group_key,
                ):
                    return dict(candidate)
        return dict(candidates[0])

    def _group_contains(
        self,
        candidate_group: Dict[str, Any],
        selected_group: Dict[str, Any],
    ) -> bool:
        for key, value in selected_group.items():
            if candidate_group.get(key) != value:
                return False
        return True

    def _candidate_l2_actions(
        self,
        candidates: List[Dict[str, Any]],
        selected_action: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        annotations = self._candidate_l2_annotations(candidates)
        if not annotations:
            return [selected_action]
        selected_candidate_id = selected_action.get("candidate_id")
        if selected_candidate_id and selected_candidate_id not in {
            annotation.get("candidate_id") for annotation in annotations
        }:
            annotations.append(dict(selected_action))
        return annotations

    def _candidate_l2_annotations(
        self,
        candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        annotations = []
        for candidate in candidates:
            annotation = candidate.get("l2_annotation")
            if isinstance(annotation, dict):
                annotations.append(dict(annotation))
        return annotations

    def generate_continuous(
        self,
        decision_state: Dict[str, Any],
        plan: HarnessPlan,
        max_cycles: int = 3,
    ) -> List[GeneratedCycle]:
        """Generate repeated action outputs without changing existing single-cycle interface."""
        cycles: List[GeneratedCycle] = []
        state = decision_state
        for index in range(max(1, int(max_cycles))):
            generated = self.generate(state, plan)
            cycles.append(GeneratedCycle(index=index, generated=generated))
            if not generated.validation.passed:
                break
            if not self._has_more_candidates(state, plan.target_stage):
                break
            state = self._consume_selected_tasks(state, generated.validation.validated_command)
        return cycles

    def _has_more_candidates(self, decision_state: Dict[str, Any], stage: str) -> bool:
        return bool(self.service.dispatch_candidates(decision_state, stage=stage))

    def _consume_selected_tasks(
        self,
        decision_state: Dict[str, Any],
        command: Dict[str, Any],
    ) -> Dict[str, Any]:
        stage = str(command.get("stage", ""))
        task_uids = set(int(uid) for uid in command.get("task_uids", []))
        if stage not in {"A", "B", "C"} or not task_uids:
            return decision_state
        cloned = dict(decision_state)
        stage_state = dict(cloned.get(stage, {}))
        for key in (
            "wait_pool_uids",
            "rework_pool_uids",
            "incoming_from_A_uids",
            "incoming_from_B_uids",
        ):
            if key in stage_state and isinstance(stage_state.get(key), list):
                stage_state[key] = [
                    uid for uid in stage_state[key] if int(uid) not in task_uids
                ]
        cloned[stage] = stage_state
        return cloned

    def _default_recipe_action(
        self,
        stage: str,
        dispatch_action: Optional[Dict[str, Any]] = None,
        decision_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        action = dispatch_action or {}
        return self.service.process_action_for_selected_candidate(
            decision_state or {},
            stage,
            action,
        )
