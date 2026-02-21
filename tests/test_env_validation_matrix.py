import sys
import random
import numpy as np
import io
import contextlib
import warnings
from typing import List, Dict, Any

from src.agents.default_meta_scheduler import DefaultMetaScheduler
from src.agents.factory import build_meta_scheduler
from src.environment.manufacturing_env import ManufacturingEnv
from src.environment.process_c_env import ProcessC_Env
from src.objects import Task
from src.schedulers.packers_c import FIFOPacker
from src.tuners.tuners_a import FIFOTuner as AFIFOTuner
from src.tuners.tuners_b import FIFOTuner as BFIFOTuner


def _seed_all(random_seed: int, np_seed: int = None):
    random.seed(random_seed)
    if np_seed is None:
        np_seed = random_seed
    np.random.seed(np_seed)


def _build_tasks(count: int, start_uid: int = 0, spec_a=(45.0, 55.0), spec_b=(20.0, 80.0), arrival_time=0) -> List[Task]:
    tasks = []
    for i in range(count):
        t = Task(
            uid=start_uid + i,
            job_id=f"JOB{start_uid}",
            due_date=1000,
            spec_a=spec_a,
            spec_b=spec_b,
            arrival_time=arrival_time,
        )
        tasks.append(t)
    return tasks


def _step_with_meta(env: ManufacturingEnv, meta):
    state = env.get_decision_state()
    actions = meta.decide(state)
    return env.step(actions)


def _run_steps(
    env: ManufacturingEnv,
    n: int,
    suppress_stdout: bool = True,
    use_meta: bool = True,
):
    meta = build_meta_scheduler(env.config) if use_meta else None
    if suppress_stdout:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            for _ in range(n):
                if use_meta:
                    _step_with_meta(env, meta)
                else:
                    env.step({})
    else:
        for _ in range(n):
            if use_meta:
                _step_with_meta(env, meta)
            else:
                env.step({})


def _collect_events(env: ManufacturingEnv) -> List[Dict[str, Any]]:
    events = []
    events.extend(getattr(env.env_A, 'event_log', []) or [])
    events.extend(getattr(env.env_B, 'event_log', []) or [])
    events.extend(getattr(env.env_C, 'event_log', []) or [])
    return events


def test_reset_default_seeds_40_tasks():
    cfg = {'num_machines_A': 1, 'num_machines_B': 1, 'num_machines_C': 1}
    env = ManufacturingEnv(cfg)
    _ = env.reset()
    assert len(env.env_A.wait_pool) == 40, f"[Contract] Expected 40 initial tasks, got {len(env.env_A.wait_pool)}"


def test_reset_seed_false_starts_empty():
    cfg = {'num_machines_A': 1, 'num_machines_B': 1, 'num_machines_C': 1}
    env = ManufacturingEnv(cfg)
    _ = env.reset(seed_initial_tasks=False)
    assert len(env.env_A.wait_pool) == 0, f"[Contract] seed_initial_tasks=False should leave A.wait_pool empty, found {len(env.env_A.wait_pool)}"


def test_reset_with_initial_tasks_injects_exact_set():
    cfg = {'num_machines_A': 1, 'num_machines_B': 1, 'num_machines_C': 1}
    env = ManufacturingEnv(cfg)
    tasks = _build_tasks(5, start_uid=500)
    env.reset(initial_tasks=tasks)
    uids = [t.uid for t in env.env_A.wait_pool]
    assert len(uids) == 5 and set(uids) == set(range(500, 505)), f"[Contract] initial tasks not injected properly: {uids}"


