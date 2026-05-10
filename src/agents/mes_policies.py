# -*- coding: utf-8 -*-
"""MES-native L3/L4 policy interfaces and default rule baselines."""

from __future__ import annotations

from abc import ABC, abstractmethod
import copy
from typing import Any, Dict, List, Optional, Sequence


class BaseL4ObjectivePolicy(ABC):
    """Interface for system-objective selection."""

    policy_id = "L4_BASE_OBJECTIVE_POLICY"
    model_id = "base-l4-objective-policy"
    model_version = "0.0"

    @abstractmethod
    def select_objective(
        self,
        decision_state: Dict[str, Any],
        trigger_due: bool,
        previous_action: Optional[Dict[str, Any]] = None,
        previous_objective_id: str = "OBJ_RULE_ONLY_BALANCED",
    ) -> Dict[str, Any]:
        """Return objective id and objective weights for this planning interval."""
        raise NotImplementedError

    def candidate_actions(self) -> List[Dict[str, Any]]:
        return [
            {"objective_id": "OBJ_DUE_DATE_RECOVERY"},
            {"objective_id": "OBJ_THROUGHPUT_FIRST"},
            {"objective_id": "OBJ_YIELD_FIRST"},
            {"objective_id": "OBJ_RULE_ONLY_BALANCED"},
        ]


class RuleBasedL4ObjectivePolicy(BaseL4ObjectivePolicy):
    """Cycle-gated objective weighting baseline."""

    policy_id = "L4_CYCLE_WEIGHT_RULE"
    model_id = "cycle-weight-objective-policy"
    model_version = "0.1.0"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = dict(config or {})

    def select_objective(
        self,
        decision_state: Dict[str, Any],
        trigger_due: bool,
        previous_action: Optional[Dict[str, Any]] = None,
        previous_objective_id: str = "OBJ_RULE_ONLY_BALANCED",
    ) -> Dict[str, Any]:
        if not trigger_due and previous_action:
            return copy.deepcopy(previous_action)

        kpis = decision_state.get("kpis", {})
        tardiness = float(kpis.get("tardiness", 0.0) or 0.0)
        wait_total = 0
        for stage in ("A", "B", "C"):
            wait_total += len(decision_state.get(stage, {}).get("wait_pool_uids", []))
        due_pressure = self._due_date_pressure(decision_state)

        if tardiness > 0 or due_pressure > 0:
            return {
                "objective_id": "OBJ_DUE_DATE_RECOVERY",
                "weights": {
                    "throughput": 0.8,
                    "yield": 1.0,
                    "tardiness": 1.4,
                    "cost": 0.2,
                    "customer_priority": 1.2,
                },
            }
        if wait_total >= 10:
            return {
                "objective_id": "OBJ_THROUGHPUT_FIRST",
                "weights": {
                    "throughput": 1.4,
                    "yield": 0.9,
                    "tardiness": 0.7,
                    "cost": 0.2,
                },
            }
        return {
            "objective_id": previous_objective_id,
            "weights": {
                "throughput": 1.0,
                "yield": 1.0,
                "tardiness": 0.5,
                "cost": 0.2,
                "customer_priority": 1.0,
            },
        }

    def _due_date_pressure(self, decision_state: Dict[str, Any]) -> float:
        now = int(decision_state.get("time", 0) or 0)
        pressure = 0.0
        tasks = decision_state.get("tasks", {})
        if not isinstance(tasks, dict):
            return pressure
        for row in tasks.values():
            if not isinstance(row, dict):
                continue
            try:
                due_date = int(row.get("due_date", now))
            except (TypeError, ValueError):
                continue
            pressure = max(pressure, float(now - due_date))
        return max(0.0, pressure)


