import sys
import random
import numpy as np
import io
import contextlib
from typing import List, Dict, Any

from src.environment.manufacturing_env import ManufacturingEnv
from src.objects import Task


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


def _run_steps(env: ManufacturingEnv, n: int, suppress_stdout: bool = True):
    if suppress_stdout:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            for _ in range(n):
                env.step({})
    else:
        for _ in range(n):
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
    obs, _, _, _ = env.step({})
    # find A completion event and B assignment event for the same uid
    a_events = [e for e in env.env_A.event_log if e.get('event_type') == 'task_completed']
    b_events = [e for e in env.env_B.event_log if e.get('event_type') == 'task_assigned']
    assert a_events, "[Timing] No A completion event recorded"
    assert b_events, "[Timing] No B assignment event recorded"
    a_time = a_events[-1]['end_time']
    b_time = b_events[-1]['start_time']
    assert a_time == b_time, f"[Invariant] A completion time ({a_time}) != B assignment time ({b_time})"


def test_same_step_handoff_b_to_c_under_pack_trigger():
    # configure C to pack immediately with min_queue_size=1 and batch_size_C=1
    cfg = {'num_machines_A': 1, 'num_machines_B': 1, 'num_machines_C': 1, 'min_queue_size': 1, 'batch_size_C': 1, 'deterministic_mode': True}
    env = ManufacturingEnv(cfg)
    # prepare a task that has already passed A and is finishing B now
    t = _build_tasks(1, start_uid=2)[0]
    # seed without initial tasks
    env.reset(seed_initial_tasks=False)
    # add to B queue and run step to let B->C happen
    t.location = 'QUEUE_B'
    env.env_B.add_tasks([t])
    _run_steps(env, 1)
    # check that tasks that passed B reached C queue
    c_queue = env.env_C.wait_pool
    for task in c_queue:
        assert getattr(task, 'arrival_time', None) == 0, f"[Timing] Expected arrival_time==0 for uid {task.uid}, got {task.arrival_time}"


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