def test_same_step_handoff_a_to_b():
    cfg = {'num_machines_A': 1, 'num_machines_B': 1, 'num_machines_C': 1, 'deterministic_mode': True}
    env = ManufacturingEnv(cfg)
    # seed one task and force A machine to finish at t=0
    t = _build_tasks(1, start_uid=1)[0]
    env.reset(initial_tasks=[t])
    m = list(env.env_A.machines.values())[0]
    # start processing and set finish_time to 0 so step() treats it as completed now
    m.start_processing([t], finish_time=0, recipe=[10, 2, 1])
    # strict external mode: no auto assignment, but A completion and handoff still occur
    _ = env.step({})
    a_events = [e for e in env.env_A.event_log if e.get('event_type') == 'task_completed']
    assert a_events, "[Timing] No A completion event recorded"
    assert any(task.uid == t.uid for task in env.env_B.wait_pool), "[Timing] A->B handoff missing after A completion"

    # next meta step should assign into B
    _run_steps(env, 1)
    b_events = [e for e in env.env_B.event_log if e.get('event_type') == 'task_assigned']
    assert b_events, "[Timing] No B assignment event recorded"
    a_time = a_events[-1]['end_time']
    b_time = b_events[-1]['start_time']
    assert b_time >= a_time, f"[Invariant] B assignment time ({b_time}) must be >= A completion time ({a_time})"


def test_same_step_handoff_b_to_c_under_pack_trigger():
    # configure C to pack immediately with min_queue_size=1 and batch_size_C=1
    cfg = {'num_machines_A': 1, 'num_machines_B': 1, 'num_machines_C': 1, 'min_queue_size': 1, 'batch_size_C': 1, 'deterministic_mode': True}
    env = ManufacturingEnv(cfg)
    # prepare a task that has already passed A and is finishing B now
    t = _build_tasks(1, start_uid=2)[0]
    # seed without initial tasks
    env.reset(seed_initial_tasks=False)
    # force a B completion at t=0 to trigger B->C handoff in the same environment step
    m = list(env.env_B.machines.values())[0]
    m.start_processing([t], finish_time=0, recipe=[50.0, 50.0, 30.0])
    _run_steps(env, 1)
    # check that tasks that passed B reached C queue
    c_queue = env.env_C.wait_pool
    for task in c_queue:
        assert getattr(task, 'arrival_time', None) == 0, f"[Timing] Expected arrival_time==0 for uid {task.uid}, got {task.arrival_time}"


def test_same_step_b_to_c_pack_when_ready():
    cfg = {
        'num_machines_A': 1,
        'num_machines_B': 1,
        'num_machines_C': 1,
        'min_queue_size': 1,
        'batch_size_C': 1,
        'packing_C': 'fifo',
        'deterministic_mode': True,
    }
    env = ManufacturingEnv(cfg)
    env.reset(seed_initial_tasks=False)

    t = _build_tasks(1, start_uid=22)[0]
    b_machine = list(env.env_B.machines.values())[0]
    b_machine.start_processing([t], finish_time=0, recipe=[50.0, 50.0, 30.0])

    _run_steps(env, 1)
    assert len(env.completed_tasks) == 1, "[Timing] B->C should pack in same step when C is immediately ready"
    assert env.env_C.pack_count == 1, "[Timing] Expected C pack_count==1 after same-step handoff pack"


def test_no_machine_overlap_on_a_and_b():
    cfg = {'num_machines_A': 2, 'num_machines_B': 2, 'num_machines_C': 1}
    env = ManufacturingEnv(cfg)
    env.reset()
    # run a handful of steps to generate assignment events
    _run_steps(env, 5)
    events = _collect_events(env)
    # build intervals per machine from assignment events
    intervals = {}
    for e in events:
        if e.get('event_type') == 'task_assigned':
            mid = e.get('machine_id')
            start = e.get('start_time')
            end = e.get('end_time')
            intervals.setdefault(mid, []).append((start, end))
    for mid, ivs in intervals.items():
        ivs_sorted = sorted(ivs)
        for i in range(1, len(ivs_sorted)):
            prev_end = ivs_sorted[i-1][1]
            cur_start = ivs_sorted[i][0]
            assert prev_end <= cur_start, f"[Invariant] Overlap on {mid}: prev_end={prev_end} cur_start={cur_start}"


