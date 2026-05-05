# -*- coding: utf-8 -*-
"""Planner -> generator -> evaluator harness for MES decision chains."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import copy
import math
from typing import Any, Dict, Iterable, List, Optional, Sequence

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
from src.mes.domain import (
    AIRecommendation,
    FeatureSnapshot,
    MESCommand,
    RuleValidationResult,
)
from src.mes.recommendations import create_recommendation, make_id
from src.mes.services import MESDecisionService
from src.mes.store import InMemoryMESStore


LAYER_SEQUENCE = ("L4", "L3", "L1", "L2")


@dataclass
class HarnessPlan:
    """Planner output for one simulator-backed MES decision cycle."""

    correlation_id: str
    target_stage: str
    objective: AIRecommendation
    stage_priority: AIRecommendation
    feature_snapshots: List[FeatureSnapshot] = field(default_factory=list)

    @property
    def recommendations(self) -> List[AIRecommendation]:
        return [self.objective, self.stage_priority]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "target_stage": self.target_stage,
            "objective": self.objective.to_dict(),
            "stage_priority": self.stage_priority.to_dict(),
            "feature_snapshots": [
                snapshot.to_dict() for snapshot in self.feature_snapshots
            ],
        }


@dataclass
class GeneratedDecision:
    """Generator output before/after rule validation."""

    plan: HarnessPlan
    recommendations: List[AIRecommendation]
    validation: RuleValidationResult
    simulator_actions: Dict[str, Dict[str, Any]]
    feature_snapshots: List[FeatureSnapshot] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "recommendations": [rec.to_dict() for rec in self.recommendations],
            "validation": self.validation.to_dict(),
            "simulator_actions": self.simulator_actions,
            "feature_snapshots": [
                snapshot.to_dict() for snapshot in self.feature_snapshots
            ],
        }


@dataclass
class GeneratedCycle:
    """One generator cycle artifact for continuous scheduling."""

    index: int
    generated: GeneratedDecision

    def to_dict(self) -> Dict[str, Any]:
        return {"index": self.index, "generated": self.generated.to_dict()}


@dataclass
class HarnessEvaluationReport:
    """Evaluator output for decision-chain connectivity."""

    status: str
    issues: List[str] = field(default_factory=list)
    checked: Dict[str, bool] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "PASSED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HarnessRunResult:
    """Full harness run artifact."""

    generated: GeneratedDecision
    evaluation: HarnessEvaluationReport
    command: Optional[MESCommand] = None
    step_result: Optional[Dict[str, Any]] = None

    @property
    def passed(self) -> bool:
        return self.evaluation.passed

    @property
    def simulator_actions(self) -> Dict[str, Dict[str, Any]]:
        return self.generated.simulator_actions

    @property
    def recommendations(self) -> List[AIRecommendation]:
        return self.generated.recommendations

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated": self.generated.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "command": self.command.to_dict() if self.command is not None else None,
            "step_result": self.step_result,
        }


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
    ) -> HarnessPlan:
        resolved_correlation_id = correlation_id or make_id("CORR")
        now = int(decision_state.get("time", 0) or 0)
        trigger_due = (now % self.planning_interval) == 0

        objective_action = self._select_objective_action(decision_state, trigger_due)
        resolved_stage = (target_stage or self._select_stage(decision_state)).upper()

        l4_snapshot = self.service.create_feature_snapshot(
            decision_state,
            layer_id="L4",
            correlation_id=resolved_correlation_id,
            features=self._objective_features(decision_state, trigger_due),
        )
        objective = create_recommendation(
            recommendation_type="OBJECTIVE",
            layer_id="L4",
            objective_id=objective_action["objective_id"],
            policy_id="PLANNER_RULE_ONLY_BASELINE",
            model_id="mes-planner",
            model_version="0.1.0",
            feature_snapshot_id=l4_snapshot.feature_snapshot_id,
            correlation_id=resolved_correlation_id,
            candidate_actions=[
                {"objective_id": "OBJ_THROUGHPUT_FIRST"},
                {"objective_id": "OBJ_YIELD_FIRST"},
                {"objective_id": "OBJ_RULE_ONLY_BALANCED"},
            ],
            recommended_action=objective_action,
            score=1.0,
            confidence=1.0,
            reasons=[
                "objective_trigger_due"
                if trigger_due
                else "objective_reused_until_next_trigger"
            ],
        )

        stage_priorities = {
            stage: 1.0 if stage == resolved_stage else 0.0 for stage in ("A", "B", "C")
        }
        l3_snapshot = self.service.create_feature_snapshot(
            decision_state,
            layer_id="L3",
            correlation_id=resolved_correlation_id,
            features={
                "stage_priorities": stage_priorities,
                "target_stage": resolved_stage,
                "objective_id": objective_action["objective_id"],
                "task_generation_trigger_due": trigger_due,
            },
        )
        stage_priority = create_recommendation(
            recommendation_type="STAGE_PRIORITY",
            layer_id="L3",
            objective_id=objective.objective_id,
            policy_id="PLANNER_STAGE_PRIORITY_BASELINE",
            model_id="mes-planner",
            model_version="0.1.0",
            feature_snapshot_id=l3_snapshot.feature_snapshot_id,
            correlation_id=resolved_correlation_id,
            parent_recommendation_id=objective.recommendation_id,
            candidate_actions=[
                {"stage": stage, "priority": priority}
                for stage, priority in stage_priorities.items()
            ],
            recommended_action={
                "target_stage": resolved_stage,
                "stage_priorities": stage_priorities,
                "task_generation_trigger_due": trigger_due,
            },
            score=1.0,
            confidence=1.0,
            reasons=[
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
        )

    def _select_stage(self, decision_state: Dict[str, Any]) -> str:
        for stage in ("A", "B", "C"):
            if self.service.dispatch_candidates(decision_state, stage=stage):
                return stage
        return "A"

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

    def _select_objective_action(
        self,
        decision_state: Dict[str, Any],
        trigger_due: bool,
    ) -> Dict[str, Any]:
        if not trigger_due and self._last_objective_action:
            return copy.deepcopy(self._last_objective_action)

        mes_state = self.service.decision_state_to_mes(decision_state)
        kpis = mes_state.get("kpis", {})
        tardiness = float(kpis.get("tardiness", 0.0) or 0.0)
        wait_total = 0
        for stage in ("A", "B", "C"):
            wait_total += len(decision_state.get(stage, {}).get("wait_pool_uids", []))

        if tardiness > 0:
            return {
                "objective_id": "OBJ_DUE_DATE_RECOVERY",
                "weights": {
                    "throughput": 0.8,
                    "yield": 1.0,
                    "tardiness": 1.4,
                    "cost": 0.2,
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
            "objective_id": self._last_objective_id,
            "weights": {
                "throughput": 1.0,
                "yield": 1.0,
                "tardiness": 0.5,
                "cost": 0.2,
            },
        }


class MESGeneratorAgent:
    """Generate dispatch/recipe recommendations and simulator actions."""

    def __init__(self, service: Optional[MESDecisionService] = None):
        self.service = service or MESDecisionService()

    def generate(
        self,
        decision_state: Dict[str, Any],
        plan: HarnessPlan,
    ) -> GeneratedDecision:
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
            },
        )
        dispatch_action = candidates[0]
        dispatch = create_recommendation(
            recommendation_type="DISPATCH" if plan.target_stage != "C" else "PACK",
            layer_id="L1",
            objective_id=plan.objective.objective_id,
            policy_id="GENERATOR_RULE_ONLY_DISPATCH",
            model_id="mes-generator",
            model_version="0.1.0",
            feature_snapshot_id=l1_snapshot.feature_snapshot_id,
            correlation_id=plan.correlation_id,
            parent_recommendation_id=plan.stage_priority.recommendation_id,
            candidate_actions=candidates,
            recommended_action=dispatch_action,
            score=1.0,
            confidence=1.0,
            reasons=["selected_first_rule_eligible_candidate"],
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
            },
        )
        recipe = create_recommendation(
            recommendation_type="RECIPE",
            layer_id="L2",
            objective_id=plan.objective.objective_id,
            policy_id="GENERATOR_DEFAULT_RECIPE",
            model_id="mes-generator",
            model_version="0.1.0",
            feature_snapshot_id=l2_snapshot.feature_snapshot_id,
            correlation_id=plan.correlation_id,
            parent_recommendation_id=dispatch.recommendation_id,
            candidate_actions=[recipe_action],
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
        if stage == "A":
            return self._recipe_action_a(dispatch_action or {}, decision_state or {})
        if stage == "B":
            return {
                "recipe_id": "SIM_B_DEFAULT",
                "recipe": [50.0, 50.0, 30.0],
                "parameters": {"chem_a": 50.0, "chem_b": 50.0, "time": 30.0},
                "replace_solution": False,
                "apc_mode": "L1L2_COMPOSED",
            }
        return {"recipe_id": "SIM_C_NO_RECIPE", "recipe": [], "apc_mode": "L1L2_COMPOSED"}

    def _recipe_action_a(
        self,
        dispatch_action: Dict[str, Any],
        decision_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        equipment_id = str(dispatch_action.get("equipment_id", ""))
        machine_state = self._machine_state(decision_state, "A", equipment_id)
        task_rows = self._task_rows(decision_state, dispatch_action.get("task_uids", []))
        spec_low, spec_high = self._spec_window(task_rows, "spec_a", (47.1, 52.9))
        target = (spec_low + spec_high) / 2.0
        current_u = float(machine_state.get("u", 0))
        current_age = float(machine_state.get("m_age", 0))

        recipes = [
            ("SIM_A_BASE", [10.0, 2.0, 1.0]),
            ("SIM_A_MEDIUM_APC", [12.0, 2.5, 1.2]),
            ("SIM_A_STRONG_APC", [15.0, 3.0, 1.5]),
            ("SIM_A_AGE_APC", [18.0, 4.0, 2.0]),
        ]
        must_refresh = current_u >= 5
        candidates = []
        for recipe_id, recipe in recipes:
            for replace_consumable in (False, True):
                if must_refresh and not replace_consumable:
                    continue
                predicted_qa = self._predict_a_qa(
                    recipe=recipe,
                    current_u=current_u,
                    current_age=current_age,
                    replace_consumable=replace_consumable,
                )
                in_spec = spec_low <= predicted_qa <= spec_high
                distance = abs(predicted_qa - target) if in_spec else (
                    min(abs(predicted_qa - spec_low), abs(predicted_qa - spec_high)) + 100.0
                )
                replacement_penalty = 0.0 if must_refresh else (0.35 if replace_consumable else 0.0)
                recipe_penalty = 0.02 * sum(recipe)
                candidates.append(
                    {
                        "recipe_id": recipe_id,
                        "recipe": recipe,
                        "replace_consumable": replace_consumable,
                        "predicted_qa": predicted_qa,
                        "in_spec": in_spec,
                        "score": distance + replacement_penalty + recipe_penalty,
                    }
                )

        selected = min(candidates, key=lambda item: item["score"])
        recipe = selected["recipe"]
        if selected["replace_consumable"]:
            reason = "apc_refresh_consumable_before_quality_drift"
        elif selected["recipe_id"] != "SIM_A_BASE":
            reason = "apc_recipe_compensates_machine_age_or_consumable_use"
        else:
            reason = "default_recipe_within_spec"

        return {
            "recipe_id": selected["recipe_id"],
            "recipe": recipe,
            "parameters": {"temp": recipe[0], "flow": recipe[1], "duration": recipe[2]},
            "replace_consumable": bool(selected["replace_consumable"]),
            "apc_mode": "L1L2_COMPOSED",
            "apc_policy": "A_SPEC_WINDOW_GRID_SEARCH",
            "predicted_qa": round(float(selected["predicted_qa"]), 4),
            "target_spec": {"low": spec_low, "high": spec_high, "target": target},
            "machine_state": {"u": current_u, "m_age": current_age},
            "selection_reason": reason,
        }

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
            if str(machine_id).split("_")[-1] == suffix and isinstance(machine_state, dict):
                return machine_state
        return {}

    def _task_rows(
        self,
        decision_state: Dict[str, Any],
        task_uids: Any,
    ) -> List[Dict[str, Any]]:
        tasks = decision_state.get("tasks", {})
        rows = []
        for uid in task_uids if isinstance(task_uids, list) else []:
            row = tasks.get(uid) or tasks.get(str(uid))
            if isinstance(row, dict):
                rows.append(row)
        return rows

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
        self._check_validation(generated.validation, issues)
        self._check_simulator_actions(generated, issues)
        if store is not None:
            self._check_cycle_integrity(generated, store, issues)

        checked = {
            "required_layers": all(layer in by_layer for layer in LAYER_SEQUENCE),
            "single_correlation_id": "CORRELATION_ID_MISMATCH" not in issues,
            "feature_snapshots": "MISSING_FEATURE_SNAPSHOT_ID" not in issues,
            "parent_chain": "BROKEN_PARENT_CHAIN" not in issues,
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


class MESDevelopmentHarness:
    """Run planner -> generator -> evaluator over one MES decision cycle."""

    def __init__(
        self,
        service: Optional[MESDecisionService] = None,
        planner: Optional[MESPlannerAgent] = None,
        generator: Optional[MESGeneratorAgent] = None,
        evaluator: Optional[MESEvaluatorAgent] = None,
        store: Optional[InMemoryMESStore] = None,
    ):
        self.service = service or MESDecisionService()
        self.planner = planner or MESPlannerAgent(self.service)
        self.generator = generator or MESGeneratorAgent(self.service)
        self.evaluator = evaluator or MESEvaluatorAgent()
        self.store = store or InMemoryMESStore()

    def run(
        self,
        decision_state: Dict[str, Any],
        target_stage: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> HarnessRunResult:
        plan = self.planner.plan(
            decision_state,
            target_stage=target_stage,
            correlation_id=correlation_id,
        )
        generated = self.generator.generate(decision_state, plan)
        pre_evaluation = self.evaluator.evaluate(generated)
        result = HarnessRunResult(generated=generated, evaluation=pre_evaluation)
        result.command = self.store.record_harness_result(generated, pre_evaluation)
        result.evaluation = self.evaluator.evaluate(generated, store=self.store)
        return result

    def run_to_simulator_actions(
        self,
        decision_state: Dict[str, Any],
        target_stage: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        result = self.run(decision_state, target_stage=target_stage)
        if not result.passed:
            return {"A": {}, "B": {}, "C": {}}
        return result.simulator_actions

    def run_and_step(
        self,
        env: Any,
        target_stage: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> HarnessRunResult:
        """Run one audited MES cycle and execute it against the simulator."""
        result = self.run(
            env.get_decision_state(),
            target_stage=target_stage,
            correlation_id=correlation_id,
        )
        if not result.passed or result.command is None:
            return result

        observation, reward, done, info = env.step(result.simulator_actions)
        result.step_result = {
            "observation": observation,
            "reward": reward,
            "done": done,
            "info": info,
        }
        self.store.record_command_executed(
            result.command.command_id,
            step_result=result.step_result,
            post_decision_state=env.get_decision_state(),
        )
        return result
