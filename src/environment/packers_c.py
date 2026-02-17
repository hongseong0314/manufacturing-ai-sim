# -*- coding: utf-8 -*-
"""
C공정 팩커 모듈
제품 조합 선택 알고리즘들
"""

from typing import List, Dict, Any, Optional, Tuple
from itertools import combinations
import numpy as np

from src.objects import Task


class BasePacker:
    """팩커 기본 인터페이스"""
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        # batch_size_C를 최우선으로, 없으면 N_pack 사용
        self.batch_size = config.get('batch_size_C', config.get('N_pack', 4))
        self.N_pack = self.batch_size  # 호환성 유지
        self.max_wait_time = config.get('max_wait_time', 30)
        self.min_queue_size = config.get('min_queue_size', 8)

    def should_pack(
        self, 
        wait_pool: List[Task], 
        current_time: int, 
        last_pack_time: int
    ) -> Tuple[bool, str]:
        """팩킹 여부 결정"""
        raise NotImplementedError

    def select_pack(self, wait_pool: List[Task], current_time: int) -> Optional[List[Task]]:
        """배치 크기만큼 Task 선택"""
        raise NotImplementedError


class FIFOPacker(BasePacker):
    """
    FIFO Packer
    대기열의 앞에서부터 순서대로 batch_size개 선택
    """
    def should_pack(
        self, 
        wait_pool: List[Task], 
        current_time: int, 
        last_pack_time: int
    ) -> Tuple[bool, str]:
        """팩킹 조건"""
        if len(wait_pool) < self.min_queue_size:
            return False, "queue_too_small"
        
        if wait_pool:
            oldest_task = min(wait_pool, key=lambda t: getattr(t, 'arrival_time', 0))
            wait_duration = current_time - getattr(oldest_task, 'arrival_time', 0)
            if wait_duration > self.max_wait_time:
                return True, "timeout"
        
        if len(wait_pool) >= self.batch_size * 2:
            return True, "queue_large"
        
        return False, "waiting"

    def select_pack(self, wait_pool: List[Task], current_time: int) -> Optional[List[Task]]:
        """앞의 batch_size개 선택"""
        if len(wait_pool) < self.batch_size:
            return None
        
        pack = wait_pool[:self.batch_size]
        print(f"    [FIFO] Pack selected: {[t.uid for t in pack]}")
        return pack


