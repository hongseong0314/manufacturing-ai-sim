# -*- coding: utf-8 -*-
"""
B공정 스케줄러 모듈
세정 레시피 결정 알고리즘들
"""

from typing import List, Dict, Any, Tuple, Optional
from src.objects import Task, ProcessB_Machine


class BaseScheduler:
    """스케줄러 기본 인터페이스"""
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.process_time = config.get('process_time_B', 4)

    def should_schedule(self) -> bool:
        """스케줄링 가능 여부"""
        raise NotImplementedError

    def get_recipe(self, task: Task, machine: ProcessB_Machine, queue_info: Dict) -> List[float]:
        """레시피 결정"""
        raise NotImplementedError

    def select_task(self, wait_pool: List[Task], rework_pool: List[Task]) -> Optional[Tuple[Task, str]]:
        """처리할 Task 선택 (우선순위: rework > wait)"""
        raise NotImplementedError

    def select_batch(self, wait_pool: List[Task], rework_pool: List[Task], batch_size: int) -> Optional[Tuple[List[Task], str]]:
        """배치 크기만큼 Task들을 선택 (우선순위: rework > wait)"""
        raise NotImplementedError


class FIFOBaseline(BaseScheduler):
    """
    FIFO Baseline Scheduler
    모든 Task에 동일한 기본 레시피 적용
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.default_recipe = config.get('default_recipe_B', [50.0, 50.0, 30.0])

    def should_schedule(self) -> bool:
        return True

    def get_recipe(self, task: Task, machine: ProcessB_Machine, queue_info: Dict) -> List[float]:
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


class RuleBasedScheduler(BaseScheduler):
    """
    Rule-Based Scheduler
    장비 상태(b_age)와 용액 신선도(v)에 따른 규칙 기반 레시피 선택
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # 상태 임계값
        self.v_fresh = 5
        self.v_medium = 15
        self.v_old = 20
        
        self.b_age_new = 10
        self.b_age_medium = 50
        self.b_age_old = 100
        
        # 규칙 기반 레시피 라이브러리
        self.recipe_library = {
            ('fresh', 'new'):        [40.0, 45.0, 25.0],
            ('fresh', 'medium'):     [50.0, 50.0, 30.0],
            ('fresh', 'old'):        [60.0, 55.0, 35.0],
            
            ('medium', 'new'):       [50.0, 50.0, 30.0],
            ('medium', 'medium'):    [55.0, 55.0, 35.0],
            ('medium', 'old'):       [65.0, 60.0, 40.0],
            
            ('old', 'new'):          [60.0, 55.0, 35.0],
            ('old', 'medium'):       [70.0, 65.0, 45.0],
            ('old', 'old'):          [80.0, 70.0, 50.0],
        }

    def should_schedule(self) -> bool:
        return True

    def _get_solution_state(self, v: float) -> str:
        """용액 상태 분류"""
        if v <= self.v_fresh:
            return 'fresh'
        elif v <= self.v_medium:
            return 'medium'
        else:
            return 'old'

    def _get_machine_state(self, b_age: int) -> str:
        """장비 상태 분류"""
        if b_age <= self.b_age_new:
            return 'new'
        elif b_age <= self.b_age_medium:
            return 'medium'
        else:
            return 'old'

    def get_recipe(self, task: Task, machine: ProcessB_Machine, queue_info: Dict) -> List[float]:
        """규칙 기반 레시피 결정"""
        # 1단계: 상태 분류
        solution_state = self._get_solution_state(machine.v)
        machine_state = self._get_machine_state(machine.b_age)
        
        # 2단계: 기본 레시피 선택
        key = (solution_state, machine_state)
        base_recipe = self.recipe_library.get(key, [50.0, 50.0, 30.0])
        
        # 3단계: Task 스펙에 따른 미세 조정
        recipe = self._adjust_by_spec(base_recipe, task.spec_b)
        
        return recipe

    def _adjust_by_spec(self, recipe: List[float], spec_b: Tuple[float, float]) -> List[float]:
        """Task 품질 요구에 따라 레시피 미조정"""
        min_b, max_b = spec_b
        mid_spec = (min_b + max_b) / 2.0
        
        if mid_spec > 60:
            adjustment = 1.1  # +10%
        elif mid_spec < 40:
            adjustment = 0.9  # -10%
        else:
            adjustment = 1.0  # 그대로
        
        return [r * adjustment for r in recipe]

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
    RL-Based Scheduler (향후 확장)
    현재는 Rule-Based로 fallback
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.fallback = RuleBasedScheduler(config)

    def should_schedule(self) -> bool:
        return True

    def get_recipe(self, task: Task, machine: ProcessB_Machine, queue_info: Dict) -> List[float]:
        """현재는 Rule-Based 사용"""
        return self.fallback.get_recipe(task, machine, queue_info)

    def select_task(self, wait_pool: List[Task], rework_pool: List[Task]) -> Optional[Tuple[Task, str]]:
        """현재는 Rule-Based 사용"""
        return self.fallback.select_task(wait_pool, rework_pool)

    def select_batch(self, wait_pool: List[Task], rework_pool: List[Task], batch_size: int) -> Optional[Tuple[List[Task], str]]:
        """현재는 Rule-Based 사용"""
        return self.fallback.select_batch(wait_pool, rework_pool, batch_size)
