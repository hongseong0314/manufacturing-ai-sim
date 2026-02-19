# -*- coding: utf-8 -*-
"""
간단한 디버그 테스트
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.environment.manufacturing_env import ManufacturingEnv

env_config = {
    'num_machines_A': 2,
    'num_machines_B': 2,
    'num_machines_C': 1,
    'process_time_A': 8,
    'process_time_B': 4,
    'max_steps': 150,
    'deterministic_mode': True,
    'scheduler_B': 'rule-based',
    'packing_C': 'greedy',
    'batch_size_C': 4,
}

env = ManufacturingEnv(env_config)
obs = env.reset()

print(f"초기: A대기={obs['A_state']['wait_pool_size']}")

for step in range(150):
    obs, reward, done, _ = env.step({})
    
    if step % 30 == 0:
        print(f"\nStep {step}:")
        print(f"  A: 대기={obs['A_state']['wait_pool_size']}, 통과={obs['A_state']['first_pass_rate']:.0%}")
        print(f"  B: 대기={obs['B_state']['wait_pool_size']}, 재작업={obs['B_state']['rework_pool_size']}, 통과={obs['B_state']['first_pass_rate']:.0%}")
        print(f"  C: 대기={obs['C_state']['queue_size']}, 팩={obs['C_state']['completed_packs']}")
        print(f"  완료={obs['num_completed']}")
    
    if done:
        break

print(f"\n최종 완료: {obs['num_completed']}")