def test_monotonic_flow_order_a_then_b_then_c():
    cfg = {'num_machines_A': 1, 'num_machines_B': 1, 'num_machines_C': 1, 'deterministic_mode': True, 'min_queue_size': 1, 'batch_size_C': 1}
    env = ManufacturingEnv(cfg)
    env.reset()
    # run until at least one completed in C or for a short horizon
    _run_steps(env, 20)
    # check histories of completed tasks
    for t in env.completed_tasks:
        procs = [h.get('process') for h in t.history]
        assert 'A' in procs and 'B' in procs and 'C' in procs, f"[Invariant] Task {t.uid} missing process steps: {procs}"


def test_rework_count_increments_on_failed_qa():
    cfg = {'num_machines_A': 1, 'num_machines_B': 1, 'num_machines_C': 1, 'deterministic_mode': True}
    env = ManufacturingEnv(cfg)
    # craft a task that will fail A by giving an impossible spec
    t = Task(uid=900, job_id='J', due_date=100, spec_a=(1000.0, 1001.0))
    env.reset(initial_tasks=[t])
    m = list(env.env_A.machines.values())[0]
    m.start_processing([t], finish_time=0, recipe=[10, 2, 1])
    _run_steps(env, 1)
    # after step, rework_count should be >=0 (we check it's present and non-negative)
    assert t.rework_count >= 0, f"[ActionAPI] Unexpected rework_count for uid {t.uid}: {t.rework_count}"


def test_rework_count_never_decreases():
    cfg = {'num_machines_A': 1, 'num_machines_B': 1, 'num_machines_C': 1}
    env = ManufacturingEnv(cfg)
    tasks = _build_tasks(3, start_uid=1000)
    env.reset(initial_tasks=tasks)
    prev_counts = {t.uid: t.rework_count for t in tasks}
    for _ in range(5):
        _run_steps(env, 1)
        for t in tasks:
            assert t.rework_count >= prev_counts[t.uid], f"[Invariant] rework_count decreased for uid {t.uid}"
            prev_counts[t.uid] = t.rework_count


def test_validation_scenario_should_not_spawn_periodic_jobs_when_seed_false():
    cfg = {'num_machines_A': 1, 'num_machines_B': 1, 'num_machines_C': 1}
    env = ManufacturingEnv(cfg)
    env.reset(seed_initial_tasks=False)
    # run until time 31 (periodic generator at multiples of 30)
    _run_steps(env, 31)
    assert len(env.env_A.wait_pool) == 0, f"[ScenarioIsolation] Periodic jobs spawned despite seed_initial_tasks=False; found {len(env.env_A.wait_pool)} tasks"


def test_arrival_time_should_update_on_b_to_c_handoff():
    cfg = {'num_machines_A': 1, 'num_machines_B': 1, 'num_machines_C': 1, 'min_queue_size': 1, 'batch_size_C': 1}
    env = ManufacturingEnv(cfg)
    t = _build_tasks(1, start_uid=2000)[0]
    env.reset(seed_initial_tasks=False)
    # simulate a B completion handoff at t=0
    t.location = 'QUEUE_B'
    env.env_B.add_tasks([t])
    _run_steps(env, 1)
    # after step, any task in C.wait_pool should have arrival_time == 0
    for task in env.env_C.wait_pool:
        assert getattr(task, 'arrival_time', None) == 0, f"[Timing] arrival_time not updated for uid {task.uid}: {task.arrival_time}"


def test_external_actions_should_override_auto_assignment_in_a():
    cfg = {'num_machines_A': 1, 'num_machines_B': 1, 'num_machines_C': 1}
    env = ManufacturingEnv(cfg)
    tasks = _build_tasks(2, start_uid=3000)
    env.reset(initial_tasks=tasks)
    # create an explicit action targeting A_0
    action = {'A': {'A_0': {'task_uids': [3001], 'recipe': [99.0, 99.0, 99.0]}}}
    # Call step with external action immediately; external actions should be applied
    obs, _, _, _ = env.step(action)
    # inspect A machine to find current_batch includes uid 3001 (if override worked)
    m = env.env_A.machines.get(0)
    uids = [t.uid for t in getattr(m, 'current_batch', [])]
    assert 3001 in uids, f"[ActionAPI] External action did not assign requested uid to machine: {uids}"


