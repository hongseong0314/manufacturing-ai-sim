from dataclasses import replace

from src.agents.factory import build_mes_policy_stack
from src.environment.manufacturing_env import ManufacturingEnv
from src.mes import MESDevelopmentHarness, MESEvaluatorAgent
from src.mes.services import MESDecisionService
from src.objects import Task


def _build_env():
    env = ManufacturingEnv(
        {
            "num_machines_A": 1,
            "num_machines_B": 1,
            "num_machines_C": 1,
            "process_time_A": 1,
            "process_time_B": 1,
            "process_time_C": 0,
            "deterministic_mode": True,
        }
    )
    env.reset(seed=11)
    return env


def _by_layer(recommendations):
    return {rec.layer_id: rec for rec in recommendations}


def _build_c_group_env():
    env = ManufacturingEnv(
        {
            "num_machines_A": 1,
            "num_machines_B": 1,
            "num_machines_C": 1,
            "batch_size_C": 2,
            "process_time_A": 1,
            "process_time_B": 1,
            "process_time_C": 0,
            "deterministic_mode": True,
        }
    )
    env.reset(seed_initial_tasks=False, seed=17)
    env.time = 50
    tasks = [
        Task(
            uid=100,
            job_id="ALPHA_LOT_100",
            customer_id="ALPHA",
            material_type="plastic",
            color="red",
            due_date=45,
            spec_a=(45.0, 55.0),
            realized_qa_B=45.0,
            margin_value=0.4,
        ),
        Task(
            uid=101,
            job_id="ALPHA_LOT_101",
            customer_id="ALPHA",
            material_type="plastic",
            color="red",
            due_date=46,
            spec_a=(45.0, 55.0),
            realized_qa_B=46.0,
            margin_value=0.4,
        ),
        Task(
            uid=200,
            job_id="BETA_LOT_200",
            customer_id="BETA",
            material_type="metal",
            color="blue",
            due_date=200,
            spec_a=(45.0, 55.0),
            realized_qa_B=90.0,
            margin_value=0.9,
        ),
        Task(
            uid=201,
            job_id="BETA_LOT_201",
            customer_id="BETA",
            material_type="metal",
            color="blue",
            due_date=201,
            spec_a=(45.0, 55.0),
            realized_qa_B=91.0,
            margin_value=0.9,
        ),
    ]
    env.env_C.add_tasks(tasks, current_time=0)
    return env


def _build_multi_stage_budget_env():
    env = ManufacturingEnv(
        {
            "num_machines_A": 2,
            "num_machines_B": 1,
            "num_machines_C": 1,
            "batch_size_C": 2,
            "process_time_A": 1,
            "process_time_B": 1,
            "process_time_C": 0,
            "deterministic_mode": True,
        }
    )
    env.reset(seed_initial_tasks=False, seed=23)
    env.time = 12
    env.env_A.add_tasks(
        [
            Task(uid=10, job_id="A_LOT_10", due_date=80, spec_a=(45.0, 55.0)),
            Task(uid=11, job_id="A_LOT_11", due_date=81, spec_a=(45.0, 55.0)),
        ]
    )
    env.env_C.add_tasks(
        [
            Task(
                uid=210,
                job_id="C_LOT_210",
                customer_id="ALPHA",
                material_type="plastic",
                color="red",
                due_date=70,
                spec_a=(45.0, 55.0),
                realized_qa_B=80.0,
            ),
            Task(
                uid=211,
                job_id="C_LOT_211",
                customer_id="ALPHA",
                material_type="plastic",
                color="red",
                due_date=71,
                spec_a=(45.0, 55.0),
                realized_qa_B=81.0,
            ),
        ],
        current_time=0,
    )
    return env


def _build_c_fifo_env():
    env = ManufacturingEnv(
        {
            "num_machines_A": 1,
            "num_machines_B": 1,
            "num_machines_C": 1,
            "batch_size_C": 2,
            "process_time_A": 1,
            "process_time_B": 1,
            "process_time_C": 0,
            "deterministic_mode": True,
        }
    )
    env.reset(seed_initial_tasks=False, seed=29)
    env.time = 10
    env.env_C.add_tasks(
        [
            Task(
                uid=10,
                job_id="FIFO_10",
                customer_id="ALPHA",
                material_type="plastic",
                color="red",
                due_date=100,
                spec_a=(45.0, 55.0),
                realized_qa_B=50.0,
            ),
            Task(
                uid=11,
                job_id="FIFO_11",
                customer_id="BETA",
                material_type="metal",
                color="blue",
                due_date=101,
                spec_a=(45.0, 55.0),
                realized_qa_B=55.0,
            ),
            Task(
                uid=12,
                job_id="FIFO_12",
                customer_id="ALPHA",
                material_type="plastic",
                color="red",
                due_date=102,
                spec_a=(45.0, 55.0),
                realized_qa_B=95.0,
            ),
        ],
        current_time=0,
    )
    return env


def _build_b_wait_env():
    env = ManufacturingEnv(
        {
            "num_machines_A": 1,
            "num_machines_B": 1,
            "num_machines_C": 1,
            "process_time_A": 1,
            "process_time_B": 1,
            "process_time_C": 0,
            "deterministic_mode": True,
        }
    )
    env.reset(seed_initial_tasks=False, seed=31)
    env.time = 18
    env.env_B.add_tasks(
        [
            Task(uid=310, job_id="B_LOT_310", due_date=90, spec_a=(45.0, 55.0)),
            Task(uid=311, job_id="B_LOT_311", due_date=91, spec_a=(45.0, 55.0)),
        ]
    )
    return env


class _ForceStageL3Policy:
    policy_id = "TEST_FORCE_STAGE_L3"
    model_id = "test-force-stage-l3"
    model_version = "0.0"

    def __init__(self, stage):
        self.stage = stage

    def select(
        self,
        decision_state,
        objective_action,
        candidate_portfolio,
        target_stage=None,
    ):
        candidates = [
            candidate
            for candidate in candidate_portfolio
            if candidate.get("stage") == self.stage
        ]
        selected = candidates[0]
        selected_id = selected["candidate_id"]
        return {
            "target_stage": self.stage,
            "selected_stage": self.stage,
            "selected_candidate_id": selected_id,
            "selected_candidate_ids": [selected_id],
            "selected_group_key": dict(selected.get("group_key", {})),
            "stage_priorities": {
                "A": 1.0 if self.stage == "A" else 0.0,
                "B": 1.0 if self.stage == "B" else 0.0,
                "C": 1.0 if self.stage == "C" else 0.0,
            },
            "dispatch_budgets": {
                "A": 1 if self.stage == "A" else 0,
                "B": 1 if self.stage == "B" else 0,
                "C": 1 if self.stage == "C" else 0,
            },
            "budget_candidate_ids": {
                "A": [selected_id] if self.stage == "A" else [],
                "B": [selected_id] if self.stage == "B" else [],
                "C": [selected_id] if self.stage == "C" else [],
            },
            "score_components": {"upper_score": 999.0},
            "constraints": {
                "max_commands_per_cycle": 1,
                "select_from_l1_portfolio": True,
            },
            "candidate_actions": list(candidate_portfolio),
            "reasons": [f"forced_{self.stage.lower()}_for_policy_swap_test"],
        }
