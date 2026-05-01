from src.environment.manufacturing_env import ManufacturingEnv
from src.mes import MESDecisionService


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
    env.reset(seed=7)
    return env


def test_mes_adapter_maps_initial_simulator_state():
    env = _build_env()
    service = MESDecisionService()

    mes_state = service.decision_state_to_mes(env.get_decision_state())

    assert mes_state["time"] == 0
    assert len(mes_state["wafers"]) == 40
    assert len(mes_state["lots"]) == 1
    assert mes_state["lots"][0]["quantity"] == 40
    assert mes_state["wip"]["A"]["wait"] == 40
    assert mes_state["equipment"][0]["equipment_id"] == "A_0"
    assert mes_state["equipment"][0]["status"] == "IDLE"


def test_rule_only_dispatch_recommendation_validates_and_steps_simulator():
    env = _build_env()
    service = MESDecisionService()
    state = env.get_decision_state()

    recommendation = service.build_rule_only_dispatch_recommendation(state, stage="A")
    assert recommendation is not None
    assert recommendation.layer_id == "L1"
    assert recommendation.recommendation_type == "DISPATCH"

    validation = service.validate_recommendations(state, [recommendation])
    assert validation.passed
    assert validation.validated_command["stage"] == "A"
    assert validation.validated_command["task_uids"]

    actions = service.simulator_actions_from_validation(validation)
    env.step(actions)

    machine = next(iter(env.env_A.machines.values()))
    assert machine.status == "busy"
    assert machine.current_batch[0].uid == validation.validated_command["task_uids"][0]


def test_rule_engine_rejects_unavailable_task():
    env = _build_env()
    service = MESDecisionService()
    state = env.get_decision_state()

    recommendation = service.build_rule_only_dispatch_recommendation(state, stage="A")
    assert recommendation is not None
    recommendation.recommended_action = {
        "stage": "A",
        "equipment_id": "A_0",
        "task_uids": [999999],
    }

    validation = service.validate_recommendations(state, [recommendation])

    assert not validation.passed
    assert "TASK_NOT_AVAILABLE" in validation.reasons
