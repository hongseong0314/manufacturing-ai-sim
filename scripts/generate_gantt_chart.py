# -*- coding: utf-8 -*-
"""
Gantt Chart 생성 스크립트
시뮬레이션 결과를 바탕으로 각 공정별 머신의 Task 처리 일정을 시각화합니다.
"""

import sys
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import rcParams
import numpy as np
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.agents.factory import build_meta_scheduler
from src.environment.manufacturing_env import ManufacturingEnv

# 한글 폰트 설정
rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial']
rcParams['axes.unicode_minus'] = False

class GanttChartCollector:
    """시뮬레이션 중 Task 처리 정보를 수집합니다."""
    
    def __init__(self):
        self.task_events = []  # (task_uid, machine_id, start_time, end_time, process_name, status)
        
    def record_event(self, task_uid, machine_id, start_time, end_time, process_name, status='process'):
        """Task 처리 이벤트 기록"""
        self.task_events.append({
            'task_uid': task_uid,
            'machine_id': machine_id,
            'start_time': start_time,
            'end_time': end_time,
            'process': process_name,
            'status': status,
        })
    
    def get_sorted_events(self):
        """정렬된 이벤트 반환"""
        return sorted(self.task_events, key=lambda x: (x['process'], x['machine_id'], x['start_time']))


def collect_simulation_data(max_steps=150):
    """시뮬레이션을 실행하고 Task 처리 데이터를 수집합니다."""
    
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
        'batch_size_C': 4,
    }
    
    env = ManufacturingEnv(env_config)
    meta = build_meta_scheduler(env.config)
    obs = env.reset()
    
    # 각 공정의 머신 상태를 추적
    machine_task_map = defaultdict(list)  # {(process, machine_id): [(start, end, task_uid), ...]}
    task_timeline = {}  # {task_uid: [(time, process, machine_id, event_type), ...]}
    
    print("시뮬레이션 실행 중...")
    
    for step in range(max_steps):
        # A공정 머신 상태 수집
        for mid, machine in env.env_A.machines.items():
            if machine.status == 'busy':
                for task in machine.current_batch:
                    if task.uid not in task_timeline:
                        task_timeline[task.uid] = []
                    task_timeline[task.uid].append({
                        'time': step,
                        'process': 'A',
                        'machine': mid,
                        'state': 'busy',
                        'finish_time': machine.finish_time,
                    })
        
        # B공정 머신 상태 수집
        for mid, machine in env.env_B.machines.items():
            if machine.status == 'busy':
                for task in machine.current_batch:
                    if task.uid not in task_timeline:
                        task_timeline[task.uid] = []
                    task_timeline[task.uid].append({
                        'time': step,
                        'process': 'B',
                        'machine': mid,
                        'state': 'busy',
                        'finish_time': machine.finish_time,
                    })
        
        state = env.get_decision_state()
        actions = meta.decide(state)
        obs, reward, done, _ = env.step(actions)
        
        if step % 30 == 0:
            print(f"  Step {step}/{max_steps}: {obs['num_completed']} tasks completed")
    
    print(f"총 {obs['num_completed']}개 Task 완료됨")
    
    # Task timeline을 처리 구간으로 변환
    processed_events = []
    
    for task_uid, events in task_timeline.items():
        # 각 공정별로 그룹화
        process_groups = defaultdict(list)
        for event in events:
            key = (event['process'], event['machine'])
            process_groups[key].append(event['time'])
        
        # 연속 구간 찾기
        for (process, machine), times in process_groups.items():
            if times:
                start_time = min(times)
                end_time = max(times) + 1
                
                processed_events.append({
                    'task_uid': task_uid,
                    'machine_id': machine,
                    'start_time': start_time,
                    'end_time': end_time,
                    'process': process,
                })
    
    return sorted(processed_events, key=lambda x: (x['process'], x['machine_id'], x['start_time']))


