# -*- coding: utf-8 -*-
"""
Task별 상세 처리 시간 추적
각 Task가 언제부터 언제까지 어느 공정에서 처리되었는지 추적합니다.
"""

import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.environment.manufacturing_env import ManufacturingEnv

def track_task_details(max_steps=150):
    """Task별 상세 정보 추적"""
    
    env_config = {
        'num_machines_A': 2,
        'num_machines_B': 2,
        'num_machines_C': 1,
        'process_time_A': 8,
        'process_time_B': 4,
        'max_steps': max_steps,
        'deterministic_mode': True,
        'scheduler_B': 'rule-based',
        'packing_C': 'greedy',
        'N_pack': 4,
    }
    
    env = ManufacturingEnv(env_config)
    obs = env.reset()
    
    # Task의 위치 변경 추적
    task_locations = defaultdict(list)  # {task_uid: [(time, location), ...]}
    task_events = defaultdict(list)     # {task_uid: [(time, event), ...]}
    
    print("Running simulation with detailed tracking...")
    
    for step in range(max_steps):
        # 각 공정의 Task 위치 기록
        
        # A공정 처리 중인 Task
        for mid, machine in env.env_A.machines.items():
            if machine.status == 'busy':
                for task in machine.current_batch:
                    task_locations[task.uid].append((step, f'Processing A_M{mid}'))
            elif machine.status == 'idle':
                for task in machine.current_batch:
                    task_locations[task.uid].append((step, f'Waiting A_M{mid}'))
        
        # A공정 대기 중인 Task
        for task in env.env_A.wait_pool:
            task_locations[task.uid].append((step, 'Queue_A'))
        
        # A공정 재작업 대기 중인 Task
        for task in env.env_A.rework_pool:
            task_locations[task.uid].append((step, 'Rework_A'))
        
        # B공정 처리 중인 Task
        for mid, machine in env.env_B.machines.items():
            if machine.status == 'busy':
                for task in machine.current_batch:
                    task_locations[task.uid].append((step, f'Processing B_M{mid}'))
        
        # B공정 대기 중인 Task
        for task in env.env_B.wait_pool:
            task_locations[task.uid].append((step, 'Queue_B'))
        
        # B공정 재세정 대기 중인 Task
        for task in env.env_B.rework_pool:
            task_locations[task.uid].append((step, 'Rework_B'))
        
        # C공정 대기 중인 Task
        for task in env.env_C.wait_pool:
            task_locations[task.uid].append((step, 'Queue_C'))
        
        # 완료된 Task
        for task in env.env_C.completed_tasks:
            task_locations[task.uid].append((step, 'COMPLETED'))
        
        obs, reward, done, _ = env.step({})
        
        if step % 30 == 0:
            print(f"  Step {step}/{max_steps}")
    
    print(f"\nSimulation complete")
    
    return task_locations, env.completed_tasks


def analyze_task_timeline(task_locations, completed_tasks):
    """Task 이동 경로 분석"""
    
    print("\n" + "="*100)
    print("TASK TIMELINE ANALYSIS")
    print("="*100)
    
    # 특정 Task 상세 분석
    focus_tasks = [0, 2, 4, 5, 6, 7]
    
    for task_uid in sorted(focus_tasks):
        if task_uid not in task_locations:
            print(f"\nTask {task_uid}: Not found")
            continue
        
        locations = task_locations[task_uid]
        
        # 상태 변화 추적
        state_changes = []
        prev_state = None
        state_start = None
        
        for time, state in locations:
            if state != prev_state:
                if prev_state is not None:
                    state_changes.append({
                        'state': prev_state,
                        'start': state_start,
                        'end': time - 1,
                        'duration': (time - 1) - state_start + 1,
                    })
                prev_state = state
                state_start = time
        
        # 마지막 상태
        if prev_state is not None:
            state_changes.append({
                'state': prev_state,
                'start': state_start,
                'end': locations[-1][0],
                'duration': locations[-1][0] - state_start + 1,
            })
        
        # Task 정보 출력
        is_completed = any(t.uid == task_uid for t in completed_tasks)
        status = "COMPLETED" if is_completed else "INCOMPLETE"
        
        print(f"\n{'='*100}")
        print(f"Task {task_uid}: [{status}]")
        print(f"{'='*100}")
        
        total_duration = locations[-1][0] - locations[0][0] + 1
        print(f"  Total duration: {total_duration} minutes (from {locations[0][0]} to {locations[-1][0]})")
        
        print(f"\n  Timeline:")
        for i, change in enumerate(state_changes):
            state = change['state']
            start = change['start']
            end = change['end']
            duration = change['duration']
            
            # 상태별 색상 표시
            if 'Processing' in state:
                status_str = f"[PROC] {state}"
            elif 'Queue' in state:
                status_str = f"[WAIT] {state}"
            elif 'Rework' in state:
                status_str = f"[REWORK] {state}"
            elif 'COMPLETED' in state:
                status_str = "[DONE] COMPLETED"
            else:
                status_str = state
            
            print(f"    {i+1}. {status_str:25s} | {start:3d}~{end:3d} min ({duration:3d} min)")
        
        # 통계
        total_processing = sum(c['duration'] for c in state_changes if 'Processing' in c['state'])
        total_waiting = sum(c['duration'] for c in state_changes if 'Queue' in c['state'])
        total_rework = sum(c['duration'] for c in state_changes if 'Rework' in c['state'])
        
        print(f"\n  Summary:")
        print(f"    - Total processing: {total_processing} minutes")
        print(f"    - Total waiting:    {total_waiting} minutes")
        print(f"    - Total rework:     {total_rework} minutes")
        print(f"    - Efficiency:       {(total_processing / total_duration * 100):.1f}%")