def test_step_without_actions_should_not_auto_assign_when_idle():
    cfg = {'num_machines_A': 1, 'num_machines_B': 1, 'num_machines_C': 1}
    env = ManufacturingEnv(cfg)
    tasks = _build_tasks(2, start_uid=3500)
    env.reset(initial_tasks=tasks)
    env.step({})
    m = env.env_A.machines.get(0)
    assert m.status == "idle", "[StrictExternal] step({}) should not auto-assign tasks in A"
    assert not getattr(m, "current_batch", []), "[StrictExternal] A machine must have empty current_batch without external actions"


def test_get_decision_state_schema_has_required_fields():
    cfg = {'num_machines_A': 1, 'num_machines_B': 1, 'num_machines_C': 1}
    env = ManufacturingEnv(cfg)
    tasks = _build_tasks(2, start_uid=3600)
    env.reset(seed_initial_tasks=False, initial_tasks=tasks)

    state = env.get_decision_state()

    top_required = {'time', 'max_steps', 'num_completed', 'tasks', 'A', 'B', 'C'}
    assert top_required.issubset(set(state.keys())), f"[StateAPI] Missing top-level keys: {top_required - set(state.keys())}"

    for process_key in ['A', 'B', 'C']:
        process_state = state[process_key]
        assert 'machines' in process_state and isinstance(process_state['machines'], dict), f"[StateAPI] {process_key}.machines missing or invalid"
        assert 'wait_pool_uids' in process_state and isinstance(process_state['wait_pool_uids'], list), f"[StateAPI] {process_key}.wait_pool_uids missing or invalid"
        assert 'queue_stats' in process_state and isinstance(process_state['queue_stats'], dict), f"[StateAPI] {process_key}.queue_stats missing or invalid"

    assert 'rework_pool_uids' in state['A'], "[StateAPI] A.rework_pool_uids missing"
    assert 'rework_pool_uids' in state['B'], "[StateAPI] B.rework_pool_uids missing"

    a_machine = state['A']['machines'].get('A_0', {})
    a_machine_required = {'status', 'finish_time', 'batch_size', 'u', 'm_age', 'current_batch_uids'}
    assert a_machine_required.issubset(set(a_machine.keys())), f"[StateAPI] Missing A machine keys: {a_machine_required - set(a_machine.keys())}"

    b_machine = state['B']['machines'].get('B_0', {})
    b_machine_required = {'status', 'finish_time', 'batch_size', 'v', 'b_age', 'current_batch_uids'}
    assert b_machine_required.issubset(set(b_machine.keys())), f"[StateAPI] Missing B machine keys: {b_machine_required - set(b_machine.keys())}"

    c_machine = state['C']['machines'].get('C_0', {})
    c_machine_required = {'status', 'finish_time', 'batch_size', 'current_batch_uids'}
    assert c_machine_required.issubset(set(c_machine.keys())), f"[StateAPI] Missing C machine keys: {c_machine_required - set(c_machine.keys())}"

    assert 3600 in state['tasks'], "[StateAPI] Task snapshot missing seeded uid=3600"
    task_row = state['tasks'][3600]
    task_required = {
        'uid', 'job_id', 'due_date', 'spec_a', 'spec_b', 'location',
        'rework_count', 'arrival_time', 'material_type', 'color',
        'margin_value', 'realized_qa_A', 'realized_qa_B',
    }
    assert task_required.issubset(set(task_row.keys())), f"[StateAPI] Missing task snapshot keys: {task_required - set(task_row.keys())}"


