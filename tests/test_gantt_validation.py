# -*- coding: utf-8 -*-
"""
Gantt Chart based integration validation tests
Batch processing simulation validation (Process A, B, C)
"""

import os
import random
import sys
from pathlib import Path

import numpy as np
from collections import defaultdict

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# Add project root path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.environment.manufacturing_env import ManufacturingEnv
from scripts.generate_gantt_chart_v3 import ValidationReport

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "results"


def _generate_initial_tasks(env: ManufacturingEnv, count: int, current_time: int = 0):
    """
    Generate initial tasks using env's generator and keep UID sequence contiguous
    for only the tasks actually injected into the scenario.
    """
    all_tasks = env.data_generator.generate_new_jobs(current_time=current_time)
    selected = all_tasks[:count]
    dropped = len(all_tasks) - len(selected)
    if dropped > 0:
        env.data_generator.task_uid_counter -= dropped
    return selected


def _set_tight_spec_a(tasks, low: float, high: float):
    """Apply the same tight A-spec to all tasks."""
    low_f = float(low)
    high_f = float(high)
    for task in tasks:
        task.spec_a = (low_f, high_f)


def _machine_order_and_y(env_a, env_b, env_c):
    machines = []
    for _, machine in sorted(env_a.machines.items()):
        machines.append(str(machine.id))
    for _, machine in sorted(env_b.machines.items()):
        machines.append(str(machine.id))
    for _, machine in sorted(env_c.machines.items()):
        machines.append(str(machine.id))
    machines.append("C_QUEUE")
    y_map = {machine_id: i for i, machine_id in enumerate(machines)}
    return machines, y_map


def _build_intervals(env_a, env_b, env_c):
    events = []
    events.extend(env_a.event_log)
    events.extend(env_b.event_log)
    events.extend(env_c.event_log)

    events.sort(key=lambda e: (e.get("timestamp", e.get("start_time", 0)), e.get("event_type", "")))

    # Count A-process assignment occurrences to compute rework index per task.
    assign_count_a = defaultdict(int)
    task_rework_idx_at_time = {}
    for event in events:
        if event.get("event_type") == "task_assigned" and str(event.get("machine_id", "")).startswith("A_"):
            for uid in event.get("task_uids", []):
                assign_count_a[uid] += 1
                task_rework_idx_at_time[(uid, event.get("start_time", 0), event.get("machine_id"))] = max(0, assign_count_a[uid] - 1)

    intervals = []
    for event in events:
        event_type = event.get("event_type")
        if event_type not in {"task_assigned", "pack_completed"}:
            continue

        machine_id = str(event.get("machine_id"))
        task_uids = event.get("task_uids", [])
        start_time = int(event.get("start_time", event.get("timestamp", 0)))
        end_time = int(event.get("end_time", start_time))
        duration = max(1, end_time - start_time)

        for idx, uid in enumerate(task_uids):
            rework_idx = task_rework_idx_at_time.get((uid, start_time, machine_id), 0)
            is_a_rework_assignment = (
                machine_id.startswith("A_")
                and event_type == "task_assigned"
                and event.get("task_type") == "rework"
                and rework_idx > 0
            )
            label = f"{uid}(R{rework_idx})" if is_a_rework_assignment else f"{uid}"
            intervals.append({
                "machine_id": machine_id,
                "start": start_time,
                "duration": duration,
                "task_uid": uid,
                "label": label,
                "event_type": event_type,
                "task_type": event.get("task_type", "new"),
                "stack_index": idx,
                "stack_size": max(1, len(task_uids)),
            })

    # C queue/wait timeline boxes for clearer in-progress visibility.
    c_queue_start = {}
    c_pack_end = {}
    final_time = max(
        [
            int(e.get("end_time", e.get("start_time", e.get("timestamp", 0))))
            for e in events
        ],
        default=0,
    ) + 1

    for event in events:
        event_type = event.get("event_type")
        if event_type == "task_queued":
            start_time = int(event.get("start_time", event.get("timestamp", 0)))
            for uid in event.get("task_uids", []):
                if uid not in c_queue_start:
                    c_queue_start[uid] = start_time
        elif event_type == "pack_completed":
            end_time = int(event.get("end_time", event.get("timestamp", 0)))
            for uid in event.get("task_uids", []):
                c_pack_end[uid] = end_time

    wait_rows = []
    for uid, start_time in c_queue_start.items():
        end_time = c_pack_end.get(uid, final_time)
        if end_time <= start_time:
            end_time = start_time + 1
        wait_rows.append({
            "task_uid": uid,
            "start": start_time,
            "end": end_time,
        })

    wait_rows.sort(key=lambda row: (row["start"], row["end"], row["task_uid"]))
    lane_ends = []
    lane_map = {}
    for row in wait_rows:
        assigned_lane = None
        for lane_idx, lane_end in enumerate(lane_ends):
            if row["start"] >= lane_end:
                assigned_lane = lane_idx
                lane_ends[lane_idx] = row["end"]
                break
        if assigned_lane is None:
            lane_ends.append(row["end"])
            assigned_lane = len(lane_ends) - 1
        lane_map[row["task_uid"]] = assigned_lane

    total_lanes = max(1, len(lane_ends))
    for row in wait_rows:
        intervals.append({
            "machine_id": "C_QUEUE",
            "start": row["start"],
            "duration": row["end"] - row["start"],
            "task_uid": row["task_uid"],
            "label": f"{row['task_uid']}",
            "event_type": "pack_wait",
            "task_type": "in_progress",
            "stack_index": lane_map[row["task_uid"]],
            "stack_size": total_lanes,
        })
    return intervals


