# -*- coding: utf-8 -*-
"""Factory helpers for building meta scheduler stacks."""

from typing import Any, Dict

from src.agents.default_meta_scheduler import DefaultMetaScheduler
from src.schedulers.packers_c import FIFOPacker, GreedyScorePacker, RandomPacker
from src.schedulers.schedulers_a import AdaptiveScheduler, FIFOScheduler, RLBasedScheduler as ASchedulerRL
from src.schedulers.schedulers_b import FIFOBaseline, RLBasedScheduler as BSchedulerRL, RuleBasedScheduler
from src.tuners.tuners_a import AdaptiveTuner, FIFOTuner as AFIFOTuner, RLBasedTuner as ARLTuner
from src.tuners.tuners_b import FIFOTuner as BFIFOTuner, RLBasedTuner as BRLTuner, RuleBasedTuner


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


def build_meta_scheduler(config: Dict[str, Any]) -> DefaultMetaScheduler:
    """Build the default meta scheduler from config."""
    return DefaultMetaScheduler(
        scheduler_a=_build_assignment_scheduler_a(config),
        scheduler_b=_build_assignment_scheduler_b(config),
        tuner_a=_build_tuner_a(config),
        tuner_b=_build_tuner_b(config),
        packer_c=_build_packer_c(config),
    )