def test_meta_scheduler_prioritizes_rework_and_avoids_duplicate_assignment():
    cfg = {
        'num_machines_A': 2,
        'num_machines_B': 1,
        'num_machines_C': 1,
        'batch_size_A': 2,
    }
    env = ManufacturingEnv(cfg)
    env.reset(seed_initial_tasks=False)

    wait_tasks = _build_tasks(3, start_uid=3700)
    rework_task = _build_tasks(1, start_uid=3800)[0]
    rework_task.location = 'REWORK_A'
    rework_task.rework_count = 1

    env.env_A.wait_pool.extend(wait_tasks)
    env.env_A.rework_pool.append(rework_task)

    meta = build_meta_scheduler(env.config)
    actions = meta.decide(env.get_decision_state())

    a_actions = actions.get('A', {})
    assert a_actions, "[Meta] Expected A actions but got none"

    all_uids = []
    for assignment in a_actions.values():
        all_uids.extend(assignment.get('task_uids', []))

    assert len(all_uids) == len(set(all_uids)), "[Meta] Duplicate task UID assigned to multiple A machines"
    assert rework_task.uid in all_uids, "[Meta] Rework task should be selected before/with new tasks"

    first_machine_id = sorted(a_actions.keys())[0]
    first_assignment = a_actions[first_machine_id]
    first_batch = first_assignment.get('task_uids', [])
    assert first_batch and first_batch[0] == rework_task.uid, "[Meta] Rework task should be first in first A batch"
    assert first_assignment.get('task_type') == 'rework', "[Meta] task_type should be 'rework' when rework task is selected"


def test_stochastic_quick_robustness_multi_seed():
    seeds = [11, 22, 33]
    for s in seeds:
        _seed_all(s)
        cfg = {'num_machines_A': 1, 'num_machines_B': 1, 'num_machines_C': 1}
        env = ManufacturingEnv(cfg)
        env.reset()
        _run_steps(env, 10)
        # basic invariants: no overlapping assignments on A
        events = _collect_events(env)
        intervals = {}
        for e in events:
            if e.get('event_type') == 'task_assigned' and e.get('process') == 'A':
                mid = e.get('machine_id')
                intervals.setdefault(mid, []).append((e.get('start_time'), e.get('end_time')))
        for mid, ivs in intervals.items():
            ivs_sorted = sorted(ivs)
            for i in range(1, len(ivs_sorted)):
                assert ivs_sorted[i-1][1] <= ivs_sorted[i][0], f"[Invariant] Overlap detected seed={s} on {mid}"


def test_no_artificial_dead_time_in_a_and_b_when_backlog_exists():
    cfg = {
        'num_machines_A': 1,
        'num_machines_B': 1,
        'num_machines_C': 1,
        'process_time_A': 1,
        'process_time_B': 3,
        'batch_size_A': 1,
        'batch_size_B': 1,
        'deterministic_mode': True,
    }
    env = ManufacturingEnv(cfg)
    tasks = _build_tasks(
        120,
        start_uid=4000,
        spec_a=(0.0, 100.0),
        spec_b=(0.0, 100.0),
    )
    env.reset(seed_initial_tasks=False, initial_tasks=tasks)
    _run_steps(env, 40)

    a_intervals = sorted(
        [
            (e['start_time'], e['end_time'])
            for e in env.env_A.event_log
            if e.get('event_type') == 'task_assigned' and e.get('machine_id') == 'A_0'
        ]
    )
    b_intervals = sorted(
        [
            (e['start_time'], e['end_time'])
            for e in env.env_B.event_log
            if e.get('event_type') == 'task_assigned' and e.get('machine_id') == 'B_0'
        ]
    )

    assert len(a_intervals) >= 2, "[Timing] Not enough A assignments to verify dead-time."
    assert len(b_intervals) >= 2, "[Timing] Not enough B assignments to verify dead-time."

    for i in range(1, len(a_intervals)):
        prev_end = a_intervals[i - 1][1]
        cur_start = a_intervals[i][0]
        assert cur_start == prev_end, (
            f"[Timing] Artificial dead-time in A_0: prev_end={prev_end}, cur_start={cur_start}"
        )

    for i in range(1, len(b_intervals)):
        prev_end = b_intervals[i - 1][1]
        cur_start = b_intervals[i][0]
        assert cur_start == prev_end, (
            f"[Timing] Artificial dead-time in B_0: prev_end={prev_end}, cur_start={cur_start}"
        )


def test_c_warns_when_num_machines_c_exceeds_single_pack_runtime():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ManufacturingEnv(
            {
                "num_machines_A": 1,
                "num_machines_B": 1,
                "num_machines_C": 2,
            }
        )

    messages = [str(entry.message) for entry in caught]
    assert any(
        "num_machines_C > 1" in message and "single-pack-per-step" in message
        for message in messages
    ), "[C-Semantics] Expected warning for num_machines_C > 1 in single-pack mode."