def draw_gantt_from_events(env_a, env_b, env_c, output_path: Path, title: str):
    """Draw gantt chart directly from process event logs."""
    if not MATPLOTLIB_AVAILABLE:
        print("[Gantt] matplotlib is not installed. Skipping direct gantt generation.")
        return None

    machines, y_map = _machine_order_and_y(env_a, env_b, env_c)
    intervals = _build_intervals(env_a, env_b, env_c)
    if not intervals:
        print("[Gantt] No intervals found in event logs.")
        return None

    max_time = max(i["start"] + i["duration"] for i in intervals)
    fig, ax = plt.subplots(figsize=(24, 12))

    color_map = {
        "new": "#4C78A8",
        "rework": "#E45756",
        "packed": "#54A24B",
        "task_assigned": "#4C78A8",
        "pack_completed": "#54A24B",
        "pack_wait": "#F28E2B",
    }

    for item in intervals:
        machine_y = y_map.get(item["machine_id"])
        if machine_y is None:
            continue

        stack_size = item["stack_size"]
        slot_height = 0.85 / stack_size
        y = machine_y - 0.425 + (item["stack_index"] * slot_height)
        color_key = item["task_type"] if item["event_type"] == "task_assigned" else item["event_type"]
        color = color_map.get(color_key, "#9C9C9C")

        rect = mpatches.Rectangle(
            (item["start"], y),
            item["duration"],
            slot_height * 0.95,
            facecolor=color,
            edgecolor="black",
            linewidth=0.8,
            alpha=0.9,
        )
        ax.add_patch(rect)
        ax.text(
            item["start"] + item["duration"] / 2.0,
            y + (slot_height * 0.48),
            item["label"],
            ha="center",
            va="center",
            fontsize=7,
            color="white",
            weight="bold",
        )

    ax.set_xlim(0, max_time + 2)
    ax.set_ylim(-1, len(machines))
    ax.set_yticks(range(len(machines)))
    ax.set_yticklabels(machines)
    ax.set_xlabel("Time Step")
    ax.set_ylabel("Machines by Process Order (A -> B -> C)")
    ax.set_title(title)
    ax.grid(True, axis="x", alpha=0.3)
    ax.set_axisbelow(True)

    legend_handles = [
        mpatches.Patch(color="#4C78A8", label="New Assignment"),
        mpatches.Patch(color="#E45756", label="Rework Assignment"),
        mpatches.Patch(color="#F28E2B", label="C Queue/Progress"),
        mpatches.Patch(color="#54A24B", label="Pack Completed"),
    ]
    ax.legend(handles=legend_handles, loc="upper right")

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[Gantt] Direct gantt chart saved: {output_path}")
    return output_path


def test_scenario_1_basic_batch_processing():
    """
    Scenario 1: Basic batch processing
    - batch_size_A=2: process max 2 tasks simultaneously in A
    - batch_size_B=1: process 1 task in B
    - verify basic flow
    """
    print("\n" + "=" * 70)
    print("SCENARIO 1: Basic batch processing (batch_size_A=2)")
    print("=" * 70)

    config = {
        'num_machines_A': 2,
        'num_machines_B': 2,
        'num_machines_C': 1,
        'process_time_A': 8,
        'process_time_B': 4,
        'process_time_C': 2,
        'batch_size_A': 2,
        'batch_size_B': 1,
        'batch_size_C': 4,
        'scheduler_A': 'fifo',
        'scheduler_B': 'fifo',
        'packing_C': 'fifo',
        'max_steps': 50,
        'deterministic_mode': True,
    }

    env = ManufacturingEnv(config)
    env.reset(seed_initial_tasks=False)

    random.seed(42)
    initial_tasks = _generate_initial_tasks(env, count=8, current_time=0)
    env.env_A.add_tasks(initial_tasks)

    print(f"\n[Setup] {len(initial_tasks)} tasks generated")
    print(f"[Setup] Process times: A={config['process_time_A']}, B={config['process_time_B']}, C={config['process_time_C']}")
    print(f"[Setup] Batch sizes: A={config['batch_size_A']}, B={config['batch_size_B']}, C={config['batch_size_C']}")

    print("\n[Simulation] Start...")
    for _ in range(config['max_steps']):
        env.step({})

    print(f"[Simulation] Done (total {config['max_steps']} steps)")

    obs = env._get_observation()
    print(f"\n[Result] Completed tasks: {obs['num_completed']}")
    print(f"[Result] A process pass: {env.env_A.stats['total_passed']}/{env.env_A.stats['total_processed']}")

    try:
        draw_gantt_from_events(
            env.env_A,
            env.env_B,
            env.env_C,
            output_path=RESULTS_DIR / "scenario1_gantt_direct.png",
            title="Scenario 1 - Event-based Gantt (A->B->C)",
        )
    except Exception as e:
        print(f"[Gantt] Direct gantt chart generation failed: {e}")

    validator = ValidationReport()
    is_valid = validator.validate_sync(env.env_A, env.env_B, env.env_C, expect_rework=False)
    validator.print_report()

    return env, is_valid


