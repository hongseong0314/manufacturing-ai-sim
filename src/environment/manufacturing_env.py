# -*- coding: utf-8 -*-
from typing import List, Dict, Any, Optional

# Local project imports
from src.objects import Task
from src.data_generator import DataGenerator
from src.environment.process_a_env import ProcessA_Env
from src.environment.process_b_env import ProcessB_Env
from src.environment.process_c_env import ProcessC_Env


class ManufacturingEnv:
    """
    Top-level orchestrator that integrates three independent process environments
    (A, B, C) into one end-to-end manufacturing simulation.

    Responsibilities:
    - Advance global simulation time
    - Execute process steps in order
    - Move tasks between processes
    - Track completed tasks and return observations/reward
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.time = 0
        self.data_generator = DataGenerator()

        # Initialize each process environment
        self.env_A = ProcessA_Env(config)
        self.env_B = ProcessB_Env(config)
        self.env_C = ProcessC_Env(config)

        # Store tasks that reached final completion
        self.completed_tasks: List[Task] = []

    def step(self, actions: Dict[str, Dict]):
        """
        Run one simulation tick.

        Process execution order:
        1) A (processing)
        2) B (inspection)
        3) C (final packaging/completion)
        4) Generate new jobs periodically
        """
        actions = actions or {}

        # 1) Process A step (main processing)
        results_A = self.env_A.step(self.time, actions.get('A'))

        # Same-step handoff: move A-passed tasks to B before B step runs.
        if results_A['succeeded']:
            self.env_B.add_tasks(results_A['succeeded'])

        # 2) Process B step (inspection)
        results_B = self.env_B.step(self.time, actions.get('B'))

        # Same-step handoff: move B-passed tasks to C before C step runs.
        if results_B['succeeded']:
            self.env_C.add_tasks(results_B['succeeded'])

        # Rework tasks remain in B's internal rework pool by design.
        if results_B['rework_count_this_step'] > 0:
            pass

        # 3) Process C step (packaging/final completion)
        results_C = self.env_C.step(self.time, actions.get('C'))
        if results_C['completed']:
            for task in results_C['completed']:
                if task.location != 'COMPLETED':
                    task.location = 'COMPLETED'
            self.completed_tasks.extend(results_C['completed'])
            print(
                f"t={self.time}: Pack #{results_C['pack_count']-1} completed, "
                f"{len(results_C['completed'])} tasks finalized "
                f"(Total: {len(self.completed_tasks)})"
            )

        # 4) Periodic new job generation (every 30 time units)
        if self.time > 0 and self.time % 30 == 0:
            new_tasks = self.data_generator.generate_new_jobs(self.time)
            self.env_A.add_tasks(new_tasks)

        # 5) Advance global time
        self.time += 1

        # 6) Build output tuple
        obs = self._get_observation()
        reward = self._calculate_reward(results_A, results_B, results_C)
        done = self._check_if_done()

        return obs, reward, done, {}

    def reset(self, seed_initial_tasks: bool = True, initial_tasks: Optional[List[Task]] = None):
        """
        Reset all sub-environments and global state.

        Args:
            seed_initial_tasks: If True, auto-generate initial tasks at reset.
            initial_tasks: Optional explicit initial task list.
                If provided, this takes priority over seed_initial_tasks.
        """
        self.time = 0
        self.data_generator = DataGenerator()
        self.completed_tasks = []

        self.env_A.reset()
        self.env_B.reset()
        self.env_C.reset()

        # Seed initial tasks according to reset options
        if initial_tasks is not None:
            self.env_A.add_tasks(initial_tasks)
        elif seed_initial_tasks:
            generated_tasks = self.data_generator.generate_new_jobs(self.time)
            self.env_A.add_tasks(generated_tasks)

        return self._get_observation()

    def _get_observation(self) -> Dict[str, Any]:
        """Return consolidated observation across A/B/C processes."""
        return {
            "time": self.time,
            "A_state": self.env_A.get_state(),
            "B_state": self.env_B.get_state(),
            "C_state": self.env_C.get_state(),
            "num_completed": len(self.completed_tasks),
        }

    def _calculate_reward(self, res_A, res_B, res_C) -> float:
        """Reward = number of tasks completed in process C at this step."""
        return len(res_C.get('completed', []))

    def _check_if_done(self) -> bool:
        """Episode termination condition based on max_steps."""
        return self.time >= self.config.get('max_steps', 1000)


if __name__ == '__main__':
    env_config = {
        'num_machines_A': 2,
        'num_machines_B': 1,
        'num_machines_C': 1,
        'process_time_A': 15,
        'process_time_B': 10,
        'process_time_C': 20,
        'max_steps': 50,
    }

    env = ManufacturingEnv(env_config)
    obs = env.reset()

    print("\n--- Initial state (t=0) ---")

    done = False
    total_reward = 0

    while not done:
        # Simple baseline policy: if A has an idle machine and queued tasks,
        # assign up to 2 tasks to the first idle machine.
        a_actions = {}
        idle_machines_A = [m for m in env.env_A.machines.values() if m.status == 'idle']
        if idle_machines_A and env.env_A.wait_pool:
            machine_to_assign = idle_machines_A[0]
            tasks_to_assign = env.env_A.wait_pool[:2]
            if tasks_to_assign:
                a_actions[machine_to_assign.id] = {
                    'task_uids': [t.uid for t in tasks_to_assign],
                    'recipe': [25.0, 5.0, 5.0],  # Example recipe
                }

        actions = {'A': a_actions, 'B': {}, 'C': {}}

        obs, reward, done, _ = env.step(actions)
        total_reward += reward
        print(
            f"--- t={obs['time']} | Action: {a_actions.keys() or 'No Action'} "
            f"| Reward: {reward} | Total Reward: {total_reward} "
            f"| Completed: {obs['num_completed']} ---"
        )

    print("\n--- Simulation finished ---")
    print(f"Final completed tasks: {obs['num_completed']}")
