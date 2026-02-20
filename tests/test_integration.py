# -*- coding: utf-8 -*-
"""
전체 제조 시스템 통합 테스트
A(가공) → B(세정) → C(팩킹) 파이프라인 검증
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.agents.factory import build_meta_scheduler
from src.environment.manufacturing_env import ManufacturingEnv
import numpy as np


def _step_with_meta(env, meta):
    state = env.get_decision_state()
    actions = meta.decide(state)
    return env.step(actions)


def test_deterministic_mode():
    """
    Deterministic 모드 테스트 (노이즈 제거, 결정론적)
    """
    print("\n" + "="*80)
    print("테스트 1: Deterministic 모드 (결정론적 시뮬레이션)")
    print("="*80)
    
    env_config = {
        'num_machines_A': 2,
        'num_machines_B': 2,
        'num_machines_C': 1,
        'process_time_A': 8,
        'process_time_B': 4,
        'process_time_C': 0,  # 팩킹은 시간 소비 안 함
        'max_steps': 100,
        'deterministic_mode': True,
        'scheduler_B': 'rule-based',  # Rule-Based 스케줄러
        'packing_C': 'greedy',         # Greedy 팩커
        'batch_size_C': 4,             # 한 팩 4개 Task
        'min_queue_size': 4,
        'max_wait_time': 30,
    }
    
    env = ManufacturingEnv(env_config)
    meta = build_meta_scheduler(env.config)
    obs = env.reset()
    
    print(f"\n초기 상태:")
    print(f"  - A공정 대기: {obs['A_state']['wait_pool_size']}개")
    print(f"  - 완료된 Task: {obs['num_completed']}개")
    
    done = False
    step_count = 0
    
    while not done and step_count < env_config['max_steps']:
        obs, reward, done, _ = _step_with_meta(env, meta)
        step_count += 1
        
        if step_count % 20 == 0:
            print(f"\n[Step {step_count}]")
            print(f"  A상태: 대기={obs['A_state']['wait_pool_size']}, 통과율={obs['A_state']['first_pass_rate']:.2%}")
            print(f"  B상태: 대기={obs['B_state']['wait_pool_size']}, 재작업={obs['B_state']['rework_pool_size']}, 통과율={obs['B_state']['first_pass_rate']:.2%}")
            print(f"  C상태: 대기={obs['C_state']['queue_size']}, 팩수={obs['C_state']['completed_packs']}")
            print(f"  완료: {obs['num_completed']}개")
    
    print(f"\n\n최종 결과 (Step {step_count}):")
    print(f"  총 완료 Task: {obs['num_completed']}개")
    print(f"  A공정 통과율: {obs['A_state']['first_pass_rate']:.2%}")
    print(f"  B공정 통과율: {obs['B_state']['first_pass_rate']:.2%}")
    print(f"  완성 팩 수: {obs['C_state']['completed_packs']}개")
    print(f"  팩질성: {obs['C_state']['avg_quality']:.2f}")
    
    assert obs['num_completed'] > 0, "완료된 Task가 없음!"
    print("\n[PASS] Deterministic 모드 테스트 통과!")


def test_stochastic_mode():
    """
    Stochastic 모드 테스트 (노이즈 포함)
    """
    print("\n" + "="*80)
    print("테스트 2: Stochastic 모드 (확률적 시뮬레이션)")
    print("="*80)
    
    env_config = {
        'num_machines_A': 3,
        'num_machines_B': 2,
        'num_machines_C': 1,
        'process_time_A': 8,
        'process_time_B': 4,
        'max_steps': 150,
        'deterministic_mode': False,  # Stochastic
        'scheduler_B': 'rule-based',
        'packing_C': 'greedy',
        'batch_size_C': 4,
    }
    
    env = ManufacturingEnv(env_config)
    meta = build_meta_scheduler(env.config)
    obs = env.reset()
    
    print(f"\n초기 상태: A대기={obs['A_state']['wait_pool_size']}개")
    
    done = False
    step_count = 0
    metrics = []
    
    while not done and step_count < env_config['max_steps']:
        obs, reward, done, _ = _step_with_meta(env, meta)
        step_count += 1
        
        metrics.append({
            'step': step_count,
            'completed': obs['num_completed'],
            'a_pass_rate': obs['A_state']['first_pass_rate'],
            'b_pass_rate': obs['B_state']['first_pass_rate'],
            'packs': obs['C_state']['completed_packs'],
        })
    
    final_completed = obs['num_completed']
    avg_a_rate = np.mean([m['a_pass_rate'] for m in metrics])
    avg_b_rate = np.mean([m['b_pass_rate'] for m in metrics])
    final_packs = obs['C_state']['completed_packs']
    
    print(f"\n최종 결과 (Step {step_count}):")
    print(f"  완료 Task: {final_completed}개")
    print(f"  평균 A통과율: {avg_a_rate:.2%}")
    print(f"  평균 B통과율: {avg_b_rate:.2%}")
    print(f"  완성 팩: {final_packs}개")
    
    assert final_completed > 0, "완료된 Task가 없음!"
    print("\n[PASS] Stochastic 모드 테스트 통과!")


def test_scheduler_comparison():
    """
    스케줄러 비교 테스트 (FIFO vs Rule-Based)
    """
    print("\n" + "="*80)
    print("테스트 3: 스케줄러 비교 (FIFO vs Rule-Based)")
    print("="*80)
    
    schedulers = ['fifo', 'rule-based']
    results = {}
    
    for scheduler_type in schedulers:
        print(f"\n[{scheduler_type.upper()} 스케줄러]")
        
        env_config = {
            'num_machines_A': 2,
            'num_machines_B': 2,
            'num_machines_C': 1,
            'process_time_A': 8,
            'process_time_B': 4,
            'max_steps': 100,
            'deterministic_mode': True,
            'scheduler_B': scheduler_type,
            'packing_C': 'greedy',
            'batch_size_C': 4,
        }
        
        env = ManufacturingEnv(env_config)
        meta = build_meta_scheduler(env.config)
        obs = env.reset()
        
        done = False
        while not done:
            obs, reward, done, _ = _step_with_meta(env, meta)
        
        results[scheduler_type] = {
            'completed': obs['num_completed'],
            'a_rate': obs['A_state']['first_pass_rate'],
            'b_rate': obs['B_state']['first_pass_rate'],
            'packs': obs['C_state']['completed_packs'],
        }
        
        print(f"  완료: {obs['num_completed']}, A통과: {obs['A_state']['first_pass_rate']:.2%}, B통과: {obs['B_state']['first_pass_rate']:.2%}")
    
    print(f"\n비교 결과:")
    print(f"  FIFO:       {results['fifo']['completed']}개 완료, 팩={(results['fifo']['packs'])}")
    print(f"  Rule-Based: {results['rule-based']['completed']}개 완료, 팩={results['rule-based']['packs']}")
    
    print("\n[PASS] 스케줄러 비교 테스트 통과!")


def test_packer_comparison():
    """
    팩커 비교 테스트 (FIFO vs Greedy)
    """
    print("\n" + "="*80)
    print("테스트 4: 팩커 비교 (FIFO vs Greedy)")
    print("="*80)
    
    packers = ['fifo', 'greedy']
    results = {}
    
    for packer_type in packers:
        print(f"\n[{packer_type.upper()} 팩커]")
        
        env_config = {
            'num_machines_A': 2,
            'num_machines_B': 2,
            'num_machines_C': 1,
            'process_time_A': 8,
            'process_time_B': 4,
            'max_steps': 100,
            'deterministic_mode': True,
            'scheduler_B': 'rule-based',
            'packing_C': packer_type,
            'batch_size_C': 4,
        }
        
        env = ManufacturingEnv(env_config)
        meta = build_meta_scheduler(env.config)
        obs = env.reset()
        
        done = False
        while not done:
            obs, reward, done, _ = _step_with_meta(env, meta)
        
        results[packer_type] = {
            'completed': obs['num_completed'],
            'packs': obs['C_state']['completed_packs'],
            'quality': obs['C_state']['avg_quality'],
            'wait_time': obs['C_state']['avg_wait_time'],
        }
        
        print(f"  팩수: {obs['C_state']['completed_packs']}, 품질: {obs['C_state']['avg_quality']:.2f}, 대기: {obs['C_state']['avg_wait_time']:.1f}분")
    
    print(f"\n비교 결과:")
    print(f"  FIFO:   팩={results['fifo']['packs']}, 품질={results['fifo']['quality']:.2f}")
    print(f"  Greedy: 팩={results['greedy']['packs']}, 품질={results['greedy']['quality']:.2f}")
    
    print("\n[PASS] 팩커 비교 테스트 통과!")


if __name__ == '__main__':
    print("\n" + "="*80)
    print("제조 시스템 통합 테스트 시작")
    print("="*80)
    
    try:
        test_deterministic_mode()
        test_stochastic_mode()
        test_scheduler_comparison()
        test_packer_comparison()
        
        print("\n\n" + "="*80)
        print("[PASS] 모든 테스트 통과!")
        print("="*80)
        
    except Exception as e:
        print(f"\n[ERROR] 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
