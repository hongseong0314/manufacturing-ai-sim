from src.environment.manufacturing_env import ManufacturingEnv
from src.mes import MESDevelopmentHarness, MESEvaluatorAgent


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


def test_development_harness_runs_connected_l4_l3_l1_l2_chain():
    env = _build_env()
    harness = MESDevelopmentHarness()

    result = harness.run(env.get_decision_state(), target_stage="A")

    assert result.passed
    by_layer = _by_layer(result.recommendations)
    assert set(by_layer) == {"L4", "L3", "L1", "L2"}

    correlation_ids = {rec.correlation_id for rec in result.recommendations}
    assert len(correlation_ids) == 1
    assert all(rec.feature_snapshot_id for rec in result.recommendations)
    assert by_layer["L3"].parent_recommendation_id == by_layer["L4"].recommendation_id
    assert by_layer["L1"].parent_recommendation_id == by_layer["L3"].recommendation_id
    assert by_layer["L2"].parent_recommendation_id == by_layer["L1"].recommendation_id

    assert result.generated.validation.passed
    assert result.simulator_actions["A"]
    assert result.command is not None
    assert result.command.status == "CREATED"


def test_harness_actions_step_the_simulator_kernel():
    env = _build_env()
    harness = MESDevelopmentHarness()

    result = harness.run(env.get_decision_state(), target_stage="A")
    env.step(result.simulator_actions)

    machine = next(iter(env.env_A.machines.values()))
    command = result.generated.validation.validated_command
    assert machine.status == "busy"
    assert [task.uid for task in machine.current_batch] == command["task_uids"]


def test_harness_persists_decision_chain_audit_records():
    env = _build_env()
    harness = MESDevelopmentHarness()

    result = harness.run(env.get_decision_state(), target_stage="A")
    correlation_id = result.generated.plan.correlation_id

    assert result.command is not None
    assert len(harness.store.feature_snapshots(correlation_id)) == 4
    assert len(harness.store.recommendations(correlation_id)) == 4
    assert len(harness.store.validations(correlation_id)) == 1
    assert (
        harness.store.commands(correlation_id)[0].command_id
        == result.command.command_id
    )

    event_types = [
        event.event_type for event in harness.store.events(correlation_id)
    ]
    assert event_types[:4] == [
        "OBJECTIVE_SELECTED",
        "STAGE_PRIORITY_UPDATED",
        "DISPATCH_RECOMMENDED",
        "RECIPE_RECOMMENDED",
    ]
    assert "RULE_VALIDATION_PASSED" in event_types
    assert "COMMAND_CREATED" in event_types

    for recommendation in harness.store.recommendations(correlation_id):
        assert recommendation.rule_validation_status == "PASSED"
        assert recommendation.final_command_id == result.command.command_id


def test_run_and_step_executes_and_records_command_event():
    env = _build_env()
    harness = MESDevelopmentHarness()

    result = harness.run_and_step(env, target_stage="A")
    correlation_id = result.generated.plan.correlation_id

    assert result.passed
    assert result.command is not None
    assert result.command.status == "EXECUTED"
    assert result.step_result is not None

    machine = next(iter(env.env_A.machines.values()))
    command = result.generated.validation.validated_command
    assert machine.status == "busy"
    assert [task.uid for task in machine.current_batch] == command["task_uids"]

    event_types = [
        event.event_type for event in harness.store.events(correlation_id)
    ]
    assert "COMMAND_EXECUTED" in event_types


def test_rejected_harness_run_records_validation_without_command():
    env = _build_env()
    harness = MESDevelopmentHarness()

    result = harness.run(env.get_decision_state(), target_stage="B")
    correlation_id = result.generated.plan.correlation_id

    assert not result.passed
    assert result.command is None
    assert harness.store.commands(correlation_id) == []
    assert harness.store.validations(correlation_id)[0].validation_status == "REJECTED"

    event_types = [
        event.event_type for event in harness.store.events(correlation_id)
    ]
    assert "RULE_VALIDATION_REJECTED" in event_types
    assert "COMMAND_EXECUTED" not in event_types


def test_evaluator_rejects_correlation_id_mismatch():
    env = _build_env()
    harness = MESDevelopmentHarness()
    result = harness.run(env.get_decision_state(), target_stage="A")

    result.recommendations[-1].correlation_id = "CORR_BROKEN"
    report = MESEvaluatorAgent().evaluate(result.generated)

    assert not report.passed
    assert "CORRELATION_ID_MISMATCH" in report.issues


def test_evaluator_rejects_broken_parent_chain():
    env = _build_env()
    harness = MESDevelopmentHarness()
    result = harness.run(env.get_decision_state(), target_stage="A")

    by_layer = _by_layer(result.recommendations)
    by_layer["L2"].parent_recommendation_id = "REC_NOT_THE_L1_PARENT"
    report = MESEvaluatorAgent().evaluate(result.generated)

    assert not report.passed
    assert "BROKEN_PARENT_CHAIN" in report.issues


