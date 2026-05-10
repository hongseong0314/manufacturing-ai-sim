# -*- coding: utf-8 -*-
"""Decision-chain evaluator for MES harness runs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from src.mes.domain import AIRecommendation, RuleValidationResult
from src.mes.store import InMemoryMESStore
from src.mes.harnessing.artifacts import GeneratedDecision, HarnessEvaluationReport


LAYER_SEQUENCE = ("L4", "L3", "L1", "L2")


class MESEvaluatorAgent:
    """Evaluate full connectivity of a generated MES decision chain."""

    def evaluate(
        self,
        generated: GeneratedDecision,
        store: Optional[InMemoryMESStore] = None,
    ) -> HarnessEvaluationReport:
        issues: List[str] = []
        recommendations = generated.recommendations
        by_layer = self._by_layer(recommendations)

        self._check_required_layers(by_layer, issues)
        self._check_correlation_ids(recommendations, issues)
        self._check_feature_snapshots(recommendations, issues)
        self._check_parent_chain(by_layer, issues)
        self._check_candidate_consistency(by_layer, issues)
        self._check_validation(generated.validation, issues)
        self._check_simulator_actions(generated, issues)
        if store is not None:
            self._check_cycle_integrity(generated, store, issues)

        checked = {
            "required_layers": all(layer in by_layer for layer in LAYER_SEQUENCE),
            "single_correlation_id": "CORRELATION_ID_MISMATCH" not in issues,
            "feature_snapshots": "MISSING_FEATURE_SNAPSHOT_ID" not in issues,
            "parent_chain": "BROKEN_PARENT_CHAIN" not in issues,
            "candidate_portfolio": "MISSING_CANDIDATE_PORTFOLIO" not in issues,
            "candidate_consistency": not any(
                issue.startswith("CANDIDATE_") for issue in issues
            ),
            "rule_validation": generated.validation.passed,
            "simulator_actions": bool(
                self._non_empty_actions(generated.simulator_actions)
            ),
            "chain_completeness": "INCOMPLETE_CHAIN_RECORDS" not in issues,
            "correlation_consistency": "STORE_CORRELATION_MISMATCH" not in issues,
            "command_event_alignment": "COMMAND_EVENT_MISMATCH" not in issues,
        }
        return HarnessEvaluationReport(
            status="PASSED" if not issues else "REJECTED",
            issues=issues,
            checked=checked,
        )

    def _by_layer(
        self,
        recommendations: Sequence[AIRecommendation],
    ) -> Dict[str, AIRecommendation]:
        by_layer: Dict[str, AIRecommendation] = {}
        for rec in recommendations:
            by_layer.setdefault(rec.layer_id, rec)
        return by_layer

    def _check_required_layers(
        self,
        by_layer: Dict[str, AIRecommendation],
        issues: List[str],
    ) -> None:
        missing = [layer for layer in LAYER_SEQUENCE if layer not in by_layer]
        if missing:
            issues.append(f"MISSING_LAYERS:{','.join(missing)}")

    def _check_correlation_ids(
        self,
        recommendations: Sequence[AIRecommendation],
        issues: List[str],
    ) -> None:
        correlation_ids = {
            rec.correlation_id
            for rec in recommendations
            if rec.correlation_id
        }
        if len(correlation_ids) != 1:
            issues.append("CORRELATION_ID_MISMATCH")

    def _check_feature_snapshots(
        self,
        recommendations: Sequence[AIRecommendation],
        issues: List[str],
    ) -> None:
        if any(not rec.feature_snapshot_id for rec in recommendations):
            issues.append("MISSING_FEATURE_SNAPSHOT_ID")

    def _check_parent_chain(
        self,
        by_layer: Dict[str, AIRecommendation],
        issues: List[str],
    ) -> None:
        if not all(layer in by_layer for layer in LAYER_SEQUENCE):
            return
        expected = {
            "L3": by_layer["L4"].recommendation_id,
            "L1": by_layer["L3"].recommendation_id,
            "L2": by_layer["L1"].recommendation_id,
        }
        for layer, parent_id in expected.items():
            if by_layer[layer].parent_recommendation_id != parent_id:
                issues.append("BROKEN_PARENT_CHAIN")
                return

    def _check_candidate_consistency(
        self,
        by_layer: Dict[str, AIRecommendation],
        issues: List[str],
    ) -> None:
        if not all(layer in by_layer for layer in ("L3", "L1", "L2")):
            return
        l3 = by_layer["L3"]
        l1 = by_layer["L1"]
        l2 = by_layer["L2"]
        l1_action = dict(l1.recommended_action or {})
        l2_action = dict(l2.recommended_action or {})
        l3_action = dict(l3.recommended_action or {})
        candidate_id = l1_action.get("candidate_id")
        if not candidate_id:
            issues.append("CANDIDATE_ID_MISSING")
            return
        l1_portfolio_ids = {
            candidate.get("candidate_id")
            for candidate in l1.candidate_actions
            if isinstance(candidate, dict)
        }
        if not l1_portfolio_ids:
            issues.append("MISSING_CANDIDATE_PORTFOLIO")
            return
        if candidate_id not in l1_portfolio_ids:
            issues.append("CANDIDATE_NOT_IN_L1_PORTFOLIO")
            return
        selected_candidate_id = l3_action.get("selected_candidate_id")
        if selected_candidate_id and selected_candidate_id != candidate_id:
            issues.append("CANDIDATE_L3_L1_MISMATCH")
            return
        l2_candidate_id = l2_action.get("candidate_id")
        if l2_candidate_id and l2_candidate_id != candidate_id:
            issues.append("CANDIDATE_L2_L1_MISMATCH")

    def _check_validation(
        self,
        validation: RuleValidationResult,
        issues: List[str],
    ) -> None:
        if not validation.passed:
            issues.append(f"RULE_VALIDATION_FAILED:{','.join(validation.reasons)}")

    def _check_simulator_actions(
        self,
        generated: GeneratedDecision,
        issues: List[str],
    ) -> None:
        non_empty = self._non_empty_actions(generated.simulator_actions)
        if not non_empty:
            issues.append("EMPTY_SIMULATOR_ACTIONS")
            return
        command = generated.validation.validated_command
        stage = command.get("stage")
        equipment_id = command.get("equipment_id")
        task_uids = command.get("task_uids")
        assignment = generated.simulator_actions.get(stage, {}).get(equipment_id)
        if not assignment or assignment.get("task_uids") != task_uids:
            issues.append("SIMULATOR_ACTION_COMMAND_MISMATCH")


    def _check_cycle_integrity(
        self,
        generated: GeneratedDecision,
        store: InMemoryMESStore,
        issues: List[str],
    ) -> None:
        correlation_id = generated.plan.correlation_id
        recommendations = store.recommendations(correlation_id)
        snapshots = store.feature_snapshots(correlation_id)
        validations = store.validations(correlation_id)
        events = store.events(correlation_id)
        commands = store.commands(correlation_id)

        if len(recommendations) < len(LAYER_SEQUENCE) or len(snapshots) < len(
            LAYER_SEQUENCE
        ) or not validations:
            issues.append("INCOMPLETE_CHAIN_RECORDS")

        minimum_events = len(recommendations) + len(validations)
        if generated.validation.passed:
            minimum_events += 1
        if len(events) < minimum_events:
            issues.append("INCOMPLETE_CHAIN_RECORDS")

        if generated.validation.passed:
            command_created = [
                event for event in events if event.event_type == "COMMAND_CREATED"
            ]
            if not commands or not command_created:
                issues.append("COMMAND_EVENT_MISMATCH")

    def _non_empty_actions(
        self,
        actions: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return [
            assignment
            for stage_actions in actions.values()
            for assignment in stage_actions.values()
            if assignment
        ]
