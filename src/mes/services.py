# -*- coding: utf-8 -*-
"""High-level MES shell services around the simulator kernel."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from src.mes.adapters import SimulatorMESAdapter
from src.mes.domain import AIRecommendation, FeatureSnapshot, RuleValidationResult
from src.mes.recommendations import create_recommendation
from src.mes.rule_engine import MESRuleEngine


class MESDecisionService:
    """Small orchestration surface for the first simulator-backed MES MVP."""

    def __init__(
        self,
        adapter: Optional[SimulatorMESAdapter] = None,
        rule_engine: Optional[MESRuleEngine] = None,
    ):
        self.adapter = adapter or SimulatorMESAdapter()
        self.rule_engine = rule_engine or MESRuleEngine()

    def decision_state_to_mes(self, decision_state: Dict[str, Any]) -> Dict[str, Any]:
        return self.adapter.decision_state_to_mes(decision_state)

    def create_feature_snapshot(
        self,
        decision_state: Dict[str, Any],
        layer_id: str,
        correlation_id: Optional[str] = None,
        features: Optional[Dict[str, Any]] = None,
    ) -> FeatureSnapshot:
        return self.adapter.feature_snapshot_from_state(
            decision_state,
            layer_id=layer_id,
            correlation_id=correlation_id,
            features=features,
        )

    def dispatch_candidates(
        self,
        decision_state: Dict[str, Any],
        stage: str = "A",
    ) -> List[Dict[str, Any]]:
        """Generate rule-only candidate actions from idle simulator machines."""
        stage = stage.upper()
        stage_state = decision_state.get(stage, {})
        pool = self._candidate_pool(stage, stage_state)
        if not pool:
            return []

        candidates: List[Dict[str, Any]] = []
        used_uids = set()
        for equipment_id, machine in sorted(stage_state.get("machines", {}).items()):
            if not self._is_machine_available(machine, decision_state):
                continue
            batch_size = int(machine.get("batch_size", 1))
            task_uids = [uid for uid in pool if uid not in used_uids][:batch_size]
            if not task_uids:
                continue
            if stage == "C" and len(task_uids) < batch_size:
                continue
            used_uids.update(task_uids)
            candidates.append(
                {
                    "stage": stage,
                    "equipment_id": str(equipment_id),
                    "task_uids": task_uids,
                    "operation_id": stage,
                    "task_type": "rework"
                    if task_uids[0] in set(stage_state.get("rework_pool_uids", []))
                    else "new",
                    "rule_precheck_status": "ELIGIBLE",
                }
            )
        return candidates

    def build_rule_only_dispatch_recommendation(
        self,
        decision_state: Dict[str, Any],
        stage: str = "A",
        correlation_id: Optional[str] = None,
    ) -> Optional[AIRecommendation]:
        """Create a baseline L1 recommendation without introducing AI yet."""
        candidates = self.dispatch_candidates(decision_state, stage=stage)
        if not candidates:
            return None
        snapshot = self.create_feature_snapshot(
            decision_state,
            layer_id="L1",
            correlation_id=correlation_id,
            features={"stage": stage.upper(), "candidate_count": len(candidates)},
        )
        return create_recommendation(
            recommendation_type="DISPATCH",
            layer_id="L1",
            objective_id="OBJ_RULE_ONLY_BASELINE",
            policy_id="RULE_ONLY_DISPATCH_BASELINE",
            model_id="rule-engine",
            model_version="0.1.0",
            feature_snapshot_id=snapshot.feature_snapshot_id,
            correlation_id=snapshot.correlation_id,
            candidate_actions=candidates,
            recommended_action=candidates[0],
            score=1.0,
            confidence=1.0,
            reasons=["first_available_rule_candidate"],
        )

    def validate_recommendations(
        self,
        decision_state: Dict[str, Any],
        recommendations: Sequence[AIRecommendation],
    ) -> RuleValidationResult:
        return self.rule_engine.validate_recommendations(decision_state, recommendations)

    def simulator_actions_from_validation(
        self,
        validation: RuleValidationResult,
    ) -> Dict[str, Dict[str, Any]]:
        if not validation.passed:
            return {"A": {}, "B": {}, "C": {}}
        return self.adapter.command_to_simulator_actions(validation.validated_command)

    def _candidate_pool(self, stage: str, stage_state: Dict[str, Any]) -> List[int]:
        pool = [int(uid) for uid in stage_state.get("rework_pool_uids", [])]
        pool.extend(int(uid) for uid in stage_state.get("wait_pool_uids", []))
        if stage == "B":
            pool = [int(uid) for uid in stage_state.get("incoming_from_A_uids", [])] + pool
        if stage == "C":
            pool = pool + [int(uid) for uid in stage_state.get("incoming_from_B_uids", [])]
        seen = set()
        ordered = []
        for uid in pool:
            if uid in seen:
                continue
            seen.add(uid)
            ordered.append(uid)
        return ordered

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
