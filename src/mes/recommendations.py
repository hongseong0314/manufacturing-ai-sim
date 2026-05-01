# -*- coding: utf-8 -*-
"""Helpers for constructing recommendation envelope records."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.mes.domain import AIRecommendation, Event


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12].upper()}"


def create_recommendation(
    recommendation_type: str,
    layer_id: str,
    objective_id: str,
    policy_id: str,
    model_id: str,
    model_version: str,
    feature_snapshot_id: str,
    correlation_id: Optional[str] = None,
    candidate_actions: Optional[List[Dict[str, Any]]] = None,
    recommended_action: Optional[Dict[str, Any]] = None,
    score: float = 0.0,
    confidence: float = 0.0,
    reasons: Optional[List[str]] = None,
    parent_recommendation_id: Optional[str] = None,
    recommendation_id: Optional[str] = None,
) -> AIRecommendation:
    """Create a standard MES recommendation envelope."""
    resolved_correlation_id = correlation_id or make_id("CORR")
    return AIRecommendation(
        recommendation_id=recommendation_id or make_id(f"REC_{layer_id}"),
        recommendation_type=recommendation_type,
        layer_id=layer_id,
        objective_id=objective_id,
        policy_id=policy_id,
        model_id=model_id,
        model_version=model_version,
        feature_snapshot_id=feature_snapshot_id,
        parent_recommendation_id=parent_recommendation_id,
        correlation_id=resolved_correlation_id,
        candidate_actions=list(candidate_actions or []),
        recommended_action=dict(recommended_action or {}),
        score=score,
        confidence=confidence,
        reasons=list(reasons or []),
    )


def recommendation_event(
    recommendation: AIRecommendation,
    event_type: Optional[str] = None,
) -> Event:
    """Build an audit event from a recommendation envelope."""
    resolved_event_type = event_type or f"{recommendation.recommendation_type}_RECOMMENDED"
    return Event(
        event_id=make_id("EVT"),
        event_type=resolved_event_type,
        correlation_id=recommendation.correlation_id,
        actor_type="AI",
        recommendation_id=recommendation.recommendation_id,
        parent_recommendation_id=recommendation.parent_recommendation_id,
        layer_id=recommendation.layer_id,
        payload=recommendation.to_dict(),
    )

