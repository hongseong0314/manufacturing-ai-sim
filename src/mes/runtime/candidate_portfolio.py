"""Candidate portfolio payload builders for MES traceability APIs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def latest_candidate_portfolio(context: Any, run_id: Optional[str] = None) -> Dict[str, Any]:
    resolved_run_id = _resolve_run_id(context, run_id)
    snapshots = _portfolio_snapshots(context, resolved_run_id)
    if not snapshots:
        return _empty_payload(None, resolved_run_id)
    latest_empty = _latest_empty_snapshot(context, resolved_run_id)
    latest_actionable = _latest_actionable_snapshot(context, resolved_run_id)
    selected = latest_actionable or snapshots[-1]
    return candidate_portfolio(
        context,
        selected.correlation_id,
        run_id=resolved_run_id,
        last_actionable_correlation_id=(
            latest_actionable.correlation_id if latest_actionable else None
        ),
        latest_empty_correlation_id=latest_empty.correlation_id if latest_empty else None,
    )


def candidate_portfolio(
    context: Any,
    correlation_id: Optional[str],
    run_id: Optional[str] = None,
    last_actionable_correlation_id: Optional[str] = None,
    latest_empty_correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_run_id = _resolve_run_id(context, run_id)
    if not correlation_id:
        return _empty_payload(None, resolved_run_id)

    snapshot = _portfolio_snapshot(context, correlation_id, resolved_run_id)
    if snapshot is None:
        return _empty_payload(correlation_id, resolved_run_id)

    features = dict(snapshot.features or {})
    items = [
        _augment_candidate(context, correlation_id, dict(candidate), resolved_run_id)
        for candidate in features.get("candidates", [])
        if isinstance(candidate, dict)
    ]
    summary = portfolio_summary_from_items(features, items)
    is_actionable = _is_actionable(features, items)
    if last_actionable_correlation_id is None:
        actionable = _latest_actionable_snapshot(context, resolved_run_id)
        last_actionable_correlation_id = actionable.correlation_id if actionable else None
    if latest_empty_correlation_id is None:
        empty = _latest_empty_snapshot(context, resolved_run_id)
        latest_empty_correlation_id = empty.correlation_id if empty else None
    return {
        "correlation_id": correlation_id,
        "run_id": resolved_run_id,
        "feature_snapshot_id": snapshot.feature_snapshot_id,
        "kind": "ACTIONABLE" if is_actionable else "EMPTY",
        "is_actionable": is_actionable,
        "empty_reason": None if is_actionable else _empty_reason(features),
        "last_actionable_correlation_id": last_actionable_correlation_id,
        "latest_empty_correlation_id": latest_empty_correlation_id,
        "diagnostics": dict(features.get("diagnostics") or _default_diagnostics()),
        "count": len(items),
        "summary": summary,
        "items": items,
    }


def portfolio_summary(
    context: Any,
    correlation_id: Optional[str],
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    payload = candidate_portfolio(context, correlation_id, run_id=run_id)
    return payload["summary"]


def portfolio_summary_from_items(
    features: Dict[str, Any],
    items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    stage_counts = {"A": 0, "B": 0, "C": 0}
    selected_candidate_ids = []
    for item in items:
        stage = str(item.get("stage", "")).upper()
        if stage in stage_counts:
            stage_counts[stage] += 1
        if item.get("selected") and item.get("candidate_id"):
            selected_candidate_ids.append(str(item["candidate_id"]))
    selected_count = len(selected_candidate_ids)
    return {
        "count": len(items),
        "selected_count": selected_count,
        "rejected_count": max(0, len(items) - selected_count),
        "stage_counts": stage_counts,
        "selected_candidate_id": features.get("selected_candidate_id"),
        "selected_candidate_ids": selected_candidate_ids,
        "selected_group_key": dict(features.get("selected_group_key") or {}),
        "objective_id": features.get("objective_id"),
        "l4_policy_id": features.get("l4_policy_id"),
        "l3_policy_id": features.get("l3_policy_id"),
    }


def _empty_payload(correlation_id: Optional[str], run_id: str = "") -> Dict[str, Any]:
    return {
        "correlation_id": correlation_id,
        "run_id": run_id,
        "feature_snapshot_id": None,
        "kind": "EMPTY",
        "is_actionable": False,
        "empty_reason": "NO_PORTFOLIO_SNAPSHOT",
        "last_actionable_correlation_id": None,
        "latest_empty_correlation_id": None,
        "diagnostics": _default_diagnostics(),
        "count": 0,
        "summary": portfolio_summary_from_items({}, []),
        "items": [],
    }


def _portfolio_snapshots(context: Any, run_id: Optional[str] = None) -> List[Any]:
    return [
        snapshot
        for snapshot in context.harness.store.feature_snapshots(run_id=run_id)
        if snapshot.layer_id == "PORTFOLIO"
    ]


def _latest_actionable_snapshot(context: Any, run_id: Optional[str] = None) -> Optional[Any]:
    for snapshot in reversed(_portfolio_snapshots(context, run_id)):
        features = dict(snapshot.features or {})
        items = [
            dict(candidate)
            for candidate in features.get("candidates", [])
            if isinstance(candidate, dict)
        ]
        if _is_actionable(features, items):
            return snapshot
    return None


def _latest_empty_snapshot(context: Any, run_id: Optional[str] = None) -> Optional[Any]:
    for snapshot in reversed(_portfolio_snapshots(context, run_id)):
        features = dict(snapshot.features or {})
        items = [
            dict(candidate)
            for candidate in features.get("candidates", [])
            if isinstance(candidate, dict)
        ]
        if not _is_actionable(features, items):
            return snapshot
    return None


def _latest_portfolio_snapshot(context: Any) -> Optional[Any]:
    snapshots = _portfolio_snapshots(context)
    return snapshots[-1] if snapshots else None


def _portfolio_snapshot(
    context: Any,
    correlation_id: str,
    run_id: Optional[str] = None,
) -> Optional[Any]:
    snapshots = [
        snapshot
        for snapshot in context.harness.store.feature_snapshots(correlation_id, run_id=run_id)
        if snapshot.layer_id == "PORTFOLIO"
    ]
    return snapshots[-1] if snapshots else None


def _augment_candidate(
    context: Any,
    correlation_id: str,
    candidate: Dict[str, Any],
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    candidate_id = str(candidate.get("candidate_id") or "")
    linked = dict(candidate.get("linked_recommendation_ids") or {})
    command_id = None
    command_status = None

    for recommendation in context.harness.store.recommendations(correlation_id, run_id=run_id):
        action = dict(recommendation.recommended_action or {})
        if action.get("candidate_id") != candidate_id:
            continue
        linked[recommendation.layer_id] = recommendation.recommendation_id
        if recommendation.final_command_id:
            command_id = recommendation.final_command_id

    if command_id:
        for command in context.harness.store.commands(correlation_id, run_id=run_id):
            if command.command_id == command_id:
                command_status = command.status
                break

    candidate["linked_recommendation_ids"] = linked
    candidate["command_id"] = command_id
    candidate["command_status"] = command_status or (
        "EXECUTED" if command_id else "NOT_SELECTED"
    )
    components = dict(candidate.get("score_components") or {})
    components.setdefault(
        "quality_risk_penalty",
        _quality_risk_penalty(candidate.get("l2_annotation") or {}),
    )
    if "final_upper_score" not in components and "upper_score" in candidate:
        components["final_upper_score"] = candidate.get("upper_score")
    candidate["score_components"] = components
    return candidate


def _resolve_run_id(context: Any, run_id: Optional[str]) -> str:
    return str(run_id or getattr(context, "run_id", "") or context.harness.store.current_run_id)


def _is_actionable(features: Dict[str, Any], items: List[Dict[str, Any]]) -> bool:
    selected_id = features.get("selected_candidate_id")
    if not selected_id or not items:
        return False
    return any(
        item.get("selected") and item.get("candidate_id") == selected_id
        for item in items
    )


def _empty_reason(features: Dict[str, Any]) -> str:
    reason = features.get("empty_reason")
    if reason:
        return str(reason)
    diagnostics = dict(features.get("diagnostics") or {})
    stages = dict(diagnostics.get("stages") or {})
    if any(
        stage.get("queue_size", 0) > 0 and stage.get("idle_machines", 0) == 0
        for stage in stages.values()
        if isinstance(stage, dict)
    ):
        return "ALL_EQUIPMENT_BUSY"
    if stages and all(
        int(stage.get("queue_size", 0) or 0) == 0
        for stage in stages.values()
        if isinstance(stage, dict)
    ):
        return "NO_WAIT_POOL"
    return "NO_ELIGIBLE_CANDIDATES"


def _quality_risk_penalty(annotation: Dict[str, Any]) -> float:
    return {
        "LOW": 0.0,
        "MEDIUM": 8.0,
        "HIGH": 25.0,
    }.get(str(annotation.get("quality_risk", "LOW")).upper(), 0.0)


def _default_diagnostics() -> Dict[str, Any]:
    return {
        "stages": {
            stage: {
                "queue_size": 0,
                "idle_machines": 0,
                "running_machines": 0,
                "batch_size": 1,
                "batch_ready": False,
                "candidate_count": 0,
            }
            for stage in ("A", "B", "C")
        }
    }
