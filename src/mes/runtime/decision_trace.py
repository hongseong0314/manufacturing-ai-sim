"""Decision-chain and traceability payload builders."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def latest_correlation_id(context: Any) -> Optional[str]:
    if context.last_correlation_id:
        return context.last_correlation_id
    commands = context.harness.store.commands()
    if commands:
        return commands[-1].correlation_id
    events = context.harness.store.events()
    if events:
        return events[-1].correlation_id
    return None


def decision_chain(context: Any, correlation_id: Optional[str]) -> Dict[str, Any]:
    if not correlation_id:
        return {
            "correlation_id": None,
            "recommendations": [],
            "events": [],
            "validations": [],
            "commands": [],
            "counts": {"recommendations": 0, "events": 0, "validations": 0, "commands": 0},
        }
    recommendations = context.harness.store.recommendations(correlation_id)
    layer_order = {layer: index for index, layer in enumerate(("L4", "L3", "L1", "L2"))}
    recommendations = sorted(
        recommendations,
        key=lambda rec: layer_order.get(rec.layer_id, 99),
    )
    events = context.harness.store.events(correlation_id)
    validations = context.harness.store.validations(correlation_id)
    commands = context.harness.store.commands(correlation_id)
    validation_status = validations[-1].validation_status if validations else "PENDING"
    recommendation_dicts = [item.to_dict() for item in recommendations]
    return {
        "correlation_id": correlation_id,
        "recommendations": recommendation_dicts,
        "events": [item.to_dict() for item in events],
        "validations": [item.to_dict() for item in validations],
        "commands": [item.to_dict() for item in commands],
        "traceability": chain_traceability(recommendation_dicts, commands),
        "validation_status": validation_status,
        "counts": {
            "recommendations": len(recommendations),
            "events": len(events),
            "validations": len(validations),
            "commands": len(commands),
        },
    }


def chain_traceability(
    recommendations: List[Dict[str, Any]],
    commands: List[Any],
) -> Dict[str, Any]:
    by_layer = {item.get("layer_id"): item for item in recommendations}
    l4 = by_layer.get("L4", {})
    l3 = by_layer.get("L3", {})
    l1 = by_layer.get("L1", {})
    l2 = by_layer.get("L2", {})
    l3_action = dict(l3.get("recommended_action") or {})
    selected_ids = set(l3_action.get("selected_candidate_ids") or [])
    selected_id = l3_action.get("selected_candidate_id")
    if selected_id:
        selected_ids.add(selected_id)
    candidate_actions = [
        candidate
        for candidate in l3.get("candidate_actions", [])
        if isinstance(candidate, dict)
    ]
    selected_candidates = [
        candidate
        for candidate in candidate_actions
        if candidate.get("candidate_id") in selected_ids
    ]
    l2_actions = [
        action
        for action in l2.get("candidate_actions", [])
        if isinstance(action, dict)
    ]
    command_dict = commands[-1].to_dict() if commands else {}
    validated_command = command_dict.get("validated_command", {})
    return {
        "objective_id": l4.get("objective_id"),
        "l4_policy_id": l4.get("policy_id"),
        "l3_policy_id": l3.get("policy_id"),
        "objective_weights": dict((l4.get("recommended_action") or {}).get("weights") or {}),
        "stage_priorities": dict(l3_action.get("stage_priorities") or {}),
        "dispatch_budgets": dict(l3_action.get("dispatch_budgets") or {}),
        "budget_candidate_ids": dict(l3_action.get("budget_candidate_ids") or {}),
        "selected_candidate_id": selected_id,
        "selected_candidate_ids": list(l3_action.get("selected_candidate_ids") or []),
        "selected_group_key": dict(l3_action.get("selected_group_key") or {}),
        "candidate_count": len(candidate_actions),
        "selected_candidates": selected_candidates,
        "l2_annotation_count": len(l2_actions),
        "l2_annotations": l2_actions,
        "final_l1_action": dict(l1.get("recommended_action") or {}),
        "final_l2_action": dict(l2.get("recommended_action") or {}),
        "command": validated_command,
    }
