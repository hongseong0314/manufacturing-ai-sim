"""AI developer console payload builders."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.mes.runtime.candidate_portfolio import candidate_portfolio


def policy_stack_payload(context: Any) -> Dict[str, Any]:
    stack = context.harness.service.policy_stack
    config = dict(stack.config or {})
    l3 = stack.l3_meta_scheduler
    l4 = stack.l4_objective_policy
    return {
        "factory_name": stack.factory_name,
        "config": config,
        "l1_policy_id": stack.l1_policy_id,
        "l2_policy_id": stack.l2_policy_id,
        "l3_policy_id": stack.l3_policy_id,
        "l4_policy_id": stack.l4_policy_id,
        "scheduler_A": config.get("scheduler_A"),
        "scheduler_B": config.get("scheduler_B"),
        "packing_C": config.get("packing_C"),
        "tuner_A": config.get("tuner_A"),
        "tuner_B": config.get("tuner_B"),
        "meta_scheduler_L3": config.get("meta_scheduler_L3"),
        "objective_policy_L4": config.get("objective_policy_L4"),
        "layers": {
            "L1": {
                "policy_id": stack.l1_policy_id,
                "model_id": "factory-built-local-dispatch",
                "model_version": "0.1.0",
                "config_source": stack.factory_name,
            },
            "L2": {
                "policy_id": stack.l2_policy_id,
                "model_id": "factory-built-rule-apc",
                "model_version": "0.1.0",
                "config_source": stack.factory_name,
            },
            "L3": {
                "policy_id": stack.l3_policy_id,
                "model_id": getattr(l3, "model_id", "mes-l3-meta-scheduler"),
                "model_version": getattr(l3, "model_version", "0.1.0"),
                "config_source": stack.factory_name,
            },
            "L4": {
                "policy_id": stack.l4_policy_id,
                "model_id": getattr(l4, "model_id", "mes-l4-objective-policy"),
                "model_version": getattr(l4, "model_version", "0.1.0"),
                "config_source": stack.factory_name,
            },
        },
    }


def decision_cycles_payload(context: Any, limit: int = 50) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    snapshots = [
        snapshot
        for snapshot in context.harness.store.feature_snapshots()
        if snapshot.layer_id == "PORTFOLIO"
    ]
    for snapshot in reversed(snapshots):
        correlation_id = snapshot.correlation_id
        if correlation_id in seen:
            continue
        seen.add(correlation_id)
        rows.append(_decision_cycle_row(context, snapshot))
        if len(rows) >= limit:
            break
    return {"count": len(rows), "items": rows}


def ai_dev_candidate_portfolio(
    context: Any,
    correlation_id: Optional[str],
) -> Dict[str, Any]:
    payload = candidate_portfolio(context, correlation_id)
    objective = _recommendation_by_layer(context, correlation_id, "L4")
    l3 = _recommendation_by_layer(context, correlation_id, "L3")
    weights = dict((objective or {}).get("recommended_action", {}).get("weights") or {})
    payload["objective_weights"] = weights
    payload["objective_action"] = dict((objective or {}).get("recommended_action") or {})
    payload["l3_action"] = dict((l3 or {}).get("recommended_action") or {})
    payload["policy_stack"] = policy_stack_payload(context)
    payload["selected_candidate"] = next(
        (item for item in payload["items"] if item.get("selected")),
        None,
    )
    return payload


def _decision_cycle_row(context: Any, snapshot: Any) -> Dict[str, Any]:
    correlation_id = snapshot.correlation_id
    portfolio = candidate_portfolio(context, correlation_id)
    summary = dict(portfolio.get("summary") or {})
    l4 = _recommendation_by_layer(context, correlation_id, "L4")
    l3 = _recommendation_by_layer(context, correlation_id, "L3")
    l3_action = dict((l3 or {}).get("recommended_action") or {})
    validations = context.harness.store.validations(correlation_id)
    commands = context.harness.store.commands(correlation_id)
    validation_status = (
        validations[-1].validation_status if validations else "PENDING"
    )
    command_status = commands[-1].status if commands else "NONE"
    return {
        "correlation_id": correlation_id,
        "time": snapshot.decision_state.get("time"),
        "objective_id": summary.get("objective_id") or (l4 or {}).get("objective_id"),
        "selected_stage": l3_action.get("selected_stage"),
        "selected_candidate_id": summary.get("selected_candidate_id"),
        "candidate_count": summary.get("count", 0),
        "selected_count": summary.get("selected_count", 0),
        "rejected_count": summary.get("rejected_count", 0),
        "validation_status": validation_status,
        "command_status": command_status,
        "is_actionable": portfolio.get("is_actionable", False),
        "empty_reason": portfolio.get("empty_reason"),
    }


def _recommendation_by_layer(
    context: Any,
    correlation_id: Optional[str],
    layer_id: str,
) -> Dict[str, Any]:
    for recommendation in context.harness.store.recommendations(correlation_id):
        if recommendation.layer_id == layer_id:
            return recommendation.to_dict()
    return {}
