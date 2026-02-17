# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any

@dataclass
class Task:
    """
    시뮬레이션 내에서 처리되는 작업(Task) 단위를 나타내는 데이터 클래스.
    하나의 'Job'은 동일한 특성을 가진 여러 개의 Task로 구성됩니다.
    """
    uid: int  # 시스템 전체에서 고유한 ID
    job_id: str  # 동일한 배치에서 생성된 Task들이 공유하는 ID
    due_date: int
    spec_a: Tuple[float, float]
    spec_b: Tuple[float, float] = (20.0, 80.0)  # B공정 품질 사양
    
    # Task의 현재 상태
    location: str = 'QUEUE_A' # e.g., QUEUE_A, PROC_A_1, QUEUE_B, REWORK_B, QUEUE_C, COMPLETED, ...
    
    # A공정 결과
    realized_qa_A: float = -1.0  # A공정 최종 품질 (-1: 미처리)
    
    # B공정 결과
    realized_qa_B: float = -1.0  # B공정 최종 품질 (-1: 미처리)
    
    # C공정 팩킹 정보
    material_type: str = 'plastic'  # 'plastic', 'metal', 'composite'
    color: str = 'red'              # 'red', 'blue', 'green'
    customer_id: str = 'UNKNOWN'    # 고객사 ID
    margin_value: float = 0.5       # 수익성 스코어 (0~1)
    
    # 팩킹 관련
    arrival_time: int = 0           # QUEUE_C 도착 시간
    pack_id: int = -1               # 팩 ID (-1: 미할당)
    rework_count: int = 0           # 재작업 횟수 (A, B 공정)
    
    # 이력 관리
    history: List[Dict[str, Any]] = field(default_factory=list)

class BaseMachine:
    """모든 공정 장비의 기본이 되는 추상 클래스."""
    def __init__(self, machine_id: int, batch_size: int = 1):
        self.id = machine_id
        self.batch_size = batch_size  # 최대 배치 크기
        self.status: str = 'idle'  # 'idle' or 'busy'
        self.current_batch: List[Task] = []
        self.finish_time: int = -1

    def start_processing(self, batch: List[Task], finish_time: int):
        """장비가 배치를 받아 작업을 시작하도록 상태를 변경합니다."""
        if self.status != 'idle':
            raise Exception(f"Machine {self.id} is not idle, but tried to start a new process.")
        if len(batch) > self.batch_size:
            raise Exception(f"Machine {self.id} batch size ({len(batch)}) exceeds max batch size ({self.batch_size}).")
        self.status = 'busy'
        self.current_batch = batch
        self.finish_time = finish_time
        # 각 Task의 위치 정보 업데이트
        for task in batch:
            task.location = f'PROC_{self.id}'

    def finish_processing(self) -> List[Task]:
        """작업 완료 후 장비 상태를 초기화하고, 처리된 배치를 반환합니다."""
        if self.status != 'busy':
            raise Exception(f"Machine {self.id} is not busy, but tried to finish a process.")
        self.status = 'idle'
        self.finish_time = -1
        finished_batch = self.current_batch
        self.current_batch = []
        self.current_recipe = []
        return finished_batch

class ProcessA_Machine(BaseMachine):
    """A공정 장비의 특성을 정의합니다 (경시성 포함)."""
    def __init__(self, machine_id: int, batch_size: int = 1, initial_m_age: int = 0):
        super().__init__(f"A_{machine_id}", batch_size=batch_size)
        self.m_age = initial_m_age  # 장비 총 누적 사용량 (초기화 불가)
        self.u = 0                  # 현재 부자재 누적 사용량
        self.current_recipe: List[float] = []  # 현재 처리 중인 레시피

    def start_processing(self, batch: List[Task], finish_time: int, recipe: List[float] = None):
        """작업 시작 시, 장비 및 부자재의 나이를 증가시킵니다."""
        super().start_processing(batch, finish_time)
        self.m_age += 1
        self.u += 1
        self.current_recipe = recipe if recipe is not None else []

    def replace_consumable(self):
        """부자재를 교체하여 u값을 초기화합니다."""
        self.u = 0

class ProcessB_Machine(BaseMachine):
    """B공정 장비 (세정 공정)."""
    def __init__(self, machine_id: int, batch_size: int = 1, initial_b_age: int = 0):
        super().__init__(f"B_{machine_id}", batch_size=batch_size)
        self.b_age = initial_b_age  # 장비 총 누적 사용량
        self.v = 0                  # 현재 용액 누적 사용량
        self.current_recipe: List[float] = []  # 현재 처리 중인 레시피

    def start_processing(self, batch: List[Task], finish_time: int, recipe: List[float] = None):
        """작업 시작 시, 장비 및 용액의 나이를 증가시킵니다."""
        if self.status != 'idle':
            raise Exception(f"Machine {self.id} is not idle.")
        if len(batch) > self.batch_size:
            raise Exception(f"Machine {self.id} batch size ({len(batch)}) exceeds max batch size ({self.batch_size}).")
        self.status = 'busy'
        self.current_batch = batch
        self.finish_time = finish_time
        self.b_age += 1
        self.v += 1
        self.current_recipe = recipe if recipe is not None else []
        
        for task in batch:
            task.location = f'PROC_{self.id}'

    def replace_solution(self):
        """용액을 교체하여 v값을 초기화합니다."""
        self.v = 0

class ProcessC_Machine(BaseMachine):
    """C공정 장비 (현재는 Dummy)."""
    def __init__(self, machine_id: int, batch_size: int = 1):
        super().__init__(f"C_{machine_id}", batch_size=batch_size)

if __name__ == '__main__':
    # 클래스 사용 예시
    task1 = Task(uid=1, job_id="JOB001", due_date=100, spec_a=(45.0, 55.0))
    machine_a1 = ProcessA_Machine(machine_id=1)
    
    print("초기 상태:")
    print(task1)
    print(machine_a1.__dict__)
    
    # 작업 시작
    machine_a1.start_processing(batch=[task1], finish_time=15)
    print("작업 시작 후:")
    print(task1)
    print(machine_a1.__dict__)
    
    # 작업 완료
    finished_tasks = machine_a1.finish_processing()
    print("작업 완료 후:")
    print(finished_tasks[0])
    print(machine_a1.__dict__)