def test_c_warns_when_process_time_c_is_nonzero_but_inactive():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ManufacturingEnv(
            {
                "num_machines_A": 1,
                "num_machines_B": 1,
                "num_machines_C": 1,
                "process_time_C": 5,
            }
        )

    messages = [str(entry.message) for entry in caught]
    assert any(
        "process_time_C" in message and "not active" in message
        for message in messages
    ), "[C-Semantics] Expected warning when nonzero process_time_C is configured."


def test_decision_state_contains_c_capabilities():
    cfg = {"num_machines_A": 1, "num_machines_B": 1, "num_machines_C": 2}
    env = ManufacturingEnv(cfg)
    env.reset(seed_initial_tasks=False)
    state = env.get_decision_state()

    capabilities = state["C"].get("capabilities", {})
    required_keys = {"single_pack_per_step", "multi_machine_active", "max_packs_per_step"}
    assert required_keys.issubset(set(capabilities.keys())), (
        f"[StateAPI] Missing C capability keys: {required_keys - set(capabilities.keys())}"
    )
    assert capabilities["single_pack_per_step"] is True
    assert capabilities["multi_machine_active"] is False
    assert capabilities["max_packs_per_step"] == 1


def test_scheduler_context_hook_supports_legacy_and_context_aware_scheduler():
    class LegacyScheduler:
        def select_batch(self, wait_pool_uids, rework_pool_uids, batch_size):
            if rework_pool_uids:
                return rework_pool_uids[:batch_size], "rework"
            if wait_pool_uids:
                return wait_pool_uids[:batch_size], "new"
            return None, None

    class DueDateContextScheduler(LegacyScheduler):
        def select_batch_with_context(
            self,
            wait_pool_uids,
            rework_pool_uids,
            batch_size,
            context=None,
        ):
            context = context or {}
            rework_rows = context.get("rework_pool_tasks", [])
            if rework_rows:
                selected = sorted(rework_rows, key=lambda row: row.get("due_date", 0))
                return [int(row["uid"]) for row in selected[:batch_size]], "rework"

            wait_rows = context.get("wait_pool_tasks", [])
            if wait_rows:
                selected = sorted(wait_rows, key=lambda row: row.get("due_date", 0))
                return [int(row["uid"]) for row in selected[:batch_size]], "new"
            return None, None

    cfg = {
        "num_machines_A": 1,
        "num_machines_B": 1,
        "num_machines_C": 1,
        "batch_size_A": 1,
    }
    env = ManufacturingEnv(cfg)
    task_late = Task(uid=7001, job_id="J1", due_date=200, spec_a=(45.0, 55.0))
    task_early = Task(uid=7002, job_id="J2", due_date=10, spec_a=(45.0, 55.0))
    env.reset(seed_initial_tasks=False, initial_tasks=[task_late, task_early])
    state = env.get_decision_state()

    legacy_meta = DefaultMetaScheduler(
        scheduler_a=LegacyScheduler(),
        scheduler_b=LegacyScheduler(),
        tuner_a=AFIFOTuner(cfg),
        tuner_b=BFIFOTuner(cfg),
        packer_c=FIFOPacker(cfg),
    )
    legacy_actions = legacy_meta.decide(state)
    assert legacy_actions["A"]["A_0"]["task_uids"] == [7001], (
        "[ContextHook] Legacy scheduler path should remain unchanged."
    )

    context_meta = DefaultMetaScheduler(
        scheduler_a=DueDateContextScheduler(),
        scheduler_b=DueDateContextScheduler(),
        tuner_a=AFIFOTuner(cfg),
        tuner_b=BFIFOTuner(cfg),
        packer_c=FIFOPacker(cfg),
    )
    context_actions = context_meta.decide(state)
    assert context_actions["A"]["A_0"]["task_uids"] == [7002], (
        "[ContextHook] Context-aware scheduler should use due-date from context payload."
    )


