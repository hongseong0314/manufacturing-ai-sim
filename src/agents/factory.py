# -*- coding: utf-8 -*-
"""Factory helpers for building scheduler and MES policy stacks."""

from dataclasses import dataclass
from typing import Any, Dict

from src.agents.default_meta_scheduler import DefaultMetaScheduler
from src.agents.mes_policies import (
    CandidatePortfolioL3MetaSchedulerPolicy,
    RuleBasedL4ObjectivePolicy,
)
from src.schedulers.packers_c import FIFOPacker, GreedyScorePacker, RandomPacker
from src.schedulers.schedulers_a import (
    AdaptiveScheduler,
    FIFOScheduler,
    RLBasedScheduler as ASchedulerRL,
)
from src.schedulers.schedulers_b import (
    FIFOBaseline,
    RLBasedScheduler as BSchedulerRL,
    RuleBasedScheduler,
)
from src.tuners.tuners_a import (
    AdaptiveTuner,
    FIFOTuner as AFIFOTuner,
    RLBasedTuner as ARLTuner,
    RuleBasedTuner as ARuleBasedTuner,
)
from src.tuners.tuners_b import (
    FIFOTuner as BFIFOTuner,
    RLBasedTuner as BRLTuner,
    RuleBasedTuner,
)


@dataclass(frozen=True)
class MESPolicyStack:
    """Factory-built policies used by the MES layered harness path."""

    scheduler_a: Any
    scheduler_b: Any
    tuner_a: Any
    tuner_b: Any
    packer_c: Any
    l3_meta_scheduler: Any
    l4_objective_policy: Any
    config: Dict[str, Any]
    l1_policy_id: str = "L1_FIFO_BASELINE"
    l2_policy_id: str = "L2_RULE_BASED_APC"
    l3_policy_id: str = "L3_CANDIDATE_PORTFOLIO_RULE"
    l4_policy_id: str = "L4_CYCLE_WEIGHT_RULE"
    factory_name: str = "build_mes_policy_stack"


def _build_assignment_scheduler_a(config: Dict[str, Any]):
    """Build process-A assignment scheduler from config."""
    scheduler_type = config.get("scheduler_A", "fifo")
    if scheduler_type == "fifo":
        return FIFOScheduler(config)
    if scheduler_type == "adaptive":
        return AdaptiveScheduler(config)
    if scheduler_type == "rl":
        return ASchedulerRL(config)
    return FIFOScheduler(config)


def _build_assignment_scheduler_b(config: Dict[str, Any]):
    """Build process-B assignment scheduler from config."""
    scheduler_type = config.get("scheduler_B", "rule-based")
    if scheduler_type == "fifo":
        return FIFOBaseline(config)
    if scheduler_type == "rule-based":
        return RuleBasedScheduler(config)
    if scheduler_type == "rl":
        return BSchedulerRL(config)
    return RuleBasedScheduler(config)


def _build_tuner_a(config: Dict[str, Any]):
    """Build process-A recipe tuner from config."""
    tuner_type = config.get("tuner_A", config.get("scheduler_A", "fifo"))
    if tuner_type == "fifo":
        return AFIFOTuner(config)
    if tuner_type == "rule-based":
        return ARuleBasedTuner(config)
    if tuner_type == "adaptive":
        return AdaptiveTuner(config)
    if tuner_type == "rl":
        return ARLTuner(config)
    return AFIFOTuner(config)


def _build_tuner_b(config: Dict[str, Any]):
    """Build process-B recipe tuner from config."""
    tuner_type = config.get("tuner_B", config.get("scheduler_B", "rule-based"))
    if tuner_type == "fifo":
        return BFIFOTuner(config)
    if tuner_type == "rule-based":
        return RuleBasedTuner(config)
    if tuner_type == "rl":
        return BRLTuner(config)
    return RuleBasedTuner(config)


def _build_packer_c(config: Dict[str, Any]):
    """Build process-C packing policy from config."""
    packing_strategy = config.get("packing_C", "greedy")
    if packing_strategy == "fifo":
        return FIFOPacker(config)
    if packing_strategy == "random":
        return RandomPacker(config)
    if packing_strategy == "greedy":
        return GreedyScorePacker(config)
    return GreedyScorePacker(config)


def _build_l3_meta_scheduler(config: Dict[str, Any]):
    """Build MES-native L3 meta scheduling policy from config."""
    scheduler_type = str(config.get("meta_scheduler_L3", "candidate-portfolio-rule"))
    if scheduler_type in {"candidate-portfolio-rule", "rule-based", "default"}:
        return CandidatePortfolioL3MetaSchedulerPolicy(config)
    return CandidatePortfolioL3MetaSchedulerPolicy(config)


def _build_l4_objective_policy(config: Dict[str, Any]):
    """Build MES-native L4 objective policy from config."""
    policy_type = str(config.get("objective_policy_L4", "cycle-weight-rule"))
    if policy_type in {"cycle-weight-rule", "rule-based", "default"}:
        return RuleBasedL4ObjectivePolicy(config)
    return RuleBasedL4ObjectivePolicy(config)


def build_meta_scheduler(config: Dict[str, Any]) -> DefaultMetaScheduler:
    """Build the default meta scheduler from config."""
    return DefaultMetaScheduler(
        scheduler_a=_build_assignment_scheduler_a(config),
        scheduler_b=_build_assignment_scheduler_b(config),
        tuner_a=_build_tuner_a(config),
        tuner_b=_build_tuner_b(config),
        packer_c=_build_packer_c(config),
    )


def build_mes_policy_stack(config: Dict[str, Any] | None = None) -> MESPolicyStack:
    """Build swappable L1/L2 policies for the MES development harness.

    Current production-like default is deliberately simple: L1 uses FIFO-style
    schedulers/packer, L2 uses rule-based APC tuners, L3 uses annotated
    candidate-portfolio scoring, and L4 uses cycle-gated objective weights.
    Later AI/RL policies should fit behind this same bundle shape.
    """
    resolved = dict(config or {})
    resolved.setdefault("scheduler_A", "fifo")
    resolved.setdefault("scheduler_B", "fifo")
    resolved.setdefault("packing_C", "fifo")
    resolved.setdefault("mes_l1_C", resolved["packing_C"])
    resolved.setdefault("tuner_A", "rule-based")
    resolved.setdefault("tuner_B", "rule-based")
    resolved.setdefault("meta_scheduler_L3", "candidate-portfolio-rule")
    resolved.setdefault("objective_policy_L4", "cycle-weight-rule")
    l3_policy = _build_l3_meta_scheduler(resolved)
    l4_policy = _build_l4_objective_policy(resolved)
    return MESPolicyStack(
        scheduler_a=_build_assignment_scheduler_a(resolved),
        scheduler_b=_build_assignment_scheduler_b(resolved),
        tuner_a=_build_tuner_a(resolved),
        tuner_b=_build_tuner_b(resolved),
        packer_c=_build_packer_c(resolved),
        l3_meta_scheduler=l3_policy,
        l4_objective_policy=l4_policy,
        config=resolved,
        l3_policy_id=getattr(l3_policy, "policy_id", "L3_CANDIDATE_PORTFOLIO_RULE"),
        l4_policy_id=getattr(l4_policy, "policy_id", "L4_CYCLE_WEIGHT_RULE"),
    )