def test_scenario_2_batch_with_rework():
    """
    Scenario 2: Batch processing + rework
    - batch_size_A=3: induce rework probability
    - verify rework handling
    """
    print("\n" + "=" * 70)
    print("SCENARIO 2: Batch processing + rework (batch_size_A=3)")
    print("=" * 70)

    config = {
        'num_machines_A': 2,
        'num_machines_B': 2,
        'num_machines_C': 1,
        'process_time_A': 8,
        'process_time_B': 4,
        'process_time_C': 2,
        'batch_size_A': 3,
        'batch_size_B': 2,
        'batch_size_C': 4,
        'scheduler_A': 'fifo',
        'scheduler_B': 'rule-based',
        'packing_C': 'greedy',
        'max_steps': 100,
        'deterministic_mode': False,
    }

    env = ManufacturingEnv(config)
    env.reset(seed_initial_tasks=False)

    random.seed(100)
    np.random.seed(100)
    initial_tasks = _generate_initial_tasks(env, count=12, current_time=0)
    env.env_A.add_tasks(initial_tasks)

    print(f"\n[Setup] {len(initial_tasks)} tasks generated")
    print("[Setup] Stochastic mode enabled (rework expected)")

    print("\n[Simulation] Start...")
    for _ in range(config['max_steps']):
        env.step({})

    print(f"[Simulation] Done (total {config['max_steps']} steps)")

    obs = env._get_observation()
    print(f"\n[Result] Completed tasks: {obs['num_completed']}")
    print(f"[Result] A process: {env.env_A.stats['total_passed']}/{env.env_A.stats['total_processed']} (rework {env.env_A.stats['total_reworked']})")

    try:
        draw_gantt_from_events(
            env.env_A,
            env.env_B,
            env.env_C,
            output_path=RESULTS_DIR / "scenario2_gantt_direct.png",
            title="Scenario 2 - Event-based Gantt (A->B->C)",
        )
    except Exception as e:
        print(f"[Gantt] Direct gantt chart generation failed: {e}")

    validator = ValidationReport()
    is_valid = validator.validate_sync(env.env_A, env.env_B, env.env_C, expect_rework=True)
    validator.print_report()

    return env, is_valid


def test_scenario_3_large_batch():
    """
    Scenario 3: Large batch processing
    - batch_size_A=5: verify high-load behavior
    - detect sync issues
    """
    print("\n" + "=" * 70)
    print("SCENARIO 3: Large batch processing (batch_size_A=5)")
    print("=" * 70)

    config = {
        'num_machines_A': 2,
        'num_machines_B': 2,
        'num_machines_C': 1,
        'process_time_A': 10,
        'process_time_B': 5,
        'process_time_C': 3,
        'batch_size_A': 5,
        'batch_size_B': 3,
        'batch_size_C': 5,
        'scheduler_A': 'adaptive',
        'scheduler_B': 'rule-based',
        'packing_C': 'greedy',
        'max_steps': 150,
        'deterministic_mode': True,
    }

    env = ManufacturingEnv(config)
    env.reset(seed_initial_tasks=False)

    random.seed(200)
    initial_tasks = _generate_initial_tasks(env, count=20, current_time=0)
    env.env_A.add_tasks(initial_tasks)

    print(f"\n[Setup] {len(initial_tasks)} tasks generated")
    print("[Setup] Large batch size for stress/sync check")

    print("\n[Simulation] Start...")
    step_count = 0
    for _ in range(config['max_steps']):
        env.step({})
        step_count += 1

    print(f"[Simulation] Done (total {step_count} steps)")

    obs = env._get_observation()
    print(f"\n[Result] Completed tasks: {obs['num_completed']}")

    try:
        draw_gantt_from_events(
            env.env_A,
            env.env_B,
            env.env_C,
            output_path=RESULTS_DIR / "scenario3_gantt_direct.png",
            title="Scenario 3 - Event-based Gantt (A->B->C)",
        )
    except Exception as e:
        print(f"[Gantt] Direct gantt chart generation failed: {e}")

    validator = ValidationReport()
    is_valid = validator.validate_sync(env.env_A, env.env_B, env.env_C, expect_rework=False)
    validator.print_report()

    return env, is_valid