def generate_gantt_chart(events, output_path='gantt_chart.png'):
    """Gantt chart 생성"""
    
    # 공정별 머신 목록 생성
    machines_by_process = defaultdict(set)
    for event in events:
        machines_by_process[event['process']].add(event['machine_id'])
    
    # Y축 레이블 및 Y좌표 매핑
    y_labels = []
    y_coords = {}
    y_index = 0
    
    process_order = ['A', 'B', 'C']
    for process in process_order:
        if process in machines_by_process:
            for machine_id in sorted(machines_by_process[process]):
                label = f"{process}_{machine_id}"
                y_labels.append(label)
                y_coords[(process, machine_id)] = y_index
                y_index += 1
    
    # 색상 맵 (Task별)
    colors = plt.cm.tab20(np.linspace(0, 1, 20))
    task_colors = {}
    color_idx = 0
    
    # Figure 생성
    fig, ax = plt.subplots(figsize=(16, len(y_labels) + 2))
    
    # 각 Task를 막대로 표시
    for event in events:
        y_pos = y_coords[(event['process'], event['machine_id'])]
        start = event['start_time']
        duration = event['end_time'] - event['start_time']
        
        # Task별 색상 할당
        task_uid = event['task_uid']
        if task_uid not in task_colors:
            task_colors[task_uid] = colors[color_idx % len(colors)]
            color_idx += 1
        
        # 막대 그리기
        ax.barh(y_pos, duration, left=start, height=0.8, 
               color=task_colors[task_uid], edgecolor='black', linewidth=0.5)
        
        # Task ID 표시 (큰 박스에만)
        if duration >= 2:
            ax.text(start + duration/2, y_pos, f"T{task_uid}", 
                   ha='center', va='center', fontsize=8, fontweight='bold')
    
    # 축 설정
    ax.set_yticks(range(len(y_labels)))
    ax.set_yticklabels(y_labels, fontsize=10)
    ax.set_xlabel('Time (minutes)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Machine', fontsize=12, fontweight='bold')
    ax.set_title('Manufacturing Process Gantt Chart\n(A: Assembly, B: Cleaning, C: Packing)', 
                fontsize=14, fontweight='bold')
    
    # 격자선 추가
    ax.grid(True, axis='x', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)
    
    # X축 범위
    max_time = max(e['end_time'] for e in events) if events else 100
    ax.set_xlim(0, max_time + 5)
    
    # 범례 (공정별 색상)
    process_patches = [
        mpatches.Patch(facecolor='lightblue', edgecolor='black', label='Process A (Assembly)'),
        mpatches.Patch(facecolor='lightgreen', edgecolor='black', label='Process B (Cleaning)'),
        mpatches.Patch(facecolor='lightyellow', edgecolor='black', label='Process C (Packing)'),
    ]
    ax.legend(handles=process_patches, loc='upper right', fontsize=10)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nGantt chart saved: {output_path}")
    
    return fig, ax


def generate_gantt_chart_by_process(events, output_path='gantt_by_process.png'):
    """공정별로 분리된 Gantt chart 생성"""
    
    processes = sorted(set(e['process'] for e in events))
    fig, axes = plt.subplots(len(processes), 1, figsize=(16, 4*len(processes)))
    
    if len(processes) == 1:
        axes = [axes]
    
    process_colors = {'A': '#FF9999', 'B': '#99CCFF', 'C': '#99FF99'}
    
    for idx, process in enumerate(processes):
        ax = axes[idx]
        
        # 해당 공정의 이벤트만 필터링
        process_events = [e for e in events if e['process'] == process]
        
        # 머신별로 정렬
        machines = sorted(set(e['machine_id'] for e in process_events))
        
        for m_idx, machine_id in enumerate(machines):
            machine_events = [e for e in process_events if e['machine_id'] == machine_id]
            
            for event in machine_events:
                start = event['start_time']
                duration = event['end_time'] - event['start_time']
                
                ax.barh(m_idx, duration, left=start, height=0.7,
                       color=process_colors[process], edgecolor='black', linewidth=1)
                
                # Task ID 표시
                if duration >= 2:
                    ax.text(start + duration/2, m_idx, f"T{event['task_uid']}", 
                           ha='center', va='center', fontsize=9, fontweight='bold')
        
        # 축 설정
        ax.set_yticks(range(len(machines)))
        ax.set_yticklabels([f"M{m}" for m in machines], fontsize=10)
        ax.set_xlabel('Time (minutes)', fontsize=11, fontweight='bold')
        ax.set_ylabel('Machine', fontsize=11, fontweight='bold')
        
        process_names = {'A': 'Assembly', 'B': 'Cleaning', 'C': 'Packing'}
        ax.set_title(f'Process {process}: {process_names[process]}', fontsize=12, fontweight='bold')
        
        ax.grid(True, axis='x', alpha=0.3, linestyle='--')
        ax.set_axisbelow(True)
        
        max_time = max(e['end_time'] for e in process_events) if process_events else 50
        ax.set_xlim(0, max_time + 3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Process-separated Gantt chart saved: {output_path}")
    
    return fig, axes


if __name__ == '__main__':
    print("=" * 80)
    print("Gantt Chart 생성 시작")
    print("=" * 80)
    
    # 시뮬레이션 실행 및 데이터 수집
    events = collect_simulation_data(max_steps=150)
    
    print(f"\n총 {len(events)}개의 Task 처리 구간 수집됨")
    
    # 통합 Gantt chart
    fig1, ax1 = generate_gantt_chart(events, 
                                     output_path=str(Path(ROOT / 'docs' / 'gantt_chart.png')))
    
    # 공정별 분리 Gantt chart
    fig2, axes2 = generate_gantt_chart_by_process(events,
                                                  output_path=str(Path(ROOT / 'docs' / 'gantt_by_process.png')))
    
    print("\n" + "=" * 80)
    print("Gantt chart 생성 완료!")
    print("=" * 80)
    
    plt.show()
