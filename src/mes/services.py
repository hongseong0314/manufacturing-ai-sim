# -*- coding: utf-8 -*-
"""Facade service for MES decision helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.agents.factory import MESPolicyStack, build_mes_policy_stack
from src.mes.adapters import SimulatorMESAdapter
from src.mes.decision.annotations import CandidateAnnotationMixin
from src.mes.decision.candidates import CandidatePortfolioMixin
from src.mes.decision.simulator_actions import SimulatorActionMixin
from src.mes.domain import FeatureSnapshot
from src.mes.rule_engine import MESRuleEngine


class MESDecisionService(
    CandidatePortfolioMixin,
    CandidateAnnotationMixin,
    SimulatorActionMixin,
):
    """Small orchestration surface for the simulator-backed MES shell."""

    def __init__(
        self,
        adapter: Optional[SimulatorMESAdapter] = None,
        rule_engine: Optional[MESRuleEngine] = None,
        config: Optional[Dict[str, Any]] = None,
        policy_stack: Optional[MESPolicyStack] = None,
    ):
        self.adapter = adapter or SimulatorMESAdapter()
        self.rule_engine = rule_engine or MESRuleEngine()
        self.policy_stack = policy_stack or build_mes_policy_stack(config or {})

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
        """Generate rule-eligible L1 candidate actions for one stage."""
        return self.l1_candidate_portfolio(decision_state, stages=[stage])


__all__ = ["MESDecisionService"]