def compare_tasks(task_locations, completed_tasks):
    """Task 비교 분석"""
    
    print("\n" + "="*100)
    print("COMPARATIVE ANALYSIS - Why did T4 and T5 take longer?")
    print("="*100)
    
    task_summary = {}
    
    for task_uid in [0, 2, 4, 5, 6, 7]:
        if task_uid not in task_locations:
            continue
        
        locations = task_locations[task_uid]
        
        # 시작/종료 시간
        start_time = locations[0][0]
        end_time = locations[-1][0]
        total_time = end_time - start_time + 1
        
        # 각 상태별 시간
        state_times = defaultdict(int)
        prev_state = None
        prev_time = locations[0][0]
        
        for time, state in locations:
            if state != prev_state:
                if prev_state is not None:
                    state_times[prev_state] += (time - prev_time)
                prev_state = state
                prev_time = time
        
        if prev_state is not None:
            state_times[prev_state] += (locations[-1][0] - prev_time + 1)
        
        # Processing과 non-processing 시간
        proc_time = sum(v for k, v in state_times.items() if 'Processing' in k)
        nonproc_time = total_time - proc_time
        
        is_completed = any(t.uid == task_uid for t in completed_tasks)
        
        task_summary[task_uid] = {
            'total_time': total_time,
            'proc_time': proc_time,
            'nonproc_time': nonproc_time,
            'state_times': dict(state_times),
            'completed': is_completed,
        }
    
    # 테이블로 출력
    print("\n  Task Comparison Table:")
    print(f"  {'Task':>6} {'Total':>8} {'Proc':>8} {'Wait':>8} {'Rework':>8} {'Status':>12}")
    print(f"  {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*12}")
    
    for task_uid in sorted(task_summary.keys()):
        summary = task_summary[task_uid]
        total = summary['total_time']
        proc = summary['proc_time']
        wait = sum(v for k, v in summary['state_times'].items() if 'Queue' in k)
        rework = sum(v for k, v in summary['state_times'].items() if 'Rework' in k)
        status = "DONE" if summary['completed'] else "PENDING"
        
        print(f"  T{task_uid:>4} {total:>7} m {proc:>7} m {wait:>7} m {rework:>7} m {status:>12}")
    
    # 분석
    print("\n  Analysis:")
    print(f"  - T0, T2: Quick completion (early tasks)")
    print(f"  - T4, T5: Longer duration due to:")
    
    for task_uid in [4, 5]:
        if task_uid in task_summary:
            summary = task_summary[task_uid]
            rework_time = sum(v for k, v in summary['state_times'].items() if 'Rework' in k)
            wait_time = sum(v for k, v in summary['state_times'].items() if 'Queue' in k)
            
            if rework_time > 0:
                print(f"    · T{task_uid}: Rework in B-process ({rework_time} min)")
            if wait_time > 20:
                print(f"    · T{task_uid}: Long waiting time ({wait_time} min)")


if __name__ == '__main__':
    print("\n" + "="*100)
    print("DETAILED TASK TRACKING ANALYSIS")
    print("="*100)
    
    # 시뮬레이션 실행 및 데이터 수집
    task_locations, completed_tasks = track_task_details(max_steps=150)
    
    # Task 타임라인 분석
    analyze_task_timeline(task_locations, completed_tasks)
    
    # Task 비교 분석
    compare_tasks(task_locations, completed_tasks)
    
    print("\n" + "="*100)
    print("Analysis complete!")
    print("="*100)
