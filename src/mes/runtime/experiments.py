"""Policy experiment runner payload builders for the AI Developer Console."""

from __future__ import annotations

import copy
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from src.agents.factory import build_mes_policy_stack
from src.agents.mes_policies import RuleBasedL4ObjectivePolicy
from src.mes import MESDevelopmentHarness
from src.mes.recommendations import make_id
from src.mes.runtime.candidate_portfolio import candidate_portfolio
from src.mes.services import MESDecisionService
from src.mes.store import InMemoryMESStore


class StaticObjectivePolicy(RuleBasedL4ObjectivePolicy):
    """Experiment-only L4 policy that returns fixed objective weights."""

    def __init__(self, policy_id: str, model_id: str, objective_action: Dict[str, Any]):
        super().__init__({})
        self.policy_id = policy_id
        self.model_id = model_id
        self.model_version = "0.1.0"
        self._objective_action = copy.deepcopy(objective_action)

    def select_objective(
        self,
        decision_state: Dict[str, Any],
        trigger_due: bool,
        previous_action: Optional[Dict[str, Any]] = None,
        previous_objective_id: str = "OBJ_RULE_ONLY_BALANCED",
    ) -> Dict[str, Any]:
        return copy.deepcopy(self._objective_action)


POLICY_VARIANTS: List[Dict[str, Any]] = [
    {
        "variant_id": "baseline_fifo_rule",
        "label": "Baseline FIFO / Rule APC",
        "description": "Current MES policy stack: FIFO L1, rule-based L2, portfolio L3, cycle L4.",
        "config_overrides": {},
    },
    {
        "variant_id": "l3_due_date_aggressive",
        "label": "Due-Date Aggressive",
        "description": "Uses the same L3 candidate portfolio but forces L4 tardiness and customer weights high.",
        "config_overrides": {},
        "l4_policy_id": "L4_EXPERIMENT_DUE_DATE",
        "l4_model_id": "experiment-fixed-due-date-objective",
        "objective_action": {
            "objective_id": "OBJ_DUE_DATE_RECOVERY",
            "weights": {
                "throughput": 0.8,
                "yield": 1.0,
                "tardiness": 2.0,
                "cost": 0.2,
                "customer_priority": 1.6,
            },
        },
    },
    {
        "variant_id": "l3_throughput_aggressive",
        "label": "Throughput Aggressive",
        "description": "Uses the same L3 candidate portfolio but forces L4 throughput weight high.",
        "config_overrides": {},
        "l4_policy_id": "L4_EXPERIMENT_THROUGHPUT",
        "l4_model_id": "experiment-fixed-throughput-objective",
        "objective_action": {
            "objective_id": "OBJ_THROUGHPUT_FIRST",
            "weights": {
                "throughput": 2.0,
                "yield": 0.8,
                "tardiness": 0.4,
                "cost": 0.2,
                "customer_priority": 0.8,
            },
        },
    },
    {
        "variant_id": "c_grouped_packing",
        "label": "C Grouped Packing",
        "description": "Keeps FIFO A/B and rule L2 but generates C candidates by grouped material/customer packs.",
        "config_overrides": {
            "packing_C": "fifo",
            "mes_l1_C": "grouped",
        },
    },
    {
        "variant_id": "bottleneck_relief",
        "label": "Bottleneck Relief",
        "description": "Throughput-oriented baseline for comparing stage budget pressure.",
        "config_overrides": {},
        "l4_policy_id": "L4_EXPERIMENT_BOTTLENECK",
        "l4_model_id": "experiment-fixed-bottleneck-objective",
        "objective_action": {
            "objective_id": "OBJ_BOTTLENECK_RELIEF",
            "weights": {
                "throughput": 1.6,
                "yield": 1.0,
                "tardiness": 0.8,
                "cost": 0.2,
                "customer_priority": 1.0,
            },
        },
    },
]


def list_policy_variants() -> Dict[str, Any]:
    items = [
        {
            "variant_id": variant["variant_id"],
            "label": variant["label"],
            "description": variant["description"],
            "config_overrides": dict(variant.get("config_overrides") or {}),
            "objective_action": copy.deepcopy(variant.get("objective_action")),
            "l4_policy_id": variant.get("l4_policy_id", "L4_CYCLE_WEIGHT_RULE"),
        }
        for variant in POLICY_VARIANTS
    ]
    return {"count": len(items), "items": items}


