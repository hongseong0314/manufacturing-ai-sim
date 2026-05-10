# -*- coding: utf-8 -*-
"""Rule validation and simulator action conversion helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from src.mes.domain import AIRecommendation, RuleValidationResult
from src.mes.recommendations import create_recommendation


class SimulatorActionMixin:
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
