"""Simulation control helpers for run-cycle, run-until, autoplay, and lot generation."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from src.mes.runtime.common import EMPTY_ACTIONS, STAGES, normalize_target_stage, stage_process_time


def generate_tasks(context: Any, time_point: Optional[int] = None) -> Dict[str, Any]:
    current_time = int(context.env.time if time_point is None else time_point)
    tasks = context.env.data_generator.generate_new_jobs(current_time)
    context.env.env_A.add_tasks(tasks)
    context.last_generation_time = current_time
    return {
        "time_point": current_time,
        "inserted_count": len(tasks),
        "task_uids": [task.uid for task in tasks],
        "queue_a_size": len(context.env.env_A.wait_pool),
    }


def maybe_generate_periodic_tasks(context: Any) -> Optional[Dict[str, Any]]:
    interval = int(context.autoplay_generate_every or 0)
    now = int(context.env.time)
    if interval <= 0 or now <= 0:
        return None
    if now % interval != 0 or context.last_generation_time == now:
        return None
    return generate_tasks(context, now)


def ready_stages(context: Any, target_stage: str) -> List[str]:
    if target_stage in STAGES:
        return [target_stage]
    state = context.env.get_decision_state()
    return [
        stage
        for stage in ("C", "B", "A")
        if context.harness.service.dispatch_candidates(state, stage=stage)
    ]


def _merge_actions(
    base: Dict[str, Dict[str, Any]],
    patch: Dict[str, Dict[str, Any]],
) -> None:
    for stage in STAGES:
        base.setdefault(stage, {})
        base[stage].update(patch.get(stage, {}))


def _reserve_assignment_in_state(
    context: Any,
    decision_state: Dict[str, Any],
    command: Dict[str, Any],
) -> Dict[str, Any]:
    """Hide one selected command from a working snapshot during AUTO planning."""
    stage = str(command.get("stage", "")).upper()
    equipment_id = str(command.get("equipment_id", ""))
    if stage not in STAGES or not equipment_id:
        return decision_state

    try:
        task_uids = [int(uid) for uid in command.get("task_uids", [])]
    except (TypeError, ValueError):
        task_uids = []
    if not task_uids:
        return decision_state

    cloned = copy.deepcopy(decision_state)
    stage_state = dict(cloned.get(stage, {}))
    selected_uids = set(task_uids)

    for key in (
        "wait_pool_uids",
        "rework_pool_uids",
        "incoming_from_A_uids",
        "incoming_from_B_uids",
    ):
        values = stage_state.get(key)
        if not isinstance(values, list):
            continue
        stage_state[key] = [uid for uid in values if int(uid) not in selected_uids]

    machines = dict(stage_state.get("machines", {}))
    machine_key = equipment_id
    if machine_key not in machines:
        suffix = equipment_id.split("_")[-1]
        for candidate_key in machines:
            if str(candidate_key).split("_")[-1] == suffix:
                machine_key = candidate_key
                break

    machine_state = machines.get(machine_key)
    if isinstance(machine_state, dict):
        reserved_machine = dict(machine_state)
        current_time = int(cloned.get("time", 0) or 0)
        reserved_machine["status"] = "busy"
        reserved_machine["finish_time"] = current_time + stage_process_time(context, stage)
        reserved_machine["current_batch_uids"] = task_uids
        machines[machine_key] = reserved_machine

    stage_state["machines"] = machines
    cloned[stage] = stage_state
    return cloned


def _record_step_for_results(
    context: Any,
    results: List[Any],
    step_result: Dict[str, Any],
) -> None:
    post_state = context.env.get_decision_state()
    for result in results:
        result.step_result = step_result
        if result.command is not None:
            context.harness.store.record_command_executed(
                result.command.command_id,
                step_result=step_result,
                post_decision_state=post_state,
            )


def _record_budget_plan_snapshots(context: Any, budget_plan: Any) -> None:
    for snapshot in getattr(budget_plan, "feature_snapshots", []):
        context.harness.store.add_feature_snapshot(snapshot)


def run_auto_cycle(context: Any) -> Dict[str, Any]:
    generated_tasks = maybe_generate_periodic_tasks(context)
    state = context.env.get_decision_state()
    budget_plan = context.harness.planner.plan(state)
    budget_action = dict(budget_plan.stage_priority.recommended_action or {})
    candidate_by_id = {
        candidate.get("candidate_id"): candidate
        for candidate in budget_plan.candidate_portfolio
        if candidate.get("candidate_id")
    }
    selected_candidate_ids = [
        candidate_id
        for candidate_id in budget_action.get("selected_candidate_ids", [])
        if candidate_id in candidate_by_id
    ]
    stages = [
        stage
        for stage, budget in budget_action.get("dispatch_budgets", {}).items()
        if int(budget or 0) > 0
    ]
    results = []
    working_state = copy.deepcopy(state)
    combined_actions = {"A": {}, "B": {}, "C": {}}

    for candidate_id in selected_candidate_ids:
        candidate = candidate_by_id[candidate_id]
        stage = str(candidate.get("stage", "")).upper()
        if stage not in STAGES:
            continue
        result = context.harness.run(
            working_state,
            target_stage=stage,
            candidate_portfolio=[candidate],
        )
        results.append(result)
        if not result.passed or result.command is None:
            break
        _merge_actions(combined_actions, result.simulator_actions)
        working_state = _reserve_assignment_in_state(
            context,
            working_state,
            result.generated.validation.validated_command,
        )

    if any(combined_actions[stage] for stage in STAGES):
        observation, reward, done, info = context.env.step(combined_actions)
        step_result = {
            "observation": observation,
            "reward": reward,
            "done": done,
            "info": info,
        }
        _record_step_for_results(context, results, step_result)
        stop_reason = "executed"
    else:
        observation, reward, done, info = context.env.step(EMPTY_ACTIONS)
        step_result = {
            "observation": observation,
            "reward": reward,
            "done": done,
            "info": info,
        }
        stop_reason = "no_candidates"

    if results:
        context.last_correlation_id = results[-1].generated.plan.correlation_id
    _record_budget_plan_snapshots(context, budget_plan)

    payload = {
        "mode": "AUTO",
        "target_stages": stages,
        "selection_source": "l3_budget_plan",
        "budget_plan": budget_action,
        "budget_correlation_id": budget_plan.correlation_id,
        "count": len(results),
        "stop_reason": stop_reason,
        "generated_tasks": generated_tasks,
        "combined_actions": combined_actions,
        "step_result": step_result,
        "cycles": [result.to_dict() for result in results],
        "time": context.env.time,
    }
    context.last_cycle = payload
    return payload


def run_single_cycle(
    context: Any,
    target_stage: str,
    execute: bool,
    advance_on_reject: bool = False,
) -> Dict[str, Any]:
    if execute:
        result = context.harness.run_and_step(context.env, target_stage=target_stage)
        if not result.passed and advance_on_reject:
            observation, reward, done, info = context.env.step(EMPTY_ACTIONS)
            result.step_result = {
                "observation": observation,
                "reward": reward,
                "done": done,
                "info": info,
            }
    else:
        result = context.harness.run(
            context.env.get_decision_state(),
            target_stage=target_stage,
        )
    context.last_correlation_id = result.generated.plan.correlation_id
    payload = result.to_dict()
    context.last_cycle = payload
    return payload


def tick_once(context: Any, target_stage: str) -> Dict[str, Any]:
    target_stage = normalize_target_stage(target_stage)
    if target_stage == "AUTO":
        return run_auto_cycle(context)
    maybe_generate_periodic_tasks(context)
    return run_single_cycle(context, target_stage, execute=True, advance_on_reject=True)


def run_until(context: Any, target_stage: str, max_cycles: int) -> Dict[str, Any]:
    target = normalize_target_stage(target_stage, default="AUTO")
    cycles: List[Dict[str, Any]] = []
    stop_reason = "max_cycles"
    for _ in range(max(1, min(500, int(max_cycles)))):
        cycle = run_auto_cycle(context) if target == "AUTO" else run_single_cycle(
            context,
            target,
            execute=True,
        )
        cycles.append(cycle)
        if cycle.get("stop_reason") == "no_candidates":
            stop_reason = "no_candidates"
            break
        validation = cycle.get("generated", {}).get("validation", {})
        if validation.get("validation_status") == "REJECTED":
            stop_reason = "rejected"
            break
    return {"count": len(cycles), "stop_reason": stop_reason, "cycles": cycles}
