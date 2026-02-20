# -*- coding: utf-8 -*-
"""Task/job generator used by the manufacturing simulation."""

import random
import string
from typing import List

from src.objects import Task


class DataGenerator:
    """Generate batches of tasks injected into process A."""

    def __init__(self):
        self.task_uid_counter = 0

    def generate_new_jobs(self, current_time: int) -> List[Task]:
        """Generate one synthetic job consisting of 40 tasks.

        The simulator typically calls this every 30 steps for periodic arrivals.
        """
        # 1) Generate a random 4-letter job ID.
        job_id = "".join(random.choices(string.ascii_uppercase, k=4))

        # 2) Shared attributes for tasks in this job.
        due_date = current_time + random.randint(100, 150)

        # Process A spec: target around 50 with random tolerance.
        spec_a_tolerance = random.uniform(2.0, 3.0)
        spec_a = (50.0 - spec_a_tolerance, 50.0 + spec_a_tolerance)

        # Process B spec: wider range so baseline scenarios can pass.
        spec_b = (45.0 + random.uniform(0, 5), 75.0 + random.uniform(0, 10))

        material_types = ["plastic", "metal", "composite"]
        colors = ["red", "blue", "green"]
        customer_id = "".join(random.choices(string.ascii_uppercase, k=4))
        margin_value = random.uniform(0.3, 0.9)

        new_tasks: List[Task] = []
        positions = ["a", "b", "c", "d"]
        num_per_position = 10

        # 3) Build 40 tasks (4 positions x 10 each).
        for _pos in positions:
            for _ in range(num_per_position):
                task = Task(
                    uid=self.task_uid_counter,
                    job_id=job_id,
                    due_date=due_date,
                    spec_a=spec_a,
                    spec_b=spec_b,
                    material_type=random.choice(material_types),
                    color=random.choice(colors),
                    customer_id=customer_id,
                    margin_value=margin_value,
                    location="QUEUE_A",
                    arrival_time=current_time,
                )
                new_tasks.append(task)
                self.task_uid_counter += 1

        print(
            f"t={current_time}: DataGenerator created job(id={job_id}) with "
            f"{len(new_tasks)} tasks for QUEUE_A."
        )
        return new_tasks


if __name__ == "__main__":
    generator = DataGenerator()

    tasks_t30 = generator.generate_new_jobs(current_time=30)
    print(f"  - First generated task: {tasks_t30[0]}")
    print(f"  - Last generated task: {tasks_t30[-1]}")

    tasks_t60 = generator.generate_new_jobs(current_time=60)
    print(f"  - First generated task: {tasks_t60[0]}")
    print(f"  - Last generated task: {tasks_t60[-1]}")
