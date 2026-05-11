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
        portfolio_snapshot = self.service.create_feature_snapshot(
            decision_state,
            layer_id="PORTFOLIO",
            correlation_id=resolved_correlation_id,
            features={
                "objective_id": objective_action["objective_id"],
                "l4_recommendation_id": objective.recommendation_id,
                "l3_recommendation_id": stage_priority.recommendation_id,
                "l4_policy_id": policy_stack.l4_policy_id,
                "l3_policy_id": policy_stack.l3_policy_id,
                "selected_candidate_id": selected_candidate_id,
                "selected_candidate_ids": selected_candidate_ids,
                "selected_group_key": selected_group_key,
                "diagnostics": self._portfolio_diagnostics(
                    decision_state,
                    l3_candidate_actions,
                ),
                "empty_reason": self._empty_reason(
                    decision_state,
                    l3_candidate_actions,
                    selected_candidate_id,
                ),
                "candidates": self._portfolio_snapshot_rows(
                    resolved_correlation_id,
                    l3_candidate_actions,
                    objective_action,
                    selected_candidate_id,
                    selected_candidate_ids,
                    {
                        "L4": objective.recommendation_id,
                        "L3": stage_priority.recommendation_id,
                    },
                ),
            },
        )

        self._last_objective_action = copy.deepcopy(objective_action)
        self._last_objective_id = str(objective_action["objective_id"])

        return HarnessPlan(
            correlation_id=resolved_correlation_id,
            target_stage=resolved_stage,
            objective=objective,
            stage_priority=stage_priority,
            feature_snapshots=[l4_snapshot, l3_snapshot, portfolio_snapshot],
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

    def _portfolio_snapshot_rows(
        self,
        correlation_id: str,
        candidate_actions: List[Dict[str, Any]],
        objective_action: Dict[str, Any],
        selected_candidate_id: Optional[str],
        selected_candidate_ids: List[str],
        linked_recommendation_ids: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        selected_ids = {str(candidate_id) for candidate_id in selected_candidate_ids}
        selected_id = str(selected_candidate_id or "")
        rows = []
        for candidate in candidate_actions:
            candidate_id = str(candidate.get("candidate_id", ""))
            selected = candidate_id == selected_id
            budget_selected = candidate_id in selected_ids
            upper_score = float(candidate.get("upper_score", 0.0) or 0.0)
            features = dict(candidate.get("features", {}) or {})
            rows.append(
                {
                    "correlation_id": correlation_id,
                    "candidate_id": candidate_id,
                    "stage": str(candidate.get("stage", "")).upper(),
                    "candidate_type": candidate.get("candidate_type"),
                    "group_key": dict(candidate.get("group_key") or {}),
                    "equipment_id": candidate.get("equipment_id"),
                    "task_uids": list(candidate.get("task_uids") or []),
                    "local_score": float(candidate.get("local_score", 0.0) or 0.0),
                    "local_rank": int(candidate.get("local_rank", 0) or 0),
                    "l2_annotation": dict(candidate.get("l2_annotation") or {}),
                    "upper_score": upper_score,
                    "score_components": {
                        "local_candidate_score": float(
                            candidate.get("local_score", 0.0) or 0.0
                        ),
                        "due_date_pressure": float(
                            features.get("due_date_pressure", 0.0) or 0.0
                        ),
                        "wip_pressure": float(features.get("batch_size", 0.0) or 0.0),
                        "objective_weight_bonus": self._objective_weight_bonus(
                            features,
                            objective_action,
                        ),
                        "quality_risk_penalty": self._quality_risk_penalty(
                            candidate,
                        ),
                        "final_upper_score": upper_score,
                    },
                    "selected": selected,
                    "budget_selected": budget_selected,
                    "rejection_reason": self._rejection_reason(selected, budget_selected),
                    "linked_recommendation_ids": dict(linked_recommendation_ids),
                }
            )
        return rows

    def _rejection_reason(self, selected: bool, budget_selected: bool) -> Optional[str]:
        if selected:
            return None
        if budget_selected:
            return "budget_candidate_not_finalized"
        return "not_selected_by_l3"

    def _objective_weight_bonus(
        self,
        features: Dict[str, Any],
        objective_action: Dict[str, Any],
    ) -> float:
        weights = dict(objective_action.get("weights", {}) or {})
        due_pressure = float(features.get("due_date_pressure", 0.0) or 0.0)
        batch_size = float(features.get("batch_size", 0.0) or 0.0)
        margin_value = float(features.get("margin_value", 0.0) or 0.0)
        return round(
            float(weights.get("tardiness", 0.5) or 0.5) * due_pressure * 10.0
            + float(weights.get("throughput", 1.0) or 1.0) * batch_size
            + float(weights.get("customer_priority", 1.0) or 1.0)
            * margin_value
            * 5.0,
            4,
        )

    def _quality_risk_penalty(self, candidate: Dict[str, Any]) -> float:
        annotation = dict(candidate.get("l2_annotation", {}) or {})
        return {
            "LOW": 0.0,
            "MEDIUM": 8.0,
            "HIGH": 25.0,
        }.get(str(annotation.get("quality_risk", "LOW")).upper(), 0.0)

    def _portfolio_diagnostics(
        self,
        decision_state: Dict[str, Any],
        candidate_actions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        candidate_counts = {"A": 0, "B": 0, "C": 0}
        for candidate in candidate_actions:
            stage = str(candidate.get("stage", "")).upper()
            if stage in candidate_counts:
                candidate_counts[stage] += 1
        return {
            "stages": {
                stage: self._stage_diagnostics(
                    decision_state,
                    stage,
                    candidate_counts[stage],
                )
                for stage in ("A", "B", "C")
            }
        }

    def _stage_diagnostics(
        self,
        decision_state: Dict[str, Any],
        stage: str,
        candidate_count: int,
    ) -> Dict[str, Any]:
        stage_state = dict(decision_state.get(stage, {}) or {})
        machines = dict(stage_state.get("machines", {}) or {})
        incoming_key = "incoming_from_A_uids" if stage == "B" else "incoming_from_B_uids"
        queue_size = (
            len(stage_state.get("wait_pool_uids", []) or [])
            + len(stage_state.get("rework_pool_uids", []) or [])
            + (len(stage_state.get(incoming_key, []) or []) if stage != "A" else 0)
        )
        idle_machines = sum(
            1
            for machine in machines.values()
            if str(machine.get("status", "")).upper() == "IDLE"
        )
        running_machines = sum(
            1
            for machine in machines.values()
            if str(machine.get("status", "")).upper() == "BUSY"
        )
        batch_sizes = [
            int(machine.get("batch_size", 1) or 1)
            for machine in machines.values()
            if isinstance(machine, dict)
        ]
        batch_size = max(1, min(batch_sizes) if batch_sizes else 1)
        return {
            "queue_size": queue_size,
            "idle_machines": idle_machines,
            "running_machines": running_machines,
            "batch_size": batch_size,
            "batch_ready": queue_size >= batch_size,
            "candidate_count": int(candidate_count),
        }

    def _empty_reason(
        self,
        decision_state: Dict[str, Any],
        candidate_actions: List[Dict[str, Any]],
        selected_candidate_id: Optional[str],
    ) -> Optional[str]:
        if candidate_actions and selected_candidate_id:
            return None
        diagnostics = self._portfolio_diagnostics(decision_state, candidate_actions)
        stages = diagnostics["stages"]
        if any(stage["queue_size"] > 0 and stage["idle_machines"] == 0 for stage in stages.values()):
            return "ALL_EQUIPMENT_BUSY"
        if all(stage["queue_size"] == 0 for stage in stages.values()):
            return "NO_WAIT_POOL"
        if any(stage["queue_size"] > 0 and not stage["batch_ready"] for stage in stages.values()):
            return "BATCH_NOT_READY"
        return "NO_ELIGIBLE_CANDIDATES"
