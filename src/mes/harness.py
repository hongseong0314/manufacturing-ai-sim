# -*- coding: utf-8 -*-
"""Facade for the planner -> generator -> evaluator MES harness."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.mes.harnessing.artifacts import (
    GeneratedCycle,
    GeneratedDecision,
    HarnessEvaluationReport,
    HarnessPlan,
    HarnessRunResult,
)
from src.mes.harnessing.evaluator import MESEvaluatorAgent
from src.mes.harnessing.generator import MESGeneratorAgent
from src.mes.harnessing.planner import MESPlannerAgent
from src.mes.services import MESDecisionService
from src.mes.store import InMemoryMESStore


class MESDevelopmentHarness:
    """Run planner -> generator -> evaluator over one MES decision cycle."""

    def __init__(
        self,
        service: Optional[MESDecisionService] = None,
        planner: Optional[MESPlannerAgent] = None,
        generator: Optional[MESGeneratorAgent] = None,
        evaluator: Optional[MESEvaluatorAgent] = None,
        store: Optional[InMemoryMESStore] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.service = service or MESDecisionService(config=config)
        self.planner = planner or MESPlannerAgent(self.service)
        self.generator = generator or MESGeneratorAgent(self.service)
        self.evaluator = evaluator or MESEvaluatorAgent()
        self.store = store or InMemoryMESStore()

    def run(
        self,
        decision_state: Dict[str, Any],
        target_stage: Optional[str] = None,
        correlation_id: Optional[str] = None,
        candidate_portfolio: Optional[List[Dict[str, Any]]] = None,
    ) -> HarnessRunResult:
        plan = self.planner.plan(
            decision_state,
            target_stage=target_stage,
            correlation_id=correlation_id,
            candidate_portfolio=candidate_portfolio,
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


__all__ = [
    "GeneratedCycle",
    "GeneratedDecision",
    "HarnessEvaluationReport",
    "HarnessPlan",
    "HarnessRunResult",
    "MESDevelopmentHarness",
    "MESEvaluatorAgent",
    "MESGeneratorAgent",
    "MESPlannerAgent",
]
