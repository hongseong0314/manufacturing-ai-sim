# -*- coding: utf-8 -*-
"""
A공정 스케줄러 모듈
가공 레시피 결정 알고리즘들
"""

from typing import List, Dict, Any, Tuple, Optional
from src.objects import Task, ProcessA_Machine


class BaseScheduler:
    """스케줄러 기본 인터페이스"""
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.process_time = config.get('process_time_A', 15)

    def should_schedule(self) -> bool:
        """스케줄링 가능 여부"""
        raise NotImplementedError

    def get_recipe(self, task: Task, machine: ProcessA_Machine, queue_info: Dict) -> List[float]:
        """레시피 결정"""
        raise NotImplementedError

    def select_task(self, wait_pool: List[Task], rework_pool: List[Task]) -> Optional[Tuple[Task, str]]:
        """처리할 Task 선택 (우선순위: rework > wait)"""
        raise NotImplementedError

    def select_batch(self, wait_pool: List[Task], rework_pool: List[Task], batch_size: int) -> Optional[Tuple[List[Task], str]]:
        """배치 크기만큼 Task들을 선택 (우선순위: rework > wait)"""
        raise NotImplementedError


class FIFOScheduler(BaseScheduler):
    """
    FIFO Scheduler for A Process
    모든 Task에 기본 레시피 [10, 2, 1] 적용
    우선순위: rework > wait
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.default_recipe = config.get('default_recipe_A', [10.0, 2.0, 1.0])

    def should_schedule(self) -> bool:
        return True

    def get_recipe(self, task: Task, machine: ProcessA_Machine, queue_info: Dict) -> List[float]:
        """항상 기본 레시피 반환"""
        return self.default_recipe

    def select_task(self, wait_pool: List[Task], rework_pool: List[Task]) -> Optional[Tuple[Task, str]]:
        """우선순위: rework > wait (FIFO)"""
        if rework_pool:
            return rework_pool.pop(0), 'rework'
        elif wait_pool:
            return wait_pool.pop(0), 'new'
        return None, None

    def select_batch(self, wait_pool: List[Task], rework_pool: List[Task], batch_size: int) -> Optional[Tuple[List[Task], str]]:
        """배치 크기만큼 Task 선택: rework 우선, 나머지는 wait_pool에서 채우기"""
        batch = []
        task_type = None
        
        # 1단계: rework_pool에서 최대한 선택
        while len(batch) < batch_size and rework_pool:
            batch.append(rework_pool.pop(0))
            task_type = 'rework'
        
        # 2단계: 나머지를 wait_pool에서 선택
        while len(batch) < batch_size and wait_pool:
            batch.append(wait_pool.pop(0))
            if task_type is None:
                task_type = 'new'
        
        # 배치가 비어있으면 None 반환
        if not batch:
            return None, None
        
        return batch, task_type


class AdaptiveScheduler(BaseScheduler):
    """
    Adaptive Scheduler for A Process
    장비 부자재 마모도(u)에 따라 레시피 동적 조정
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # 부자재 상태 임계값
        self.u_fresh = 3
        self.u_medium = 7
        self.u_old = 10
        
        # 상태별 기본 레시피
        self.recipe_library = {
            'fresh': [10.0, 2.0, 1.0],
            'medium': [12.0, 2.5, 1.2],
            'old': [15.0, 3.0, 1.5],
        }

    def should_schedule(self) -> bool:
        return True

    def _get_consumable_state(self, u: float) -> str:
        """부자재 상태 분류"""
        if u <= self.u_fresh:
            return 'fresh'
        elif u <= self.u_medium:
            return 'medium'
        else:
            return 'old'

    def get_recipe(self, task: Task, machine: ProcessA_Machine, queue_info: Dict) -> List[float]:
        """부자재 상태에 따라 레시피 결정"""
        consumable_state = self._get_consumable_state(machine.u)
        return self.recipe_library.get(consumable_state, [10.0, 2.0, 1.0])

    def select_task(self, wait_pool: List[Task], rework_pool: List[Task]) -> Optional[Tuple[Task, str]]:
        """우선순위: rework > wait (FIFO)"""
        if rework_pool:
            return rework_pool.pop(0), 'rework'
        elif wait_pool:
            return wait_pool.pop(0), 'new'
        return None, None

    def select_batch(self, wait_pool: List[Task], rework_pool: List[Task], batch_size: int) -> Optional[Tuple[List[Task], str]]:
        """배치 크기만큼 Task 선택: rework 우선, 나머지는 wait_pool에서 채우기"""
        batch = []
        task_type = None
        
        # 1단계: rework_pool에서 최대한 선택
        while len(batch) < batch_size and rework_pool:
            batch.append(rework_pool.pop(0))
            task_type = 'rework'
        
        # 2단계: 나머지를 wait_pool에서 선택
        while len(batch) < batch_size and wait_pool:
            batch.append(wait_pool.pop(0))
            if task_type is None:
                task_type = 'new'
        
        # 배치가 비어있으면 None 반환
        if not batch:
            return None, None
        
        return batch, task_type


class RLBasedScheduler(BaseScheduler):
    """
    RL-Based Scheduler for A Process
    (Placeholder) 향후 DQN/PPO 기반 스케줄러로 구현
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.default_recipe = config.get('default_recipe_A', [10.0, 2.0, 1.0])

    def should_schedule(self) -> bool:
        return True

    def get_recipe(self, task: Task, machine: ProcessA_Machine, queue_info: Dict) -> List[float]:
        """현재는 기본 레시피 반환 (향후 구현)"""
        return self.default_recipe

    def select_task(self, wait_pool: List[Task], rework_pool: List[Task]) -> Optional[Tuple[Task, str]]:
        """우선순위: rework > wait (FIFO)"""
        if rework_pool:
            return rework_pool.pop(0), 'rework'
        elif wait_pool:
            return wait_pool.pop(0), 'new'
        return None, None

    def select_batch(self, wait_pool: List[Task], rework_pool: List[Task], batch_size: int) -> Optional[Tuple[List[Task], str]]:
        """배치 크기만큼 Task 선택: rework 우선, 나머지는 wait_pool에서 채우기"""
        batch = []
        task_type = None
        
        # 1단계: rework_pool에서 최대한 선택
        while len(batch) < batch_size and rework_pool:
            batch.append(rework_pool.pop(0))
            task_type = 'rework'
        
        # 2단계: 나머지를 wait_pool에서 선택
        while len(batch) < batch_size and wait_pool:
            batch.append(wait_pool.pop(0))
            if task_type is None:
                task_type = 'new'
        
        # 배치가 비어있으면 None 반환
        if not batch:
            return None, None
        
        return batch, task_type