class BaseL3MetaSchedulerPolicy(ABC):
    """Interface for annotated candidate-portfolio selection."""

    policy_id = "L3_BASE_META_SCHEDULER"
    model_id = "base-l3-meta-scheduler"
    model_version = "0.0"

    @abstractmethod
    def select(
        self,
        decision_state: Dict[str, Any],
        objective_action: Dict[str, Any],
        candidate_portfolio: Sequence[Dict[str, Any]],
        target_stage: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Select stage/group/candidate budgets from the annotated portfolio."""
        raise NotImplementedError


class CandidatePortfolioL3MetaSchedulerPolicy(BaseL3MetaSchedulerPolicy):
    """Default MES-native L3 policy over L1 candidates with L2 annotations."""

    policy_id = "L3_CANDIDATE_PORTFOLIO_RULE"
    model_id = "candidate-portfolio-meta-scheduler"
    model_version = "0.1.0"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = dict(config or {})

    def select(
        self,
        decision_state: Dict[str, Any],
        objective_action: Dict[str, Any],
        candidate_portfolio: Sequence[Dict[str, Any]],
        target_stage: Optional[str] = None,
    ) -> Dict[str, Any]:
        portfolio = [dict(candidate) for candidate in candidate_portfolio]
        selected_candidate = self._select_portfolio_candidate(
            portfolio,
            objective_action,
            target_stage=target_stage,
        )
        resolved_stage = (
            target_stage
            or (selected_candidate or {}).get("stage")
            or self._select_stage(decision_state, portfolio)
        )
        resolved_stage = str(resolved_stage or "A").upper()
        if selected_candidate is None and target_stage is not None:
            selected_candidate = self._select_portfolio_candidate(
                portfolio,
                objective_action,
                target_stage=resolved_stage,
            )

        budget_candidates = self._select_budget_candidates(
            portfolio,
            objective_action,
            target_stage=target_stage,
        )
        if selected_candidate is None and budget_candidates:
            selected_candidate = budget_candidates[0]

        selected_group_key = dict((selected_candidate or {}).get("group_key", {}))
        selected_candidate_id = (selected_candidate or {}).get("candidate_id")
        selected_candidate_ids = [
            str(candidate.get("candidate_id"))
            for candidate in budget_candidates
            if candidate.get("candidate_id")
        ]
        dispatch_budgets = self._dispatch_budgets(budget_candidates)
        budget_candidate_ids = self._budget_candidate_ids(budget_candidates)
        return {
            "target_stage": resolved_stage,
            "selected_stage": resolved_stage,
            "selected_candidate_id": selected_candidate_id,
            "selected_candidate_ids": selected_candidate_ids,
            "selected_group_key": selected_group_key,
            "stage_priorities": self._stage_priorities(
                portfolio,
                objective_action,
                selected_stage=resolved_stage,
            ),
            "dispatch_budgets": dispatch_budgets,
            "budget_candidate_ids": budget_candidate_ids,
            "score_components": self._score_components(
                selected_candidate,
                objective_action,
            ),
            "constraints": {
                "max_commands_per_cycle": len(selected_candidate_ids),
                "select_from_l1_portfolio": True,
            },
            "candidate_actions": self._l3_candidate_actions(portfolio, objective_action),
            "reasons": ["candidate_portfolio_meta_scheduler"],
        }

    def _select_stage(
        self,
        decision_state: Dict[str, Any],
        candidate_portfolio: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        if candidate_portfolio:
            return str(candidate_portfolio[0].get("stage", "A") or "A")
        for stage in ("A", "B", "C"):
            stage_state = decision_state.get(stage, {})
            if stage_state.get("wait_pool_uids") or stage_state.get("rework_pool_uids"):
                return stage
        return "A"

    def _select_portfolio_candidate(
        self,
        candidate_portfolio: List[Dict[str, Any]],
        objective_action: Dict[str, Any],
        target_stage: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        candidates = [
            candidate
            for candidate in candidate_portfolio
            if target_stage is None
            or str(candidate.get("stage", "")).upper() == str(target_stage).upper()
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda candidate: (
                self._upper_score(candidate, objective_action),
                float(candidate.get("local_score", 0.0) or 0.0),
                -int(candidate.get("local_rank", 0) or 0),
            ),
        )

    def _select_budget_candidates(
        self,
        candidate_portfolio: List[Dict[str, Any]],
        objective_action: Dict[str, Any],
        target_stage: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        candidates = [
            candidate
            for candidate in candidate_portfolio
            if target_stage is None
            or str(candidate.get("stage", "")).upper() == str(target_stage).upper()
        ]
        ranked = sorted(
            candidates,
            key=lambda candidate: (
                self._upper_score(candidate, objective_action),
                float(candidate.get("local_score", 0.0) or 0.0),
                -int(candidate.get("local_rank", 0) or 0),
            ),
            reverse=True,
        )
        selected: List[Dict[str, Any]] = []
        used_equipment = set()
        used_task_uids = set()
        for candidate in ranked:
            stage = str(candidate.get("stage", "")).upper()
            equipment_id = str(candidate.get("equipment_id", ""))
            equipment_key = (stage, equipment_id)
            if stage not in {"A", "B", "C"} or not equipment_id:
                continue
            if equipment_key in used_equipment:
                continue
            task_uids = {
                int(uid)
                for uid in candidate.get("task_uids", [])
                if str(uid).lstrip("-").isdigit()
            }
            if not task_uids or task_uids & used_task_uids:
                continue
            selected.append(candidate)
            used_equipment.add(equipment_key)
            used_task_uids.update(task_uids)
        return selected

    def _dispatch_budgets(
        self,
        selected_candidates: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        budgets = {stage: 0 for stage in ("A", "B", "C")}
        for candidate in selected_candidates:
            stage = str(candidate.get("stage", "")).upper()
            if stage in budgets:
                budgets[stage] += 1
        return budgets

    def _budget_candidate_ids(
        self,
        selected_candidates: List[Dict[str, Any]],
    ) -> Dict[str, List[str]]:
        ids = {stage: [] for stage in ("A", "B", "C")}
        for candidate in selected_candidates:
            stage = str(candidate.get("stage", "")).upper()
            candidate_id = candidate.get("candidate_id")
            if stage in ids and candidate_id:
                ids[stage].append(str(candidate_id))
        return ids

    def _stage_priorities(
        self,
        candidate_portfolio: List[Dict[str, Any]],
        objective_action: Dict[str, Any],
        selected_stage: str,
    ) -> Dict[str, float]:
        scores = {stage: 0.0 for stage in ("A", "B", "C")}
        for candidate in candidate_portfolio:
            stage = str(candidate.get("stage", "")).upper()
            if stage not in scores:
                continue
            scores[stage] = max(scores[stage], self._upper_score(candidate, objective_action))
        max_score = max(scores.values()) if scores else 0.0
        if max_score <= 0:
            return {
                stage: 1.0 if stage == selected_stage else 0.0
                for stage in ("A", "B", "C")
            }
        return {
            stage: round(score / max_score, 4)
            for stage, score in scores.items()
        }

    def _l3_candidate_actions(
        self,
        candidate_portfolio: List[Dict[str, Any]],
        objective_action: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        actions = []
        for candidate in candidate_portfolio:
            action = dict(candidate)
            action["upper_score"] = round(
                self._upper_score(candidate, objective_action),
                4,
            )
            actions.append(action)
        return actions

    def _upper_score(
        self,
        candidate: Dict[str, Any],
        objective_action: Dict[str, Any],
    ) -> float:
        features = dict(candidate.get("features", {}) or {})
        annotation = dict(candidate.get("l2_annotation", {}) or {})
        weights = dict(objective_action.get("weights", {}) or {})
        local_score = float(candidate.get("local_score", 0.0) or 0.0)
        due_pressure = float(features.get("due_date_pressure", 0.0) or 0.0)
        batch_size = float(features.get("batch_size", 1.0) or 1.0)
        margin_value = float(features.get("margin_value", 0.0) or 0.0)
        throughput_weight = float(weights.get("throughput", 1.0) or 1.0)
        tardiness_weight = float(weights.get("tardiness", 0.5) or 0.5)
        customer_weight = float(weights.get("customer_priority", 1.0) or 1.0)
        quality_risk_penalty = {
            "LOW": 0.0,
            "MEDIUM": 8.0,
            "HIGH": 25.0,
        }.get(str(annotation.get("quality_risk", "LOW")).upper(), 0.0)
        return (
            local_score
            + tardiness_weight * due_pressure * 10.0
            + throughput_weight * batch_size
            + customer_weight * margin_value * 5.0
            - quality_risk_penalty
        )

    def _score_components(
        self,
        selected_candidate: Optional[Dict[str, Any]],
        objective_action: Dict[str, Any],
    ) -> Dict[str, float]:
        if selected_candidate is None:
            return {
                "local_candidate_score": 0.0,
                "due_date_pressure": 0.0,
                "upper_score": 0.0,
            }
        features = dict(selected_candidate.get("features", {}) or {})
        return {
            "local_candidate_score": float(
                selected_candidate.get("local_score", 0.0) or 0.0
            ),
            "due_date_pressure": float(features.get("due_date_pressure", 0.0) or 0.0),
            "wip_pressure": float(features.get("batch_size", 0.0) or 0.0),
            "upper_score": round(
                self._upper_score(selected_candidate, objective_action),
                4,
            ),
        }
