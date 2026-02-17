# -*- coding: utf-8 -*-
"""
C공정 환경 (팩킹 공정)
여러 제품 Task를 조합하여 최종 패키지를 구성합니다.
"""

from typing import List, Dict, Any, Optional
import numpy as np

from src.objects import Task, ProcessC_Machine
from src.environment.packers_c import FIFOPacker, RandomPacker, GreedyScorePacker


class ProcessC_Env:
    """
    C공정 환경 클래스
    팩킹 공정을 시뮬레이션합니다. (실제 처리 시간 소비 없음)
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.num_machines = config.get('num_machines_C', 1)  # 팩킹은 시간 소비 안 함
        self.batch_size_C = config.get('batch_size_C', 4)  # C공정 배치 크기 (팩 크기)
        self.machines: Dict[int, ProcessC_Machine] = {
            i: ProcessC_Machine(i, batch_size=self.batch_size_C) for i in range(self.num_machines)
        }
        
        # 대기열
        self.wait_pool: List[Task] = []
        self.completed_tasks: List[Task] = []
        
        # 팩킹 파라미터
        self.N_pack = self.batch_size_C  # 팩 크기는 batch_size_C와 동일
        self.max_wait_time = config.get('max_wait_time', 30)
        self.min_queue_size = config.get('min_queue_size', 8)
        
        # 팩커 선택
        packing_strategy = config.get('packing_C', 'greedy')
        if packing_strategy == 'fifo':
            self.packer = FIFOPacker(config)
        elif packing_strategy == 'random':
            self.packer = RandomPacker(config)
        elif packing_strategy == 'greedy':
            self.packer = GreedyScorePacker(config)
        else:
            self.packer = GreedyScorePacker(config)
        
        self.last_pack_time = 0
        self.pack_count = 0
        
        self.deterministic = config.get('deterministic_mode', False)
        
        # 통계
        self.stats = {
            'total_packs': 0,
            'total_tasks_packed': 0,
            'avg_quality': 0.0,
            'avg_compat': 0.0,
            'avg_wait_time': 0.0,
        }
        
        # 이벤트 로그 (Gantt chart 생성용)
        self.event_log: List[Dict[str, Any]] = []

    def reset(self):
        """환경 초기화"""
        self.machines = {
            i: ProcessC_Machine(i, batch_size=self.batch_size_C) for i in range(self.num_machines)
        }
        self.wait_pool = []
        self.completed_tasks = []
        self.pack_count = 0
        self.last_pack_time = 0
        self.event_log = []
        
        self.stats = {
            'total_packs': 0,
            'total_tasks_packed': 0,
            'avg_quality': 0.0,
            'avg_compat': 0.0,
            'avg_wait_time': 0.0,
        }

    def add_tasks(self, tasks: List[Task]):
        """B공정에서 넘어온 Task들을 대기열에 추가"""
        for task in tasks:
            task.location = 'QUEUE_C'
            task.arrival_time = getattr(task, 'arrival_time', 0)
        self.wait_pool.extend(tasks)

    def step(self, current_time: int, actions: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        C공정 1 time step 진행 (팩킹 의사결정)
        
        Returns:
            {
                'completed': [...],         # 완료된 팩의 Task들
                'pack_count': int,
                'queue_size': int
            }
        """
        completed_packs = []
        
        # 1단계: 팩킹 여부 결정
        should_pack, reason = self.packer.should_pack(
            self.wait_pool,
            current_time,
            self.last_pack_time
        )
        
        if should_pack:
            print(f"\n  t={current_time}: 팩킹 시작 (사유: {reason})")
            
            # 2단계: 팩 선택
            pack = self.packer.select_pack(self.wait_pool, current_time)
            
            if pack:
                # 3단계: 대기열에서 제거
                for task in pack:
                    self.wait_pool.remove(task)
                
                # 4단계: 팩 정보 생성
                pack_info = self._create_pack_info(pack, current_time)
                
                # 5단계: Task 상태 업데이트
                for task in pack:
                    task.location = 'COMPLETED'
                    task.pack_id = self.pack_count
                    task.history.append({
                        'time': current_time,
                        'process': 'C',
                        'status': 'PACKED',
                        'pack_id': self.pack_count,
                        'pack_quality': pack_info['avg_quality'],
                        'pack_compat': pack_info['avg_compat'],
                        'wait_time': current_time - getattr(task, 'arrival_time', 0),
                    })
                
                completed_packs.extend(pack)
                self.completed_tasks.extend(pack)
                
                # 이벤트: 팩 완료
                task_uids = [t.uid for t in pack]
                self.event_log.append({
                    'timestamp': current_time,
                    'event_type': 'pack_completed',
                    'process': 'C',
                    'machine_id': 'C_0',  # C공정은 머신이 1개 (팩킹)
                    'task_uids': task_uids,
                    'pack_id': self.pack_count,
                    'start_time': current_time,
                    'end_time': current_time,  # C공정은 시간 소비 없음
                })
                
                self.pack_count += 1
                self.last_pack_time = current_time
                
                print(f"    [OK] Pack #{self.pack_count-1} completed!")
                print(f"       - Avg Quality: {pack_info['avg_quality']:.2f}")
                print(f"       - Compatibility: {pack_info['avg_compat']:.2f}")
                print(f"       - Tasks: {[t.uid for t in pack]}")
                
                # 6단계: 통계 업데이트
                self._update_stats(pack_info)
        
        # 7단계: 대기열 상태
        if self.wait_pool:
            oldest_arrival = min(
                [getattr(t, 'arrival_time', 0) for t in self.wait_pool],
                default=current_time
            )
            max_wait = current_time - oldest_arrival
            print(f"    [Queue] 대기 중: {len(self.wait_pool)}개, 최대 대기: {max_wait}분")
        
        return {
            'completed': completed_packs,
            'pack_count': self.pack_count,
            'queue_size': len(self.wait_pool),
        }

    def _create_pack_info(self, pack: List[Task], current_time: int) -> Dict[str, Any]:
        """팩 정보 생성"""
        avg_quality = np.mean([
            getattr(t, 'realized_qa_B', 50) for t in pack
        ])
        
        if hasattr(self.packer, '_compute_compatibility'):
            compat = self.packer._compute_compatibility(pack)
        else:
            compat = 1.0
        
        wait_times = [
            current_time - getattr(t, 'arrival_time', current_time) for t in pack
        ]
        avg_wait = np.mean(wait_times) if wait_times else 0
        
        return {
            'pack_id': self.pack_count,
            'avg_quality': avg_quality,
            'avg_compat': compat,
            'avg_wait_time': avg_wait,
            'task_count': len(pack),
        }

    def _update_stats(self, pack_info: Dict[str, Any]):
        """통계 업데이트"""
        n = self.stats['total_packs']
        self.stats['total_packs'] += 1
        self.stats['total_tasks_packed'] += pack_info['task_count']
        
        self.stats['avg_quality'] = (
            (self.stats['avg_quality'] * n + pack_info['avg_quality'])
            / (n + 1)
        )
        
        self.stats['avg_compat'] = (
            (self.stats['avg_compat'] * n + pack_info['avg_compat'])
            / (n + 1)
        )
        
        self.stats['avg_wait_time'] = (
            (self.stats['avg_wait_time'] * n + pack_info['avg_wait_time'])
            / (n + 1)
        )

    def get_state(self) -> Dict[str, Any]:
        """현재 상태 보고"""
        return {
            'queue_size': len(self.wait_pool),
            'completed_packs': self.pack_count,
            'total_tasks_packed': self.stats['total_tasks_packed'],
            'avg_quality': self.stats['avg_quality'],
            'avg_compat': self.stats['avg_compat'],
            'avg_wait_time': self.stats['avg_wait_time'],
        }
