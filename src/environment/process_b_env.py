# -*- coding: utf-8 -*-
"""
B공정 환경 (세정 공정)
스케줄러를 통한 동적 레시피 결정 및 QA 검증
"""

from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from src.objects import Task, ProcessB_Machine
from src.environment.schedulers_b import FIFOBaseline, RuleBasedScheduler, RLBasedScheduler


class ProcessB_Env:
    """
    B공정 환경 클래스
    세정 공정을 시뮬레이션하고, 선택된 스케줄러로 레시피를 결정합니다.
    """
    
    # 물리 모델 상수 (v1 기준)
    C1_BASE = 0.4
    C2 = 0.3
    C3 = 0.2
    D_BASE = 40.0
    C12_BASE = 0.01
    DELTA_C = 0.001
    DELTA_D = 0.02
    
    ALPHA = 0.15          # 용액 효율 감소율
    ALPHA_K = 0.1         # 용액 효율 곡률
    BETA = 1.5            # 노이즈 최대값
    BETA_K = 0.1          # 노이즈 곡률
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.num_machines = config.get('num_machines_B', 5)
        self.process_time = config.get('process_time_B', 4)
        self.batch_size_B = config.get('batch_size_B', 1)  # B공정 배치 크기
        
        # 장비 초기화
        self.machines: Dict[int, ProcessB_Machine] = {
            i: ProcessB_Machine(i, batch_size=self.batch_size_B) for i in range(self.num_machines)
        }
        
        # 대기열 관리
        self.wait_pool: List[Task] = []
        self.rework_pool: List[Task] = []
        
        # 스케줄러 선택
        scheduler_type = config.get('scheduler_B', 'rule-based')
        if scheduler_type == 'fifo':
            self.scheduler = FIFOBaseline(config)
        elif scheduler_type == 'rule-based':
            self.scheduler = RuleBasedScheduler(config)
        elif scheduler_type == 'rl':
            self.scheduler = RLBasedScheduler(config)
        else:
            self.scheduler = RuleBasedScheduler(config)
        
        # 설정
        self.deterministic = config.get('deterministic_mode', False)
        
        # 통계
        self.stats = {
            'total_processed': 0,
            'total_passed': 0,
            'total_reworked': 0,
            'solution_replacements': 0,
            'first_pass_rate': 0.0,
            'avg_rework_count': 0.0,
        }
        
        # 이벤트 로그 (Gantt chart 생성용)
        self.event_log: List[Dict[str, Any]] = []

    def reset(self):
        """환경 초기화"""
        self.machines = {
            i: ProcessB_Machine(i, batch_size=self.batch_size_B) for i in range(self.num_machines)
        }
        self.wait_pool = []
        self.rework_pool = []
        self.event_log = []
        
        self.stats = {
            'total_processed': 0,
            'total_passed': 0,
            'total_reworked': 0,
            'solution_replacements': 0,
            'first_pass_rate': 0.0,
            'avg_rework_count': 0.0,
        }

    def add_tasks(self, tasks: List[Task]):
        """새로운 Task들을 대기열에 추가"""
        for task in tasks:
            task.location = 'QUEUE_B'
        self.wait_pool.extend(tasks)

    def _run_qa_check(
        self, 
        machine: ProcessB_Machine, 
        recipe: List[float], 
        task: Task, 
        current_time: int
    ) -> Dict[str, Any]:
        """B공정 QA 검증"""
        # 레시피 값이 문자열일 수 있으므로 float 변환
        try:
            r1, r2, r3 = [float(x) for x in recipe]
        except (ValueError, TypeError):
            r1, r2, r3 = 50.0, 50.0, 30.0
        
        # 간단한 선형 모델 (과도한 값 방지)
        # 기본값: (r1+r2+r3)/3로 대략 50에서 70 범위
        base_quality = (r1 + r2 + r3) / 3.0
        
        # 용액 효율 감소 (v 값에 따라)
        effectiveness = max(0.1, 1.0 - self.ALPHA * (machine.v / 30.0))
        
        # 단순 QA값: 50 ~ 100 범위로 정규화
        mean_qa = 50.0 + (base_quality - 40.0) * 0.5 * effectiveness
        mean_qa = max(50.0, min(100.0, mean_qa))  # 50 ~ 100 범위 제한
        
        # Deterministic 모드
        if self.deterministic:
            realized_qa = mean_qa
        else:
            std_dev = self.BETA * 0.1  # 노이즈 최대 ±5 정도
            realized_qa = np.random.normal(mean_qa, std_dev)
            realized_qa = max(50.0, min(100.0, realized_qa))  # 범위 제한
        
        # 기계 나이에 따른 degradation (선택사항)
        degradation = 1.0 - (machine.b_age / 1000.0) * 0.1
        realized_qa *= degradation
        realized_qa = max(50.0, min(100.0, realized_qa))
        
        # QA 판정
        min_b, max_b = task.spec_b
        passed = min_b < realized_qa < max_b
        
        return {
            'passed': passed,
            'realized_qa': realized_qa,
            'mean_qa': mean_qa,
            'effectiveness': effectiveness,
        }

    def step(self, current_time: int, actions: Dict[str, Any] = None) -> Dict[str, Any]:
        """B공정 1 time step 진행"""
        succeeded_tasks = []
        rework_tasks = []
        solution_replacements_this_step = 0
        
        # 1단계: 완료된 세정 처리
        for m in self.machines.values():
            if m.status == 'busy' and current_time >= m.finish_time:
                recipe_used = m.current_recipe if m.current_recipe else [0.0, 0.0, 0.0]
                finished_batch = m.finish_processing()
                
                # 이벤트: task 완료
                task_uids = [t.uid for t in finished_batch]
                self.event_log.append({
                    'timestamp': current_time,
                    'event_type': 'task_completed',
                    'process': 'B',
                    'machine_id': m.id,
                    'task_uids': task_uids,
                    'end_time': current_time,
                })
                
                for task in finished_batch:
                    qa_result = self._run_qa_check(m, recipe_used, task, current_time)
                    
                    if qa_result['passed']:
                        succeeded_tasks.append(task)
                        task.location = 'QUEUE_C'
                        task.realized_qa_B = qa_result['realized_qa']
                        self.stats['total_passed'] += 1
                        print(f"  t={current_time}: Task {task.uid:3d} 세정 성공 [PASS] (qa={qa_result['realized_qa']:.2f})")
                    else:
                        rework_tasks.append(task)
                        task.location = 'REWORK_B'
                        task.rework_count += 1
                        self.rework_pool.append(task)
                        self.stats['total_reworked'] += 1
                        print(f"  t={current_time}: Task {task.uid:3d} 재세정 필요 [FAIL] (qa={qa_result['realized_qa']:.2f})")
                    
                    task.history.append({
                        'time': current_time,
                        'process': 'B',
                        'realized_qa': qa_result['realized_qa'],
                        'passed': qa_result['passed'],
                        'recipe': recipe_used,
                        'rework_count': task.rework_count,
                    })
                
                self.stats['total_processed'] += len(finished_batch)
                
                if m.v >= 20:
                    m.replace_solution()
                    solution_replacements_this_step += 1
                    self.stats['solution_replacements'] += 1
                    print(f"  t={current_time}: Machine B_{m.id} 용액 교체")
        
        # 2단계: 새로운 Task 할당
        idle_machines = [m for m in self.machines.values() if m.status == 'idle']
        
        for m in idle_machines:
            queue_info = {
                'wait_pool_size': len(self.wait_pool),
                'rework_queue_size': len(self.rework_pool),
            }
            batch, task_type = self.scheduler.select_batch(self.wait_pool, self.rework_pool, m.batch_size)
            
            if batch is None or len(batch) == 0:
                continue
            
            # 배치의 첫 번째 task의 레시피로 배치 전체 처리
            recipe = self.scheduler.get_recipe(batch[0], m, queue_info)
            
            finish_time = current_time + self.process_time
            m.start_processing(batch, finish_time, recipe)
            
            # 이벤트: task 할당
            task_uids = [t.uid for t in batch]
            self.event_log.append({
                'timestamp': current_time,
                'event_type': 'task_assigned',
                'process': 'B',
                'machine_id': m.id,
                'task_uids': task_uids,
                'start_time': current_time,
                'end_time': finish_time,
                'task_type': task_type,
            })
            
            batch_str = ", ".join([str(t.uid) for t in batch])
            print(f"  t={current_time}: Tasks [{batch_str}] B_{m.id}에서 배치 처리 시작 ({task_type}), 레시피={[f'{r:.0f}' for r in recipe]}")
        
        # 3단계: 통계 업데이트
        if self.stats['total_processed'] > 0:
            self.stats['first_pass_rate'] = self.stats['total_passed'] / self.stats['total_processed']
            
            total_rework_count = sum(t.rework_count for t in succeeded_tasks + rework_tasks)
            total_count = len(succeeded_tasks) + len(rework_tasks)
            if total_count > 0:
                self.stats['avg_rework_count'] = total_rework_count / total_count
        
        return {
            'succeeded': succeeded_tasks,
            'rework': rework_tasks,
            'completed_this_step': len(succeeded_tasks),
            'rework_count_this_step': len(rework_tasks),
            'solution_replacements': solution_replacements_this_step,
        }

    def get_state(self) -> Dict[str, Any]:
        """현재 상태 보고"""
        return {
            'wait_pool_size': len(self.wait_pool),
            'rework_pool_size': len(self.rework_pool),
            'idle_machines': sum(1 for m in self.machines.values() if m.status == 'idle'),
            'busy_machines': sum(1 for m in self.machines.values() if m.status == 'busy'),
            'first_pass_rate': self.stats['first_pass_rate'],
            'total_passed': self.stats['total_passed'],
            'total_reworked': self.stats['total_reworked'],
        }
