# -*- coding: utf-8 -*-
"""L4/L3 planner for MES decision chains."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from src.mes.recommendations import create_recommendation, make_id
from src.mes.services import MESDecisionService
from src.mes.harnessing.artifacts import HarnessPlan


class MESPlannerAgent:
    """Choose objective and stage focus for the current decision cycle."""

    def __init__(
        self,
        service: Optional[MESDecisionService] = None,
        planning_interval: int = 1,
    ):
        self.service = service or MESDecisionService()
        self.planning_interval = max(1, int(planning_interval))
        self._last_objective_action: Dict[str, Any] = {}
        self._last_objective_id: str = "OBJ_RULE_ONLY_BALANCED"

    def plan(
        self,
        decision_state: Dict[str, Any],
        target_stage: Optional[str] = None,
        correlation_id: Optional[str] = None,
        candidate_portfolio: Optional[List[Dict[str, Any]]] = None,
    ) -> HarnessPlan:
        resolved_correlation_id = correlation_id or make_id("CORR")
        now = int(decision_state.get("time", 0) or 0)
        trigger_due = (now % self.planning_interval) == 0
        raw_portfolio = list(
            candidate_portfolio
            if candidate_portfolio is not None
            else self.service.l1_candidate_portfolio(decision_state)
        )
        portfolio = self.service.annotate_candidate_portfolio(
            decision_state,
            raw_portfolio,
        )

        policy_stack = self.service.policy_stack
        l4_policy = policy_stack.l4_objective_policy
        l3_policy = policy_stack.l3_meta_scheduler
        objective_action = l4_policy.select_objective(
            decision_state,
            trigger_due=trigger_due,
            previous_action=self._last_objective_action,
            previous_objective_id=self._last_objective_id,
        )
        l3_selection = dict(
            l3_policy.select(
                decision_state,
                objective_action,
                portfolio,
                target_stage=target_stage,
            )
        )
        selected_candidate_ids = [
            str(candidate_id)
            for candidate_id in l3_selection.get("selected_candidate_ids", [])
        ]
        selected_candidate_id = l3_selection.get("selected_candidate_id")
        if not selected_candidate_id and selected_candidate_ids:
            selected_candidate_id = selected_candidate_ids[0]
        resolved_stage = str(
            l3_selection.get("target_stage")
            or l3_selection.get("selected_stage")
            or target_stage
            or "A"
        ).upper()
        selected_stage = str(l3_selection.get("selected_stage") or resolved_stage).upper()
        selected_group_key = dict(l3_selection.get("selected_group_key") or {})
        stage_priorities = dict(l3_selection.get("stage_priorities") or {})
        dispatch_budgets = dict(l3_selection.get("dispatch_budgets") or {})
        budget_candidate_ids = dict(l3_selection.get("budget_candidate_ids") or {})
        score_components = dict(l3_selection.get("score_components") or {})
        constraints = dict(l3_selection.get("constraints") or {})
        constraints.setdefault("max_commands_per_cycle", len(selected_candidate_ids))
        constraints.setdefault("select_from_l1_portfolio", True)
        l3_candidate_actions = list(l3_selection.get("candidate_actions") or [])

        l4_snapshot = self.service.create_feature_snapshot(
            decision_state,
            layer_id="L4",
            correlation_id=resolved_correlation_id,
            features={
                **self._objective_features(decision_state, trigger_due),
                "l4_policy_id": policy_stack.l4_policy_id,
            },
        )
        objective_candidate_actions = (
            l4_policy.candidate_actions()
            if callable(getattr(l4_policy, "candidate_actions", None))
            else [
                {"objective_id": "OBJ_THROUGHPUT_FIRST"},
                {"objective_id": "OBJ_YIELD_FIRST"},
                {"objective_id": "OBJ_RULE_ONLY_BALANCED"},
            ]
        )
        objective = create_recommendation(
            recommendation_type="OBJECTIVE",
            layer_id="L4",
            objective_id=objective_action["objective_id"],
            policy_id=policy_stack.l4_policy_id,
            model_id=getattr(l4_policy, "model_id", "mes-l4-objective-policy"),
            model_version=getattr(l4_policy, "model_version", "0.1.0"),
            feature_snapshot_id=l4_snapshot.feature_snapshot_id,
            correlation_id=resolved_correlation_id,
            candidate_actions=objective_candidate_actions,
            recommended_action=objective_action,
            score=1.0,
            confidence=1.0,
            reasons=objective_action.get("reasons") or [
                "objective_trigger_due"
                if trigger_due
                else "objective_reused_until_next_trigger"
            ],
        )
        l3_snapshot = self.service.create_feature_snapshot(
            decision_state,
            layer_id="L3",
            correlation_id=resolved_correlation_id,
            features={
                "stage_priorities": stage_priorities,
                "target_stage": resolved_stage,
                "candidate_count": len(portfolio),
                "selected_candidate_id": selected_candidate_id,
                "selected_candidate_ids": selected_candidate_ids,
                "selected_group_key": selected_group_key,
                "dispatch_budgets": dispatch_budgets,
                "budget_candidate_ids": budget_candidate_ids,
                "objective_id": objective_action["objective_id"],
                "l3_policy_id": policy_stack.l3_policy_id,
                "task_generation_trigger_due": trigger_due,
            },
        )
        stage_priority = create_recommendation(
            recommendation_type="STAGE_PRIORITY",
            layer_id="L3",
            objective_id=objective.objective_id,
            policy_id=policy_stack.l3_policy_id,
            model_id=getattr(l3_policy, "model_id", "mes-l3-meta-scheduler"),
            model_version=getattr(l3_policy, "model_version", "0.1.0"),
            feature_snapshot_id=l3_snapshot.feature_snapshot_id,
            correlation_id=resolved_correlation_id,
            parent_recommendation_id=objective.recommendation_id,
            candidate_actions=l3_candidate_actions,
            recommended_action={
                "target_stage": resolved_stage,
                "selected_stage": selected_stage,
                "selected_candidate_id": selected_candidate_id,
                "selected_candidate_ids": selected_candidate_ids,
                "selected_group_key": selected_group_key,
                "stage_priorities": stage_priorities,
                "dispatch_budgets": dispatch_budgets,
                "budget_candidate_ids": budget_candidate_ids,
                "score_components": score_components,
                "constraints": constraints,
                "task_generation_trigger_due": trigger_due,
            },
            score=1.0,
            confidence=1.0,
            reasons=l3_selection.get("reasons") or [
                "first_stage_with_rule_eligible_candidates"
                if trigger_due
                else "stage_priority_maintained_until_next_trigger"
            ],
        )

        self._last_objective_action = copy.deepcopy(objective_action)
        self._last_objective_id = str(objective_action["objective_id"])

        return HarnessPlan(
            correlation_id=resolved_correlation_id,
            target_stage=resolved_stage,
            objective=objective,
            stage_priority=stage_priority,
            feature_snapshots=[l4_snapshot, l3_snapshot],
            candidate_portfolio=portfolio,
        )

    def _objective_features(
        self,
        decision_state: Dict[str, Any],
        trigger_due: bool,
    ) -> Dict[str, Any]:
        mes_state = self.service.decision_state_to_mes(decision_state)
        return {
            "time": mes_state.get("time", 0),
            "wip": mes_state.get("wip", {}),
            "kpis": mes_state.get("kpis", {}),
            "task_generation_trigger_due": trigger_due,
            "planning_interval": self.planning_interval,
        }