def capture_scenario(context: Any) -> Dict[str, Any]:
    decision_state = copy.deepcopy(context.env.get_decision_state())
    scenario_id = make_id("SCN")
    scenario = {
        "scenario_id": scenario_id,
        "time": int(decision_state.get("time", 0) or 0),
        "source_correlation_id": context.last_correlation_id,
        "config": copy.deepcopy(context.env.config),
        "decision_state": decision_state,
        "tasks": copy.deepcopy(decision_state.get("tasks", {})),
        "A": copy.deepcopy(decision_state.get("A", {})),
        "B": copy.deepcopy(decision_state.get("B", {})),
        "C": copy.deepcopy(decision_state.get("C", {})),
        "equipment": _equipment_snapshot(decision_state),
        "kpis": copy.deepcopy(decision_state.get("kpis", {})),
    }
    context.scenario_snapshots[scenario_id] = copy.deepcopy(scenario)
    return copy.deepcopy(scenario)


def list_scenarios(context: Any) -> Dict[str, Any]:
    items = [
        _scenario_summary(scenario)
        for scenario in reversed(list(context.scenario_snapshots.values()))
    ]
    return {"count": len(items), "items": items}


def run_experiment(context: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    scenario_id = payload.get("scenario_id")
    if not scenario_id:
        scenario = capture_scenario(context)
    else:
        scenario = context.scenario_snapshots.get(str(scenario_id))
    if scenario is None:
        raise KeyError(f"unknown scenario_id: {scenario_id}")

    requested_variant_ids = payload.get("variant_ids") or [
        "baseline_fifo_rule",
        "c_grouped_packing",
    ]
    variants = [_variant_by_id(str(variant_id)) for variant_id in requested_variant_ids]
    experiment_id = make_id("EXP")
    results = [
        _run_variant_replay(
            scenario,
            variant,
            experiment_id=experiment_id,
            target_stage=payload.get("target_stage"),
        )
        for variant in variants
    ]
    experiment = {
        "experiment_id": experiment_id,
        "scenario_id": scenario["scenario_id"],
        "scenario": _scenario_summary(scenario),
        "count": len(results),
        "results": results,
        "comparison": _comparison_summary(results),
    }
    context.experiment_results[experiment_id] = copy.deepcopy(experiment)
    return copy.deepcopy(experiment)


def get_experiment(context: Any, experiment_id: str) -> Dict[str, Any]:
    experiment = context.experiment_results.get(experiment_id)
    if experiment is None:
        raise KeyError(f"unknown experiment_id: {experiment_id}")
    return copy.deepcopy(experiment)


def list_experiments(context: Any) -> Dict[str, Any]:
    items = [
        {
            "experiment_id": experiment["experiment_id"],
            "scenario_id": experiment["scenario_id"],
            "count": experiment["count"],
            "best_variant_id": experiment["comparison"].get("best_variant_id"),
        }
        for experiment in reversed(list(context.experiment_results.values()))
    ]
    return {"count": len(items), "items": items}


def _run_variant_replay(
    scenario: Dict[str, Any],
    variant: Dict[str, Any],
    experiment_id: str,
    target_stage: Optional[str] = None,
) -> Dict[str, Any]:
    decision_state = copy.deepcopy(scenario["decision_state"])
    config = copy.deepcopy(scenario.get("config") or {})
    config.update(copy.deepcopy(variant.get("config_overrides") or {}))
    stack = build_mes_policy_stack(config)
    if variant.get("objective_action"):
        l4_policy = StaticObjectivePolicy(
            str(variant.get("l4_policy_id")),
            str(variant.get("l4_model_id")),
            dict(variant["objective_action"]),
        )
        stack = replace(
            stack,
            l4_objective_policy=l4_policy,
            l4_policy_id=l4_policy.policy_id,
            config=config,
        )
    service = MESDecisionService(policy_stack=stack)
    harness = MESDevelopmentHarness(
        service=service,
        store=InMemoryMESStore(),
    )
    correlation_id = make_id("CORR_EXP")
    result = harness.run(
        decision_state,
        target_stage=target_stage,
        correlation_id=correlation_id,
    )
    portfolio = candidate_portfolio(SimpleNamespace(harness=harness), correlation_id)
    l3_action = result.generated.plan.stage_priority.recommended_action
    l2_action = _recommendation_action(result, "L2")
    selected_candidate = next(
        (item for item in portfolio.get("items", []) if item.get("selected")),
        None,
    )
    command = result.command.to_dict() if result.command is not None else None
    selected_stage = l3_action.get("selected_stage")
    task_count = len((command or {}).get("validated_command", {}).get("task_uids", []))
    return {
        "experiment_id": experiment_id,
        "scenario_id": scenario["scenario_id"],
        "variant_id": variant["variant_id"],
        "variant_label": variant["label"],
        "correlation_id": correlation_id,
        "policy_stack": {
            "factory_name": stack.factory_name,
            "l1_policy_id": stack.l1_policy_id,
            "l2_policy_id": stack.l2_policy_id,
            "l3_policy_id": stack.l3_policy_id,
            "l4_policy_id": stack.l4_policy_id,
            "config": copy.deepcopy(stack.config),
        },
        "l4_objective_id": result.generated.plan.objective.objective_id,
        "l3_policy_id": stack.l3_policy_id,
        "l4_policy_id": stack.l4_policy_id,
        "selected_stage": selected_stage,
        "selected_candidate_id": l3_action.get("selected_candidate_id"),
        "selected_candidate": selected_candidate,
        "candidate_count": portfolio.get("count", 0),
        "local_score": (selected_candidate or {}).get("local_score"),
        "upper_score": (selected_candidate or {}).get("upper_score"),
        "quality_risk": dict(l2_action or {}).get("quality_risk"),
        "command_valid": result.passed and result.command is not None,
        "validation_status": result.generated.validation.validation_status,
        "validation_reasons": list(result.generated.validation.reasons),
        "command": command,
        "portfolio": portfolio,
        "score_components": dict(l3_action.get("score_components") or {}),
        "kpi_delta": {
            "selected_task_count": task_count,
            "expected_wip_reduction": task_count if result.passed else 0,
            "expected_completion_delta": task_count if selected_stage == "C" and result.passed else 0,
            "command_count_delta": 1 if result.passed and result.command is not None else 0,
        },
    }


def _comparison_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {"best_variant_id": None, "decision_diff": []}
    best = max(
        results,
        key=lambda row: (
            float(row.get("upper_score") or 0.0),
            int(row.get("kpi_delta", {}).get("expected_wip_reduction", 0) or 0),
        ),
    )
    return {
        "best_variant_id": best.get("variant_id"),
        "best_reason": "highest_upper_score_then_expected_wip_reduction",
        "decision_diff": [
            {
                "variant_id": row.get("variant_id"),
                "selected_stage": row.get("selected_stage"),
                "selected_candidate_id": row.get("selected_candidate_id"),
                "upper_score": row.get("upper_score"),
                "quality_risk": row.get("quality_risk"),
                "command_valid": row.get("command_valid"),
            }
            for row in results
        ],
    }


def _variant_by_id(variant_id: str) -> Dict[str, Any]:
    for variant in POLICY_VARIANTS:
        if variant["variant_id"] == variant_id:
            return copy.deepcopy(variant)
    raise KeyError(f"unknown variant_id: {variant_id}")


def _recommendation_action(result: Any, layer_id: str) -> Dict[str, Any]:
    for recommendation in result.generated.recommendations:
        if recommendation.layer_id == layer_id:
            return dict(recommendation.recommended_action or {})
    return {}


def _scenario_summary(scenario: Dict[str, Any]) -> Dict[str, Any]:
    decision_state = scenario.get("decision_state", {})
    return {
        "scenario_id": scenario["scenario_id"],
        "time": scenario["time"],
        "source_correlation_id": scenario.get("source_correlation_id"),
        "task_count": len(decision_state.get("tasks", {})),
        "queue_sizes": {
            stage: len(decision_state.get(stage, {}).get("wait_pool_uids", []) or [])
            for stage in ("A", "B", "C")
        },
        "equipment_count": len(scenario.get("equipment", [])),
    }


def _equipment_snapshot(decision_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    equipment = []
    for stage in ("A", "B", "C"):
        for equipment_id, machine in sorted(
            decision_state.get(stage, {}).get("machines", {}).items()
        ):
            equipment.append(
                {
                    "equipment_id": str(equipment_id),
                    "stage": stage,
                    "status": machine.get("status"),
                    "batch_size": machine.get("batch_size"),
                    "current_batch_uids": list(machine.get("current_batch_uids", []) or []),
                    "finish_time": machine.get("finish_time"),
                }
            )
    return equipment
