# -*- coding: utf-8 -*-
"""Domain records for the MES shell.

These dataclasses intentionally sit outside the simulator kernel. They describe
MES-facing DTOs and audit records while `src.environment` continues to own
physics and state transitions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Product:
    product_id: str
    product_family: str = "standard"
    priority_class: str = "normal"
    default_route_id: str = "ROUTE_DEFAULT"
    spec_profile_id: str = "SPEC_DEFAULT"
    customer_id: str = "UNKNOWN"
    margin_value: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Lot:
    lot_id: str
    product_id: str
    route_id: str = "ROUTE_DEFAULT"
    current_operation_id: str = "A"
    carrier_id: str = ""
    status: str = "WAIT"
    priority: float = 1.0
    due_date: int = 0
    quantity: int = 0
    rework_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Wafer:
    wafer_id: str
    lot_id: str
    slot_no: int = 0
    status: str = "WAIT"
    current_operation_id: str = "A"
    qa_results: Dict[str, Any] = field(default_factory=dict)
    genealogy_parent_ids: List[str] = field(default_factory=list)
    genealogy_child_ids: List[str] = field(default_factory=list)
    task_uid: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Carrier:
    carrier_id: str
    carrier_type: str = "FOUP"
    location: str = ""
    status: str = "AVAILABLE"
    lot_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Equipment:
    equipment_id: str
    equipment_group_id: str
    status: str = "IDLE"
    current_lot_id: str = ""
    current_recipe_id: str = ""
    capable_operations: List[str] = field(default_factory=list)
    batch_size: int = 1
    health_state: Dict[str, Any] = field(default_factory=dict)
    last_event_time: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Recipe:
    recipe_id: str
    recipe_version: str = "v1"
    operation_id: str = ""
    equipment_group_id: str = ""
    approval_status: str = "APPROVED"
    parameter_set: Dict[str, Any] = field(default_factory=dict)
    control_limits: Dict[str, Any] = field(default_factory=dict)
    download_status: str = "VERIFIED"
    compare_result: str = "MATCH"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FeatureSnapshot:
    feature_snapshot_id: str
    correlation_id: str
    layer_id: str
    source: str
    decision_state: Dict[str, Any]
    features: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AIRecommendation:
    recommendation_id: str
    recommendation_type: str
    layer_id: str
    objective_id: str
    policy_id: str
    model_id: str
    model_version: str
    feature_snapshot_id: str
    correlation_id: str
    candidate_actions: List[Dict[str, Any]] = field(default_factory=list)
    recommended_action: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)
    parent_recommendation_id: Optional[str] = None
    rule_validation_status: str = "PENDING"
    rule_validation_reasons: List[str] = field(default_factory=list)
    final_command_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Event:
    event_id: str
    event_type: str
    correlation_id: str
    actor_type: str = "SYSTEM"
    recommendation_id: Optional[str] = None
    parent_recommendation_id: Optional[str] = None
    layer_id: Optional[str] = None
    lot_id: Optional[str] = None
    wafer_ids: List[str] = field(default_factory=list)
    equipment_id: Optional[str] = None
    operation_id: Optional[str] = None
    recipe_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MESCommand:
    command_id: str
    command_type: str
    correlation_id: str
    validation_status: str
    status: str = "CREATED"
    validated_command: Dict[str, Any] = field(default_factory=dict)
    simulator_actions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Genealogy:
    genealogy_id: str
    parent_entity_type: str
    parent_entity_id: str
    child_entity_type: str
    child_entity_id: str
    operation_id: str
    equipment_id: str
    event_id: str
    correlation_id: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RuleValidationResult:
    validation_status: str
    correlation_id: str = ""
    reasons: List[str] = field(default_factory=list)
    validated_command: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.validation_status == "PASSED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
