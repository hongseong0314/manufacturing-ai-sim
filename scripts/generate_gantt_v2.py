# -*- coding: utf-8 -*-
"""
고급 Gantt Chart 생성 스크립트 v2
시뮬레이션 실행 중 각 Task의 정확한 처리 시간을 추적합니다.
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
from src.objects import Task

# 한글 폰트 설정 (영문만 사용)
rcParams['axes.unicode_minus'] = False

class DetailedGanttCollector:
    """매 step마다 Task의 정확한 상태를 추적합니다."""
    
    def __init__(self):
        self.task_states = defaultdict(list)  # {task_uid: [(time, process, machine, state), ...]}
        self.current_time = 0
    
    def collect_state(self, env, current_time):
        """현재 시뮬레이션 상태 기록"""
        self.current_time = current_time
        
        # A공정 머신 상태
        for mid, machine in env.env_A.machines.items():
            if machine.status == 'busy':
                for task in machine.current_batch:
                    self.task_states[task.uid].append({
                        'time': current_time,
                        'process': 'A',
                        'machine': mid,
                        'status': 'processing',
                        'finish_time': machine.finish_time,
                    })
        
        # B공정 머신 상태
        for mid, machine in env.env_B.machines.items():
            if machine.status == 'busy':
                for task in machine.current_batch:
                    self.task_states[task.uid].append({
                        'time': current_time,
                        'process': 'B',
                        'machine': mid,
                        'status': 'processing',
                        'finish_time': machine.finish_time,
                    })
        
        # C공정 대기 상태
        for task in env.env_C.wait_pool:
            self.task_states[task.uid].append({
                'time': current_time,
                'process': 'C',
                'machine': 0,
                'status': 'waiting',
                'finish_time': None,
            })
    
    def extract_intervals(self):
        """연속 구간을 추출합니다."""
        intervals = []
        
        for task_uid, states in self.task_states.items():
            if not states:
                continue
            
            # 공정별로 그룹화
            process_segments = defaultdict(lambda: {'start': None, 'end': None, 'machine': None})
            
            for state in sorted(states, key=lambda x: x['time']):
                key = (state['process'], state['machine'])
                
                if state['status'] == 'processing':
                    if process_segments[key]['start'] is None:
                        process_segments[key]['start'] = state['time']
                    process_segments[key]['end'] = state['time']
        
            # 최종 구간으로 변환
            for (process, machine), segment in process_segments.items():
                if segment['start'] is not None and segment['end'] is not None:
                    intervals.append({
                        'task_uid': task_uid,
                        'process': process,
                        'machine': machine,
                        'start': segment['start'],
                        'end': segment['end'] + 1,  # 포함된 마지막 time까지
                    })
        
        return sorted(intervals, key=lambda x: (x['process'], x['machine'], x['start']))


def simulate_with_tracking(max_steps=150):
    """추적 기능과 함께 시뮬레이션 실행"""
    
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
    
    collector = DetailedGanttCollector()
    
    print("Running simulation with tracking...")
    
    for step in range(max_steps):
        collector.collect_state(env, step)
        state = env.get_decision_state()
        actions = meta.decide(state)
        obs, reward, done, _ = env.step(actions)
        
        if step % 30 == 0:
            print(f"  Step {step}/{max_steps}: {obs['num_completed']} tasks completed")
        
        if done:
            break
    
    intervals = collector.extract_intervals()
    
    print(f"\nSimulation complete: {obs['num_completed']} tasks completed")
    print(f"Extracted {len(intervals)} task intervals")
    
    return intervals, max_steps


def create_gantt_visualization(intervals, total_time, filename='gantt_advanced.png'):
    """고급 Gantt chart 시각화"""
    
    # 공정과 머신별로 Y축 구성
    machines_map = defaultdict(set)
    for interval in intervals:
        machines_map[(interval['process'], interval['machine'])].add(interval['machine'])
    
    # Y축 라벨 구성
    y_labels = []
    y_position = {}
    y_idx = 0
    
    # 각 공정별로 머신 정렬
    for process in ['A', 'B', 'C']:
        process_machines = sorted(set(m for p, m in machines_map if p == process))
        for machine_id in process_machines:
            label = f"P{process}_M{machine_id}"
            y_labels.append(label)
            y_position[(process, machine_id)] = y_idx
            y_idx += 1
    
    # 색상 팔레트
    colors_process = {
        'A': '#FFB6B6',  # 밝은 빨강
        'B': '#B6D7FF',  # 밝은 파랑
        'C': '#B6FFB6',  # 밝은 초록
    }
    
    # 도형 생성
    fig, ax = plt.subplots(figsize=(18, len(y_labels) + 2))
    
    # Task 박스 그리기
    task_colors = {}
    color_palette = plt.cm.Set3(np.linspace(0, 1, 20))
    
    for idx, interval in enumerate(intervals):
        y_pos = y_position[(interval['process'], interval['machine'])]
        start = interval['start']
        duration = interval['end'] - interval['start']
        
        # Task에 색상 할당
        task_uid = interval['task_uid']
        if task_uid not in task_colors:
            task_colors[task_uid] = color_palette[task_uid % len(color_palette)]
        
        # 막대 그리기
        rect = mpatches.Rectangle((start, y_pos - 0.35), duration, 0.7,
                                  facecolor=task_colors[task_uid],
                                  edgecolor='black', linewidth=1.5)
        ax.add_patch(rect)
        
        # Task ID 표시
        if duration >= 3:
            ax.text(start + duration/2, y_pos, f"T{task_uid}",
                   ha='center', va='center', fontsize=9, fontweight='bold')
    
    # 축 설정
    ax.set_yticks(range(len(y_labels)))
    ax.set_yticklabels(y_labels, fontsize=11, fontweight='bold')
    ax.set_xlim(0, total_time + 5)
    ax.set_ylim(-0.5, len(y_labels) - 0.5)
    
    # 축 레이블 및 제목
    ax.set_xlabel('Time (minutes)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Machine', fontsize=12, fontweight='bold')
    ax.set_title('Manufacturing Process Gantt Chart - Detailed View\n(Task Processing Schedule)', 
                fontsize=14, fontweight='bold', pad=20)
    
    # 격자 추가
    ax.grid(True, axis='x', alpha=0.3, linestyle='--', linewidth=0.8)
    ax.set_axisbelow(True)
    
    # 범례
    legend_elements = [
        mpatches.Patch(facecolor=colors_process['A'], edgecolor='black', label='Process A (Assembly)'),
        mpatches.Patch(facecolor=colors_process['B'], edgecolor='black', label='Process B (Cleaning)'),
        mpatches.Patch(facecolor=colors_process['C'], edgecolor='black', label='Process C (Packing)'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=11, framealpha=0.9)
    
    # X축 눈금 설정
    ax.set_xticks(range(0, total_time + 1, 10))
    
    plt.tight_layout()
    plt.savefig(filename, dpi=200, bbox_inches='tight')
    print(f"\nGantt chart saved: {filename}")
    
    return fig, ax


def create_summary_statistics(intervals):
    """성능 통계 요약"""
    
    print("\n" + "="*80)
    print("PERFORMANCE STATISTICS")
    print("="*80)
    
    # 공정별 통계
    process_stats = defaultdict(lambda: {'count': 0, 'total_time': 0, 'avg_wait': 0})
    
    for interval in intervals:
        process = interval['process']
        process_stats[process]['count'] += 1
        process_stats[process]['total_time'] += (interval['end'] - interval['start'])
    
    print("\nProcess Statistics:")
    for process in ['A', 'B', 'C']:
        if process in process_stats:
            stats = process_stats[process]
            print(f"\n  Process {process}:")
            print(f"    - Total intervals: {stats['count']}")
            print(f"    - Total processing time: {stats['total_time']} minutes")
            if stats['count'] > 0:
                avg_time = stats['total_time'] / stats['count']
                print(f"    - Average interval duration: {avg_time:.1f} minutes")
    
    # 머신별 통계
    print("\n" + "-"*80)
    print("Machine Utilization:")
    machine_utilization = defaultdict(float)
    
    for interval in intervals:
        key = (interval['process'], interval['machine'])
        machine_utilization[key] += (interval['end'] - interval['start'])
    
    for (process, machine), util_time in sorted(machine_utilization.items()):
        utilization_pct = (util_time / 150) * 100  # 150분 기준
        print(f"  P{process}_M{machine}: {util_time:3.0f} min ({utilization_pct:5.1f}%)")
    
    # Task별 처리 경로
    print("\n" + "-"*80)
    print("Task Processing Path:")
    
    task_processes = defaultdict(list)
    for interval in intervals:
        task_processes[interval['task_uid']].append(interval['process'])
    
    # 유니크한 경로 찾기
    paths = defaultdict(int)
    for task_uid, processes in task_processes.items():
        path = '->'.join(sorted(set(processes)))
        paths[path] += 1
    
    for path, count in sorted(paths.items()):
        print(f"  {path}: {count} tasks")
    
    print("\n" + "="*80)


if __name__ == '__main__':
    print("\n" + "="*80)
    print("ADVANCED GANTT CHART GENERATION v2")
    print("="*80)
    
    # 시뮬레이션 실행 및 데이터 수집
    intervals, total_time = simulate_with_tracking(max_steps=150)
    
    # Gantt chart 생성
    output_file = str(Path(ROOT / 'docs' / 'gantt_advanced.png'))
    create_gantt_visualization(intervals, total_time, filename=output_file)
    
    # 통계 출력
    create_summary_statistics(intervals)
    
    print("\nCompleted successfully!")
    print(f"Output file: {output_file}")