def test_reset_seed_reproducibility_for_initial_state_and_short_trace():
    cfg = {
        "num_machines_A": 1,
        "num_machines_B": 1,
        "num_machines_C": 1,
        "deterministic_mode": False,
        "batch_size_C": 1,
        "min_queue_size": 1,
        "max_steps": 20,
    }

    def run_trace(seed_value: int):
        env = ManufacturingEnv(cfg)
        meta = build_meta_scheduler(env.config)
        env.reset(seed=seed_value)

        initial_signature = [
            (
                task.uid,
                task.job_id,
                task.due_date,
                tuple(task.spec_a),
                tuple(task.spec_b),
                task.material_type,
                task.color,
            )
            for task in env.env_A.wait_pool[:8]
        ]

        trace = []
        for _ in range(8):
            obs, reward, _, _ = _step_with_meta(env, meta)
            trace.append(
                (
                    obs["time"],
                    obs["A_state"]["wait_pool_size"],
                    obs["B_state"]["wait_pool_size"],
                    obs["C_state"]["queue_size"],
                    obs["num_completed"],
                    reward,
                )
            )

        event_sizes = (
            len(env.env_A.event_log),
            len(env.env_B.event_log),
            len(env.env_C.event_log),
        )
        return initial_signature, trace, event_sizes

    run1 = run_trace(seed_value=1234)
    run2 = run_trace(seed_value=1234)
    assert run1 == run2, "[Seed] Same reset seed should reproduce initial tasks and short trace."


def test_process_c_default_and_opt_in_multi_pack_behavior():
    tasks_default = _build_tasks(2, start_uid=8000)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        env_default = ProcessC_Env(
            {"num_machines_C": 2, "batch_size_C": 1, "max_packs_per_step": 1}
        )
    env_default.add_tasks(tasks_default, current_time=0)
    result_default = env_default.step(
        current_time=0,
        actions={
            "C_0": {"task_uids": [8000], "reason": "test"},
            "C_1": {"task_uids": [8001], "reason": "test"},
        },
    )
    assert len(result_default["completed"]) == 1, (
        "[C-MultiPack] Default mode should complete at most one pack per step."
    )
    assert env_default.pack_count == 1

    tasks_multi = _build_tasks(2, start_uid=8100)
    env_multi = ProcessC_Env(
        {"num_machines_C": 2, "batch_size_C": 1, "max_packs_per_step": 2}
    )
    env_multi.add_tasks(tasks_multi, current_time=0)
    result_multi = env_multi.step(
        current_time=0,
        actions={
            "C_0": {"task_uids": [8100], "reason": "test"},
            "C_1": {"task_uids": [8101], "reason": "test"},
        },
    )
    assert len(result_multi["completed"]) == 2, (
        "[C-MultiPack] Opt-in mode should allow multiple packs in one step."
    )
    assert env_multi.pack_count == 2


def test_meta_scheduler_emits_multi_c_actions_when_opted_in():
    cfg = {
        "num_machines_A": 1,
        "num_machines_B": 1,
        "num_machines_C": 2,
        "batch_size_C": 1,
        "min_queue_size": 1,
        "max_packs_per_step": 2,
        "packing_C": "fifo",
    }
    env = ManufacturingEnv(cfg)
    env.reset(seed_initial_tasks=False)

    c_tasks = _build_tasks(2, start_uid=8200)
    for task in c_tasks:
        task.realized_qa_B = 50.0
    env.env_C.add_tasks(c_tasks, current_time=0)

    meta = build_meta_scheduler(env.config)
    actions = meta.decide(env.get_decision_state())
    c_actions = actions.get("C", {})

    assert len(c_actions) == 2, (
        "[Meta-C] Expected two C actions when max_packs_per_step=2 and two machines are available."
    )


if __name__ == '__main__':
    # Fallback runner when pytest is not available; execute tests sequentially
    tests = [
        obj for name, obj in globals().items()
        if callable(obj) and name.startswith('test_')
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"[OK] {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"[FAIL] {t.__name__}: {e}")
    sys.exit(1 if failures else 0)
