# -*- coding: utf-8 -*-
"""
Run a manufacturing simulation, collect metrics, and save plots to a PDF.
Produces: docs/figures/simulation_report.pdf
"""
import os
import random
import sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.backends.backend_pdf import PdfPages

# Ensure workspace root is on sys.path so `src` imports work when run as a script
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.environment.manufacturing_env import ManufacturingEnv
from src.agents.factory import build_meta_scheduler

sns.set(style="whitegrid")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'docs', 'figures')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Simulation config
env_config = {
    'num_machines_A': 3,
    'num_machines_B': 2,
    'num_machines_C': 2,
    'process_time_A': 8,
    'process_time_B': 4,
    'process_time_C': 4,
    'max_steps': 400,
    'deterministic_mode': False
}

# Seeds for reproducibility
SEED = 0
np.random.seed(SEED)
random.seed(SEED)

STEPS = 300

def collect_and_plot():
    env = ManufacturingEnv(env_config)
    meta = build_meta_scheduler(env.config)
    obs = env.reset()

    # Metrics storage
    time_idx = []
    queue_A = []
    rework_A = []
    queue_B = []
    queue_C = []
    completed = []
    util_A = []
    util_B = []
    util_C = []

    # Gantt data: per-task intervals [(process, start, end)]
    task_intervals = {}
    prev_task_machine = {}  # uid -> (proc_name, machine_key)
    seen_tasks = set()

    for t in range(STEPS):
        state = env.get_decision_state()
        actions = meta.decide(state)
        obs, reward, done, info = env.step(actions)

        time_idx.append(obs['time'])
        queue_A.append(len(env.env_A.wait_pool))
        rework_A.append(len(env.env_A.rework_pool))
        queue_B.append(len(env.env_B.wait_pool))
        queue_C.append(len(env.env_C.wait_pool))
        completed.append(len(env.completed_tasks))

        util_A.append(sum(1 for m in env.env_A.machines.values() if m.status=='busy') / max(1, len(env.env_A.machines)))
        util_B.append(sum(1 for m in env.env_B.machines.values() if m.status=='busy') / max(1, len(env.env_B.machines)))
        util_C.append(sum(1 for m in env.env_C.machines.values() if m.status=='busy') / max(1, len(env.env_C.machines)))

        # --- Gantt tracking: map current busy tasks to machines
        current_task_machine = {}
        # A machines
        for mid, m in env.env_A.machines.items():
            for task in m.current_batch:
                current_task_machine[task.uid] = ('A', f'A_{mid}', m.finish_time, env.env_A.process_time)
                seen_tasks.add(task.uid)
        # B machines
        for mid, m in env.env_B.machines.items():
            for task in m.current_batch:
                current_task_machine[task.uid] = ('B', f'B_{mid}', m.finish_time, env.env_B.process_time)
                seen_tasks.add(task.uid)
        # C machines
        for mid, m in env.env_C.machines.items():
            for task in m.current_batch:
                current_task_machine[task.uid] = ('C', f'C_{mid}', m.finish_time, env.env_C.process_time)
                seen_tasks.add(task.uid)

        # Start intervals for newly busy tasks
        for uid, info in current_task_machine.items():
            if uid not in prev_task_machine:
                proc_name, machine_key, finish_time, p_time = info
                start_time = finish_time - p_time if finish_time is not None else obs['time']
                task_intervals.setdefault(uid, []).append([proc_name, start_time, None])

        # Close intervals for tasks that finished processing this step
        for uid, info in list(prev_task_machine.items()):
            if uid not in current_task_machine:
                # find last open interval and close it
                intervals = task_intervals.get(uid, [])
                if intervals:
                    for iv in reversed(intervals):
                        if iv[2] is None:
                            iv[2] = obs['time']
                            break

        # If tasks were completed this step, ensure C intervals closed
        # Ensure any remaining open intervals are closed for tasks completed in C.
        for task in env.completed_tasks:
            uid = task.uid
            intervals = task_intervals.get(uid, [])
            if intervals:
                for iv in reversed(intervals):
                    if iv[2] is None:
                        iv[2] = obs['time']
                        break

        prev_task_machine = current_task_machine

    # Create PDF with multiple plots
    pdf_path = os.path.join(OUTPUT_DIR, 'simulation_report.pdf')
    with PdfPages(pdf_path) as pdf:
        # 1) Queue sizes
        plt.figure(figsize=(10, 6))
        plt.plot(time_idx, queue_A, label='A wait')
        plt.plot(time_idx, rework_A, label='A rework')
        plt.plot(time_idx, queue_B, label='B wait')
        plt.plot(time_idx, queue_C, label='C wait')
        plt.xlabel('Time')
        plt.ylabel('Queue Size')
        plt.title('Queue sizes over time')
        plt.legend()
        pdf.savefig()
        plt.close()

        # 2) Completed over time
        plt.figure(figsize=(10, 4))
        plt.plot(time_idx, completed, color='tab:green')
        plt.xlabel('Time')
        plt.ylabel('Cumulative Completed Tasks')
        plt.title('Completed tasks over time')
        pdf.savefig()
        plt.close()

        # 3) Utilization
        plt.figure(figsize=(10, 6))
        plt.plot(time_idx, util_A, label='A util')
        plt.plot(time_idx, util_B, label='B util')
        plt.plot(time_idx, util_C, label='C util')
        plt.xlabel('Time')
        plt.ylabel('Utilization (fraction)')
        plt.title('Machine utilization over time')
        plt.legend()
        pdf.savefig()
        plt.close()

        # 4) Rework fraction (rework / (rework + completed + epsilon))
        eps = 1e-6
        rework_frac = [r / (r + c + eps) for r, c in zip(rework_A, completed)]
        plt.figure(figsize=(10, 4))
        plt.plot(time_idx, rework_frac, color='tab:orange')
        plt.xlabel('Time')
        plt.ylabel('Rework fraction')
        plt.title('A-process rework fraction (rework / (rework+completed))')
        pdf.savefig()
        plt.close()

        # 5) Gantt chart (show first N tasks)
        max_tasks = 40
        task_list = sorted(list(seen_tasks))[:max_tasks]
        fig, ax = plt.subplots(figsize=(12, max(4, len(task_list) * 0.2)))
        y_positions = {uid: i for i, uid in enumerate(task_list)}
        colors = {'A': 'tab:blue', 'B': 'tab:orange', 'C': 'tab:green'}
        for uid in task_list:
            intervals = task_intervals.get(uid, [])
            for iv in intervals:
                proc, start, end = iv
                if end is None:
                    end = STEPS
                ax.barh(y_positions[uid], end - start, left=start, height=0.6, color=colors.get(proc, 'gray'), edgecolor='k')
        ax.set_yticks(list(y_positions.values()))
        ax.set_yticklabels([f'Task {uid}' for uid in task_list])
        ax.set_xlabel('Time')
        ax.set_title('Gantt chart (first %d tasks)' % len(task_list))
        pdf.savefig(fig)
        plt.close(fig)

    print(f"Saved simulation report: {pdf_path}")
    return pdf_path


if __name__ == '__main__':
    path = collect_and_plot()
    print('Done. PDF at:', path)