class RandomPacker(BasePacker):
    """
    Random Packer
    대기열에서 무작위로 batch_size개 선택
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.random_seed = config.get('random_seed', None)

    def should_pack(
        self, 
        wait_pool: List[Task], 
        current_time: int, 
        last_pack_time: int
    ) -> Tuple[bool, str]:
        """FIFO와 동일"""
        if len(wait_pool) < self.min_queue_size:
            return False, "queue_too_small"
        
        if wait_pool:
            oldest_task = min(wait_pool, key=lambda t: getattr(t, 'arrival_time', 0))
            wait_duration = current_time - getattr(oldest_task, 'arrival_time', 0)
            if wait_duration > self.max_wait_time:
                return True, "timeout"
        
        if len(wait_pool) >= self.batch_size * 2:
            return True, "queue_large"
        
        return False, "waiting"

    def select_pack(self, wait_pool: List[Task], current_time: int) -> Optional[List[Task]]:
        """무작위로 batch_size개 선택"""
        if len(wait_pool) < self.batch_size:
            return None
        
        if self.random_seed is not None:
            np.random.seed(self.random_seed)
        
        indices = np.random.choice(len(wait_pool), self.batch_size, replace=False)
        pack = [wait_pool[i] for i in sorted(indices)]
        
        print(f"    [RANDOM] Pack selected: {[t.uid for t in pack]}")
        return pack


class GreedyScorePacker(BasePacker):
    """
    Greedy Score-Based Packer
    최고 점수 조합 선택 (상위 K개 후보에서)
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # 점수 가중치
        self.alpha_quality = config.get('alpha_quality', 1.0)
        self.beta_compat = config.get('beta_compat', 0.5)
        self.gamma_margin = config.get('gamma_margin', 0.3)
        self.delta_time = config.get('delta_time', 0.2)
        
        # 호환성 테이블
        self.compatibility_matrix = self._init_compatibility_matrix()
        
        # 후보 제한 (계산 효율)
        self.K_candidates = config.get('K_candidates', 15)
    
    def _init_compatibility_matrix(self) -> Dict[Tuple[str, str], float]:
        """호환성 정의"""
        return {
            # Material
            ('plastic', 'plastic'): 1.0,
            ('plastic', 'metal'): 0.5,
            ('plastic', 'composite'): 0.7,
            ('metal', 'metal'): 1.0,
            ('metal', 'plastic'): 0.5,
            ('metal', 'composite'): 0.8,
            ('composite', 'plastic'): 0.7,
            ('composite', 'metal'): 0.8,
            ('composite', 'composite'): 1.0,
            
            # Color
            ('red', 'red'): 1.0,
            ('red', 'blue'): 0.7,
            ('red', 'green'): 0.6,
            ('blue', 'red'): 0.7,
            ('blue', 'blue'): 1.0,
            ('blue', 'green'): 0.7,
            ('green', 'red'): 0.6,
            ('green', 'blue'): 0.7,
            ('green', 'green'): 1.0,
        }

    def should_pack(
        self, 
        wait_pool: List[Task], 
        current_time: int, 
        last_pack_time: int
    ) -> Tuple[bool, str]:
        """팩킹 조건"""
        if len(wait_pool) < self.min_queue_size:
            return False, "queue_too_small"
        
        if wait_pool:
            oldest_task = min(wait_pool, key=lambda t: getattr(t, 'arrival_time', 0))
            wait_duration = current_time - getattr(oldest_task, 'arrival_time', 0)
            if wait_duration > self.max_wait_time:
                return True, "timeout"
        
        if len(wait_pool) >= self.batch_size * 2:
            return True, "queue_large"
        
        return False, "waiting"

    def select_pack(self, wait_pool: List[Task], current_time: int) -> Optional[List[Task]]:
        """최고 점수 조합 선택"""
        if len(wait_pool) < self.batch_size:
            return None
        
        # 상위 K개 후보 선택
        K = min(self.K_candidates, len(wait_pool))
        candidates = sorted(
            wait_pool,
            key=lambda t: getattr(t, 'realized_qa_B', 50),
            reverse=True
        )[:K]
        
        # 모든 조합 점수 계산
        best_score = -float('inf')
        best_combo = None
        
        for combo in combinations(candidates, self.batch_size):
            score = self._compute_score(list(combo), current_time)
            if score > best_score:
                best_score = score
                best_combo = list(combo)
        
        if best_combo:
            print(f"    [GREEDY] Pack selected: {[t.uid for t in best_combo]}, score={best_score:.2f}")
            return best_combo
        
        return None

    def _compute_score(self, tasks: List[Task], current_time: int) -> float:
        """팩 점수 계산"""
        # 품질
        quality_score = np.mean([
            getattr(t, 'realized_qa_B', 50) for t in tasks
        ])
        
        # 호환성
        compat_score = self._compute_compatibility(tasks)
        
        # 마진
        margin_score = np.mean([
            getattr(t, 'margin_value', 0.5) for t in tasks
        ]) * 100
        
        # 시간 페널티
        time_penalty = self._compute_time_penalty(tasks, current_time)
        
        # 최종 점수
        score = (
            self.alpha_quality * quality_score
            + self.beta_compat * compat_score * 100
            + self.gamma_margin * margin_score
            - self.delta_time * time_penalty
        )
        
        return score

    def _compute_compatibility(self, tasks: List[Task]) -> float:
        """호환성 점수"""
        if len(tasks) < 2:
            return 1.0
        
        compat_product = 1.0
        for i, task_i in enumerate(tasks):
            for task_j in tasks[i+1:]:
                compat = self._get_pairwise_compat(task_i, task_j)
                compat_product *= compat
        
        n_pairs = len(tasks) * (len(tasks) - 1) / 2
        if n_pairs > 0:
            return compat_product ** (1 / n_pairs)
        else:
            return 1.0

    def _get_pairwise_compat(self, task_i: Task, task_j: Task) -> float:
        """두 Task 호환성"""
        # Material
        mat_i = getattr(task_i, 'material_type', 'plastic')
        mat_j = getattr(task_j, 'material_type', 'plastic')
        key_mat = (mat_i, mat_j) if (mat_i, mat_j) in self.compatibility_matrix else (mat_j, mat_i)
        mat_compat = self.compatibility_matrix.get(key_mat, 0.7)
        
        # Color
        color_i = getattr(task_i, 'color', 'red')
        color_j = getattr(task_j, 'color', 'red')
        key_color = (color_i, color_j) if (color_i, color_j) in self.compatibility_matrix else (color_j, color_i)
        color_compat = self.compatibility_matrix.get(key_color, 0.7)
        
        return (mat_compat + color_compat) / 2

    def _compute_time_penalty(self, tasks: List[Task], current_time: int) -> float:
        """시간 페널티"""
        max_due = max([getattr(t, 'due_date', current_time + 100) for t in tasks])
        return max(0, current_time - max_due)
