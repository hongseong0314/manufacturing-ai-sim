# -*- coding: utf-8 -*-
"""DTO artifacts for MES harness runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from src.mes.domain import AIRecommendation, FeatureSnapshot, MESCommand, RuleValidationResult


@dataclass
class HarnessPlan:
    """Planner output for one simulator-backed MES decision cycle."""

    correlation_id: str
    target_stage: str
    objective: AIRecommendation
    stage_priority: AIRecommendation
    feature_snapshots: List[FeatureSnapshot] = field(default_factory=list)
    candidate_portfolio: List[Dict[str, Any]] = field(default_factory=list)

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
            "candidate_portfolio": list(self.candidate_portfolio),
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
