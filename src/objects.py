# -*- coding: utf-8 -*-
"""Core simulation domain objects (tasks and machines)."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class Task:
    """A single unit of work that flows through A -> B -> C."""

    uid: int
    job_id: str
    due_date: int
    spec_a: Tuple[float, float]
    spec_b: Tuple[float, float] = (20.0, 80.0)

    # Runtime status.
    location: str = "QUEUE_A"

    # Process quality outcomes.
    realized_qa_A: float = -1.0
    realized_qa_B: float = -1.0

    # Packaging-related attributes.
    material_type: str = "plastic"
    color: str = "red"
    customer_id: str = "UNKNOWN"
    margin_value: float = 0.5

    # Tracking fields.
    arrival_time: int = 0
    pack_id: int = -1
    rework_count: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)


class BaseMachine:
    """Base machine abstraction shared by all process machines."""

    def __init__(self, machine_id: int, batch_size: int = 1):
        self.id = machine_id
        self.batch_size = batch_size
        self.status: str = "idle"
        self.current_batch: List[Task] = []
        self.finish_time: int = -1

    def start_processing(self, batch: List[Task], finish_time: int):
        """Start processing a batch on this machine."""
        if self.status != "idle":
            raise Exception(
                f"Machine {self.id} is not idle, but tried to start a new process."
            )
        if len(batch) > self.batch_size:
            raise Exception(
                f"Machine {self.id} batch size ({len(batch)}) exceeds max batch size ({self.batch_size})."
            )

        self.status = "busy"
        self.current_batch = batch
        self.finish_time = finish_time

        for task in batch:
            task.location = f"PROC_{self.id}"

    def finish_processing(self) -> List[Task]:
        """Finish current batch and return processed tasks."""
        if self.status != "busy":
            raise Exception(
                f"Machine {self.id} is not busy, but tried to finish a process."
            )
        self.status = "idle"
        self.finish_time = -1
        finished_batch = self.current_batch
        self.current_batch = []
        self.current_recipe = []
        return finished_batch


class ProcessA_Machine(BaseMachine):
    """Process-A machine with consumable-aging state."""

    def __init__(self, machine_id: int, batch_size: int = 1, initial_m_age: int = 0):
        super().__init__(f"A_{machine_id}", batch_size=batch_size)
        self.m_age = initial_m_age
        self.u = 0
        self.current_recipe: List[float] = []

    def start_processing(
        self,
        batch: List[Task],
        finish_time: int,
        recipe: List[float] = None,
    ):
        """Start processing and update A-machine aging counters."""
        super().start_processing(batch, finish_time)
        self.m_age += 1
        self.u += 1
        self.current_recipe = recipe if recipe is not None else []

    def replace_consumable(self):
        """Replace consumable and reset usage counter."""
        self.u = 0


class ProcessB_Machine(BaseMachine):
    """Process-B machine with solution-aging state."""

    def __init__(self, machine_id: int, batch_size: int = 1, initial_b_age: int = 0):
        super().__init__(f"B_{machine_id}", batch_size=batch_size)
        self.b_age = initial_b_age
        self.v = 0
        self.current_recipe: List[float] = []

    def start_processing(
        self,
        batch: List[Task],
        finish_time: int,
        recipe: List[float] = None,
    ):
        """Start processing and update B-machine aging counters."""
        if self.status != "idle":
            raise Exception(f"Machine {self.id} is not idle.")
        if len(batch) > self.batch_size:
            raise Exception(
                f"Machine {self.id} batch size ({len(batch)}) exceeds max batch size ({self.batch_size})."
            )

        self.status = "busy"
        self.current_batch = batch
        self.finish_time = finish_time
        self.b_age += 1
        self.v += 1
        self.current_recipe = recipe if recipe is not None else []

        for task in batch:
            task.location = f"PROC_{self.id}"

    def replace_solution(self):
        """Replace solution and reset usage counter."""
        self.v = 0


class ProcessC_Machine(BaseMachine):
    """Process-C machine (pack/finalization)."""

    def __init__(self, machine_id: int, batch_size: int = 1):
        super().__init__(f"C_{machine_id}", batch_size=batch_size)


if __name__ == "__main__":
    # Small smoke example.
    task1 = Task(uid=1, job_id="JOB001", due_date=100, spec_a=(45.0, 55.0))
    machine_a1 = ProcessA_Machine(machine_id=1)

    print("Initial state:")
    print(task1)
    print(machine_a1.__dict__)

    machine_a1.start_processing(batch=[task1], finish_time=15)
    print("After start_processing:")
    print(task1)
    print(machine_a1.__dict__)

    finished_tasks = machine_a1.finish_processing()
    print("After finish_processing:")
    print(finished_tasks[0])
    print(machine_a1.__dict__)