def test_evaluator_cycle_report_flags_set_on_success():
    env = _build_env()
    harness = MESDevelopmentHarness()

    result = harness.run(env.get_decision_state(), target_stage="A")

    assert result.evaluation.checked["chain_completeness"]
    assert result.evaluation.checked["correlation_consistency"]
    assert result.evaluation.checked["command_event_alignment"]


def test_evaluator_rejects_command_event_alignment_mismatch():
    env = _build_env()
    harness = MESDevelopmentHarness()
    result = harness.run(env.get_decision_state(), target_stage="A")

    correlation_id = result.generated.plan.correlation_id
    harness.store._events = [
        event
        for event in harness.store._events
        if not (
            event.correlation_id == correlation_id
            and event.event_type == "COMMAND_CREATED"
        )
    ]

    report = MESEvaluatorAgent().evaluate(result.generated, store=harness.store)

    assert not report.passed
    assert "COMMAND_EVENT_MISMATCH" in report.issues


def test_evaluator_rejects_incomplete_cycle_records_after_correlation_drift():
    env = _build_env()
    harness = MESDevelopmentHarness()
    result = harness.run(env.get_decision_state(), target_stage="A")

    correlation_id = result.generated.plan.correlation_id
    event = next(iter(harness.store.events(correlation_id)))
    event.correlation_id = "CORR_BROKEN"

    report = MESEvaluatorAgent().evaluate(result.generated, store=harness.store)

    assert not report.passed
    assert "INCOMPLETE_CHAIN_RECORDS" in report.issues


def test_generator_supports_continuous_cycle_outputs():
    env = _build_env()
    harness = MESDevelopmentHarness()
    plan = harness.planner.plan(env.get_decision_state(), target_stage="A")

    cycles = harness.generator.generate_continuous(
        env.get_decision_state(),
        plan,
        max_cycles=2,
    )

    assert len(cycles) >= 1
    assert cycles[0].generated.validation.passed
    assert cycles[0].generated.simulator_actions["A"]


def test_l2_recipe_composes_apc_fields_for_rule_engine_command():
    env = _build_env()
    harness = MESDevelopmentHarness()

    result = harness.run(env.get_decision_state(), target_stage="A")
    by_layer = _by_layer(result.recommendations)
    l2_action = by_layer["L2"].recommended_action

    assert l2_action["apc_mode"] == "L1L2_COMPOSED"
    assert "parameters" in l2_action

    command = result.generated.validation.validated_command
    assert "recipe" in command


def test_planner_time_trigger_reuses_objective_between_intervals():
    env = _build_env()
    planner = MESDevelopmentHarness().planner
    planner.planning_interval = 3

    state = env.get_decision_state()
    state["time"] = 0
    plan0 = planner.plan(state)

    state = env.get_decision_state()
    state["time"] = 1
    plan1 = planner.plan(state)

    assert plan0.objective.recommended_action == plan1.objective.recommended_action
    assert plan1.stage_priority.recommended_action["task_generation_trigger_due"] is False


def test_planner_updates_objective_on_large_wait_pool():
    env = _build_env()
    harness = MESDevelopmentHarness()

    state = env.get_decision_state()
    state["A"]["wait_pool_uids"] = list(range(100, 111))
    state["time"] = 2

    plan = harness.planner.plan(state)

    assert plan.objective.objective_id == "OBJ_THROUGHPUT_FIRST"
    assert plan.objective.recommended_action["weights"]["throughput"] > 1.0


def test_rule_engine_prefers_layer_matched_dispatch_and_recipe_recommendations():
    env = _build_env()
    harness = MESDevelopmentHarness()
    state = env.get_decision_state()

    l1 = harness.service.build_rule_only_dispatch_recommendation(state, stage="A")
    assert l1 is not None

    from src.mes.recommendations import create_recommendation

    wrong_dispatch = create_recommendation(
        recommendation_type="DISPATCH",
        layer_id="L3",
        objective_id="OBJ_TEST",
        policy_id="TEST",
        model_id="test",
        model_version="0.0",
        feature_snapshot_id="FS_WRONG",
        correlation_id=l1.correlation_id,
        recommended_action={"stage": "A", "equipment_id": "A_999", "task_uids": [999999]},
    )

    l2 = create_recommendation(
        recommendation_type="RECIPE",
        layer_id="L2",
        objective_id="OBJ_TEST",
        policy_id="TEST",
        model_id="test",
        model_version="0.0",
        feature_snapshot_id="FS_L2",
        correlation_id=l1.correlation_id,
        recommended_action={"recipe": [1.0, 2.0, 3.0]},
        parent_recommendation_id=l1.recommendation_id,
    )

    validation = harness.service.validate_recommendations(state, [wrong_dispatch, l1, l2])

    assert validation.passed
    assert validation.validated_command["dispatch_recommendation_id"] == l1.recommendation_id
    assert validation.validated_command["recipe_recommendation_id"] == l2.recommendation_id