def test_scenario_4_forced_rework_tight_spec():
    """
    Scenario 4: Forced rework with tight A spec
    - tighten spec_a to intentionally induce repeated A failures
    - verify that rework is actually generated and observed
    """
    print("\n" + "=" * 70)
    print("SCENARIO 4: Forced rework with tight A spec")
    print("=" * 70)

    config = {
        'num_machines_A': 1,
        'num_machines_B': 1,
        'num_machines_C': 1,
        'process_time_A': 4,
        'process_time_B': 4,
        'process_time_C': 2,
        'batch_size_A': 2,
        'batch_size_B': 1,
        'batch_size_C': 2,
        'scheduler_A': 'fifo',
        'scheduler_B': 'fifo',
        'packing_C': 'fifo',
        'max_steps': 28,
        'deterministic_mode': True,
    }

    env = ManufacturingEnv(config)
    env.reset(seed_initial_tasks=False)

    random.seed(404)
    np.random.seed(404)
    initial_tasks = _generate_initial_tasks(env, count=6, current_time=0)

    # Force deterministic QA miss in A so tasks must go through rework loop.
    _set_tight_spec_a(initial_tasks, low=60.0, high=61.0)
    env.env_A.add_tasks(initial_tasks)

    print(f"\n[Setup] {len(initial_tasks)} tasks generated")
    print("[Setup] Tight spec_a applied: (60.0, 61.0) for all initial tasks")
    print("[Setup] Rework is intentionally expected")

    print("\n[Simulation] Start...")
    for _ in range(config['max_steps']):
        env.step({})
    print(f"[Simulation] Done (total {config['max_steps']} steps)")

    obs = env._get_observation()
    print(f"\n[Result] Completed tasks: {obs['num_completed']}")
    print(
        f"[Result] A process: {env.env_A.stats['total_passed']}/"
        f"{env.env_A.stats['total_processed']} (rework {env.env_A.stats['total_reworked']})"
    )

    try:
        draw_gantt_from_events(
            env.env_A,
            env.env_B,
            env.env_C,
            output_path=RESULTS_DIR / "scenario4_gantt_direct.png",
            title="Scenario 4 - Forced rework (tight spec A)",
        )
    except Exception as e:
        print(f"[Gantt] Direct gantt chart generation failed: {e}")

    validator = ValidationReport()
    is_valid = validator.validate_sync(env.env_A, env.env_B, env.env_C, expect_rework=True)
    validator.print_report()

    # Guardrail: this scenario must create rework by design.
    assert env.env_A.stats["total_reworked"] > 0, "Scenario 4 should generate A rework but none was observed."

    return env, is_valid


def print_summary(results):
    """Print summary"""
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for scenario, (_env, is_valid) in results.items():
        status = "PASS" if is_valid else "FAIL"
        print(f"{scenario}: {status}")

    all_pass = all(is_valid for _, is_valid in results.values())
    print("\n" + ("=" * 70))
    if all_pass:
        print("All scenarios passed.")
    else:
        print("Some scenarios failed. Check the results above.")
    print("=" * 70)


def main():
    """Main entry"""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    results = {}

    try:
        env1, valid1 = test_scenario_1_basic_batch_processing()
        results['Scenario 1: Basic'] = (env1, valid1)
    except Exception as e:
        print(f"Scenario 1 failed: {e}")
        import traceback
        traceback.print_exc()

    try:
        env2, valid2 = test_scenario_2_batch_with_rework()
        results['Scenario 2: Rework'] = (env2, valid2)
    except Exception as e:
        print(f"Scenario 2 failed: {e}")
        import traceback
        traceback.print_exc()

    try:
        env3, valid3 = test_scenario_3_large_batch()
        results['Scenario 3: Large Batch'] = (env3, valid3)
    except Exception as e:
        print(f"Scenario 3 failed: {e}")
        import traceback
        traceback.print_exc()

    try:
        env4, valid4 = test_scenario_4_forced_rework_tight_spec()
        results['Scenario 4: Forced Rework'] = (env4, valid4)
    except Exception as e:
        print(f"Scenario 4 failed: {e}")
        import traceback
        traceback.print_exc()

    print_summary(results)


if __name__ == '__main__':
    main()
