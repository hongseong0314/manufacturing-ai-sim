# -*- coding: utf-8 -*-
import random
import string
from typing import List
from src.objects import Task

class DataGenerator:
    """
    시뮬레이션을 위한 Task(Job) 생성기.
    """
    def __init__(self):
        self.task_uid_counter = 0

    def generate_new_jobs(self, current_time: int) -> List[Task]:
        """
        새로운 Job(40개의 Task 묶음)을 생성합니다.
        - 30분 주기로 호출되는 것을 가정합니다.
        """
        # 1. 새로운 Job ID 랜덤 생성 (4자리 문자열)
        job_id = ''.join(random.choices(string.ascii_uppercase, k=4))
        
        # 2. 공통 속성 정의
        # 납기: 현재 시간 + 100~150분 사이의 랜덤한 값
        due_date = current_time + random.randint(100, 150)
        
        # A공정 품질 사양: 목표 50, 허용 오차 ±2 ~ ±3
        spec_a_tolerance = random.uniform(2.0, 3.0)
        spec_a = (50.0 - spec_a_tolerance, 50.0 + spec_a_tolerance)
        
        # B공정 품질 사양: 모든 Task가 통과할 수 있는 넓은 범위
        # B공정 QA 평균값이 50~66 범위이므로, 아래한계를 낮춤
        spec_b = (45.0 + random.uniform(0, 5), 75.0 + random.uniform(0, 10))
        
        # 팩킹용 정보
        material_types = ['plastic', 'metal', 'composite']
        colors = ['red', 'blue', 'green']
        customer_id = ''.join(random.choices(string.ascii_uppercase, k=4))
        margin_value = random.uniform(0.3, 0.9)  # 0.3 ~ 0.9

        new_tasks = []
        positions = ['a', 'b', 'c', 'd']
        num_per_position = 10

        # 3. Task 배치 생성 (총 40개)
        for pos in positions:
            for i in range(num_per_position):
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
                    location='QUEUE_A',
                    arrival_time=current_time,  # C공정 도착 시간용
                )
                new_tasks.append(task)
                self.task_uid_counter += 1
        
        print(f"t={current_time}: DataGenerator가 신규 Job(id={job_id}) 생성. 총 {len(new_tasks)}개 Task를 QUEUE_A에 추가.")
        return new_tasks

if __name__ == '__main__':
    # 클래스 사용 예시
    generator = DataGenerator()
    
    # t=30 일 때의 Task 생성
    tasks_t30 = generator.generate_new_jobs(current_time=30)
    print(f"  - 생성된 첫 번째 Task: {tasks_t30[0]}")
    print(f"  - 생성된 마지막 Task: {tasks_t30[-1]}")
    
    # t=60 일 때의 Task 생성
    tasks_t60 = generator.generate_new_jobs(current_time=60)
    print(f"  - 생성된 첫 번째 Task: {tasks_t60[0]}")
    print(f"  - 생성된 마지막 Task: {tasks_t60[-1]}")
