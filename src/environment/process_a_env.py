# -*- coding: utf-8 -*-
from typing import List, Dict, Any, Tuple
import numpy as np

from src.objects import Task, ProcessA_Machine
from src.environment.schedulers_a import FIFOScheduler, AdaptiveScheduler, RLBasedScheduler

# 물리 모델 파라미터 (v9 효율성 드래그 감소)
# 목표: Task 스펙(약 47~53) 범위에서 QA 통과
# recipe [10, 2, 1] 기준으로 약 51 출력
# 주요 변경: BETA = 0.2 (효율성이 너무 빠르게 떨어지는 것을 방지)
W1_BASE, W2_BASE, W3_BASE, B_BASE = 0.5, 0.3, 0.2, 45.0
W12_BASE = 0.01
BETA, BETA_K = 0.2, 0.1  # BETA 0.8 → 0.2로 감소
GAMMA, GAMMA_K = 1.5, 0.1
DELTA_W1, DELTA_W12, DELTA_B = 0.001, 0.0001, 0.02

class ProcessA_Env:
    """A공정만을 담당하는 독립적인 시뮬레이션 환경."""

    def __init__(self, config: Dict[str, Any]):
        self.num_machines = config.get('num_machines_A', 10)
        self.process_time = config.get('process_time_A', 15)
        self.batch_size_A = config.get('batch_size_A', 1)  # A공정 배치 크기
        self.machines = {i: ProcessA_Machine(i, batch_size=self.batch_size_A) for i in range(self.num_machines)}
        
        # A공정 내의 Task 위치
        self.wait_pool: List[Task] = []
        self.rework_pool: List[Task] = []
        
        # 스케줄러 선택
        scheduler_type = config.get('scheduler_A', 'fifo')
        if scheduler_type == 'fifo':
            self.scheduler = FIFOScheduler(config)
        elif scheduler_type == 'adaptive':
            self.scheduler = AdaptiveScheduler(config)
        elif scheduler_type == 'rl':
            self.scheduler = RLBasedScheduler(config)
        else:
            self.scheduler = FIFOScheduler(config)
        
        # Deterministic mode (노이즈 비활성화)
        self.deterministic = config.get('deterministic_mode', False)
        
        # 통계
        self.stats = {
            'total_processed': 0,
            'total_passed': 0,
            'total_reworked': 0,
            'first_pass_rate': 0.0,
            'avg_rework_count': 0.0,
        }
        
        # 이벤트 로그 (Gantt chart 생성용)
        self.event_log: List[Dict[str, Any]] = []

    def _get_physical_model_params(self, m_age: int) -> Tuple:
        w1 = W1_BASE * (1 - DELTA_W1 * m_age)
        w12 = W12_BASE * (1 - DELTA_W12 * m_age)
        b = B_BASE - DELTA_B * m_age
        return w1, w12, b

    def _run_qa_check(self, machine: ProcessA_Machine, recipe: List[float], task: Task, current_time: int) -> bool:
        """주어진 레시피로 Task를 처리하고 품질을 검사합니다."""
        s1, s2, s3 = recipe
        w1, w12, b = self._get_physical_model_params(machine.m_age)
        
        # 디버그 로깅: 파라미터 확인
        # print(f"    [DEBUG] recipe={recipe}, m_age={machine.m_age}, w1={w1:.4f}, w12={w12:.5f}, b={b:.2f}, u={machine.u}")
        
        g_s = (w1 * s1 + W2_BASE * s2 + W3_BASE * s3 + b) + (w12 * s1 * s2)
        effectiveness = 1 - BETA * np.tanh(BETA_K * machine.u)
        mean_qa = g_s * effectiveness
        std_dev_noise = GAMMA * np.tanh(GAMMA_K * machine.u)
        
        # Deterministic 모드: 노이즈 비활성화
        if self.deterministic:
            realized_qa = mean_qa
        else:
            realized_qa = np.random.normal(mean_qa, std_dev_noise)
        
        # QA 체크 결과 로깅
        passed = task.spec_a[0] <= realized_qa <= task.spec_a[1]
        status = "PASS" if passed else "FAIL"
        print(f"  QA {status}: Task {task.uid:3d}, realized_qa={realized_qa:.2f}, spec=({task.spec_a[0]:.1f}, {task.spec_a[1]:.1f}), g_s={g_s:.2f}")
        
        task.history.append({'time': current_time, 'process': 'A', 'qa': realized_qa})

        return passed

    def reset(self):
        """환경을 초기화합니다."""
        self.machines = {i: ProcessA_Machine(i, batch_size=self.batch_size_A) for i in range(self.num_machines)}
        self.wait_pool = []
        self.rework_pool = []
        self.event_log = []
        self.stats = {
            'total_processed': 0,
            'total_passed': 0,
            'total_reworked': 0,
            'first_pass_rate': 0.0,
            'avg_rework_count': 0.0,
        }

    def step(self, current_time: int, actions: Dict[str, Any] = None) -> Dict[str, List[Task]]:
        """
        A공정의 1 time step을 진행합니다.
        자동 FIFO 스케줄링 적용.
        
        Args:
            current_time (int): 현재 시뮬레이션 시간.
            actions (Dict): (선택사항) 외부 action 입력
              
        Returns:
            Dict: {'succeeded': [...], 'rework': [...]}
        """
        succeeded_tasks = []
        actions = actions or {}

        # 1. 작업 완료된 장비 처리
        for m in self.machines.values():
            if m.status == 'busy' and current_time >= m.finish_time:
                # 실제 사용된 레시피는 finish_processing 전에 저장 (finish_processing에서 current_recipe가 초기화됨)
                recipe_used = m.current_recipe if m.current_recipe else [10, 2, 1]  # 기본 레시피
                finished_batch = m.finish_processing()
                
                # 이벤트: task 완료
                task_uids = [t.uid for t in finished_batch]
                self.event_log.append({
                    'timestamp': current_time,
                    'event_type': 'task_completed',
                    'process': 'A',
                    'machine_id': m.id,
                    'task_uids': task_uids,
                    'end_time': current_time,
                })
                
                for task in finished_batch:
                    if self._run_qa_check(m, recipe_used, task, current_time):
                        succeeded_tasks.append(task)
                        self.stats['total_passed'] += 1
                    else:
                        # 재작업 필요: rework_pool에 추가
                        task.location = 'REWORK_A'
                        task.rework_count += 1
                        task.history.append({'time': current_time, 'process': 'A', 'status': 'Rework'})
                        self.rework_pool.append(task)
                        self.stats['total_reworked'] += 1
                
                self.stats['total_processed'] += len(finished_batch)
                
                # 부자재 마모도에 따라 주기적으로 교체
                if m.u >= 10:
                    m.replace_consumable()
        
        # 2. Idle 장비에 Task 할당 (스케줄러 사용, 배치 처리)
        for m in self.machines.values():
            if m.status == 'idle':
                queue_info = {
                    'wait_pool_size': len(self.wait_pool),
                    'rework_pool_size': len(self.rework_pool),
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
                    'process': 'A',
                    'machine_id': m.id,
                    'task_uids': task_uids,
                    'start_time': current_time,
                    'end_time': finish_time,
                    'task_type': task_type,
                })
                
                batch_str = ", ".join([str(t.uid) for t in batch])
                print(f"  t={current_time}: Tasks [{batch_str}] A_{m.id}에서 배치 처리 시작 ({task_type}), 레시피={recipe}")
        
        # 3. 외부 action이 있으면 적용 (위의 자동 스케줄링을 override)
        if actions:
            tasks_to_remove = []
            allocated_uids = set()  # 이미 할당된 task uid 추적
            
            for machine_id_str, assignment in actions.items():
                if not assignment: continue
                
                try:
                    machine_id = int(machine_id_str.split('_')[1])
                    machine = self.machines[machine_id]
                except (ValueError, KeyError):
                    continue

                if machine.status == 'idle':
                    task_uids = assignment.get('task_uids', [])
                    recipe = assignment.get('recipe', [10, 2, 1])
                    
                    # rework_pool을 먼저 확인
                    batch = []
                    for uid in task_uids:
                        # 이미 할당된 uid는 무시
                        if uid in allocated_uids:
                            continue
                        
                        # rework_pool에서 찾기
                        rework_task = next((t for t in self.rework_pool if t.uid == uid), None)
                        if rework_task:
                            batch.append(rework_task)
                            tasks_to_remove.append(('rework', rework_task))
                            allocated_uids.add(uid)
                        else:
                            # wait_pool에서 찾기
                            wait_task = next((t for t in self.wait_pool if t.uid == uid), None)
                            if wait_task:
                                batch.append(wait_task)
                                tasks_to_remove.append(('wait', wait_task))
                                allocated_uids.add(uid)
                    
                    if len(batch) == len(task_uids):
                        finish_time = current_time + self.process_time
                        machine.start_processing(batch, finish_time, recipe)
                    # Task를 찾지 못한 경우는 무시 (이미 처리됨)
            
            # 할당된 Task 제거
            for pool_type, task in tasks_to_remove:
                try:
                    if pool_type == 'rework':
                        self.rework_pool.remove(task)
                    else:
                        self.wait_pool.remove(task)
                except ValueError:
                    # 이미 제거된 경우 무시
                    pass

        return {"succeeded": succeeded_tasks, "rework": self.rework_pool}

    def add_tasks(self, tasks: List[Task]):
        """외부(최상위 Env)에서 새로운 Task들을 받아 대기열에 추가합니다."""
        self.wait_pool.extend(tasks)

    def get_state(self) -> Dict[str, Any]:
        """최상위 Env 또는 스케줄러에게 현재 상태를 보고합니다."""
        # First pass rate 계산
        if self.stats['total_processed'] > 0:
            self.stats['first_pass_rate'] = self.stats['total_passed'] / self.stats['total_processed']
        else:
            self.stats['first_pass_rate'] = 0.0
        
        # Average rework count (재작업이 발생한 Task의 평균 재작업 횟수)
        total_rework_count = self.stats['total_reworked']
        if self.stats['total_processed'] > 0:
            self.stats['avg_rework_count'] = total_rework_count / self.stats['total_processed']
        else:
            self.stats['avg_rework_count'] = 0.0
        
        return {
            "wait_pool_size": len(self.wait_pool),
            "rework_pool_size": len(self.rework_pool),
            "total_processed": self.stats['total_processed'],
            "total_passed": self.stats['total_passed'],
            "total_reworked": self.stats['total_reworked'],
            "first_pass_rate": self.stats['first_pass_rate'],
            "avg_rework_count": self.stats['avg_rework_count'],
        }
