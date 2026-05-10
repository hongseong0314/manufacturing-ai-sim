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


def test_factory_builds_default_mes_policy_stack_for_fifo_l1_and_rule_l2():
    stack = build_mes_policy_stack({"batch_size_C": 2})

    assert stack.config["scheduler_A"] == "fifo"
    assert stack.config["scheduler_B"] == "fifo"
    assert stack.config["packing_C"] == "fifo"
    assert stack.config["tuner_A"] == "rule-based"
    assert stack.config["tuner_B"] == "rule-based"
    assert stack.config["meta_scheduler_L3"] == "candidate-portfolio-rule"
    assert stack.config["objective_policy_L4"] == "cycle-weight-rule"
    assert stack.l1_policy_id == "L1_FIFO_BASELINE"
    assert stack.l2_policy_id == "L2_RULE_BASED_APC"
    assert stack.l3_policy_id == "L3_CANDIDATE_PORTFOLIO_RULE"
    assert stack.l4_policy_id == "L4_CYCLE_WEIGHT_RULE"
    assert stack.l3_meta_scheduler.policy_id == stack.l3_policy_id
    assert stack.l4_objective_policy.policy_id == stack.l4_policy_id


def test_harness_uses_factory_l3_l4_policy_ids():
    env = _build_env()
    harness = MESDevelopmentHarness(config=env.config)

    result = harness.run(env.get_decision_state(), target_stage="A")

    assert result.passed
    by_layer = _by_layer(result.recommendations)
    assert by_layer["L4"].policy_id == "L4_CYCLE_WEIGHT_RULE"
    assert by_layer["L3"].policy_id == "L3_CANDIDATE_PORTFOLIO_RULE"
    assert by_layer["L3"].model_id == "candidate-portfolio-meta-scheduler"
    assert by_layer["L4"].model_id == "cycle-weight-objective-policy"


def test_fake_l3_policy_can_force_c_candidate_selection():
    env = _build_multi_stage_budget_env()
    stack = replace(
        build_mes_policy_stack(env.config),
        l3_meta_scheduler=_ForceStageL3Policy("C"),
        l3_policy_id="TEST_FORCE_STAGE_L3",
    )
    harness = MESDevelopmentHarness(service=MESDecisionService(policy_stack=stack))

    result = harness.run(env.get_decision_state())

    assert result.passed
    by_layer = _by_layer(result.recommendations)
    assert by_layer["L3"].policy_id == "TEST_FORCE_STAGE_L3"
    assert by_layer["L3"].recommended_action["selected_stage"] == "C"
    assert by_layer["L1"].recommended_action["stage"] == "C"
    assert by_layer["L1"].recommended_action["candidate_id"] == (
        by_layer["L3"].recommended_action["selected_candidate_id"]
    )


def test_fake_l3_policy_can_force_b_candidate_selection():
    env = _build_b_wait_env()
    stack = replace(
        build_mes_policy_stack(env.config),
        l3_meta_scheduler=_ForceStageL3Policy("B"),
        l3_policy_id="TEST_FORCE_STAGE_L3",
    )
    harness = MESDevelopmentHarness(service=MESDecisionService(policy_stack=stack))

    result = harness.run(env.get_decision_state())

    assert result.passed
    by_layer = _by_layer(result.recommendations)
    assert by_layer["L3"].policy_id == "TEST_FORCE_STAGE_L3"
    assert by_layer["L3"].recommended_action["selected_stage"] == "B"
    assert by_layer["L1"].recommended_action["stage"] == "B"


def test_harness_uses_factory_fifo_l1_policy_for_c_packing():
    env = _build_c_fifo_env()
    service = MESDecisionService(
        policy_stack=build_mes_policy_stack(
            {
                "batch_size_C": 2,
                "packing_C": "fifo",
                "mes_l1_C": "fifo",
                "tuner_A": "rule-based",
                "tuner_B": "rule-based",
            }
        )
    )
    harness = MESDevelopmentHarness(service=service)

    result = harness.run(env.get_decision_state(), target_stage="C")

    assert result.passed
    by_layer = _by_layer(result.recommendations)
    l1 = by_layer["L1"]
    l2 = by_layer["L2"]
    assert l1.policy_id == "L1_FIFO_BASELINE"
    assert l1.recommended_action["task_uids"] == [10, 11]
    assert l1.recommended_action["policy_source"]["factory"] == "build_mes_policy_stack"
    assert l2.policy_id == "L2_RULE_BASED_APC"
    assert l2.recommended_action["apc_mode"] == "L1L2_COMPOSED"
    assert l2.recommended_action["policy_source"]["factory"] == "build_mes_policy_stack"
    assert l2.recommended_action["policy_source"]["l2_policy_id"] == "L2_RULE_BASED_APC"


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


def test_c_packing_l3_selects_due_customer_from_l1_candidate_portfolio():
    env = _build_c_group_env()
    harness = MESDevelopmentHarness(config={**env.config, "mes_l1_C": "grouped"})

    result = harness.run(env.get_decision_state(), target_stage="C")

    assert result.passed
    by_layer = _by_layer(result.recommendations)
    l3 = by_layer["L3"]
    l1 = by_layer["L1"]
    l2 = by_layer["L2"]

    customer_scores = {
        candidate["group_key"]["customer_id"]: candidate["local_score"]
        for candidate in l3.candidate_actions
    }
    assert customer_scores["BETA"] > customer_scores["ALPHA"]
    assert l3.recommended_action["selected_group_key"]["customer_id"] == "ALPHA"
    assert l3.recommended_action["selected_candidate_id"] == l1.recommended_action["candidate_id"]
    assert l1.recommended_action["group_key"]["customer_id"] == "ALPHA"
    assert l2.recommended_action["candidate_id"] == l1.recommended_action["candidate_id"]
    assert result.command is not None
    assert (
        result.command.validated_command["dispatch_recommendation_id"]
        == l1.recommendation_id
    )


def test_l3_c_packing_candidates_include_l2_annotations_before_selection():
    env = _build_c_group_env()
    harness = MESDevelopmentHarness(config={**env.config, "mes_l1_C": "grouped"})

    result = harness.run(env.get_decision_state(), target_stage="C")

    assert result.passed
    by_layer = _by_layer(result.recommendations)
    l3 = by_layer["L3"]
    l1 = by_layer["L1"]
    l2 = by_layer["L2"]

    assert len(l3.candidate_actions) >= 2
    for candidate in l3.candidate_actions:
        annotation = candidate["l2_annotation"]
        assert annotation["candidate_id"] == candidate["candidate_id"]
        assert annotation["stage"] == "C"
        assert "pack_quality_prediction" in annotation
        assert "compatibility" in annotation
        assert annotation["quality_risk"] in {"LOW", "MEDIUM", "HIGH"}

    l1_candidate_ids = {
        candidate["candidate_id"] for candidate in l1.candidate_actions
    }
    l2_candidate_ids = {
        annotation["candidate_id"] for annotation in l2.candidate_actions
    }
    assert l1_candidate_ids <= l2_candidate_ids
    assert l2.recommended_action["candidate_id"] == l1.recommended_action["candidate_id"]


def test_l3_allocates_multi_stage_budgets_from_single_portfolio_pass():
    env = _build_multi_stage_budget_env()
    harness = MESDevelopmentHarness(config=env.config)

    plan = harness.planner.plan(env.get_decision_state())
    action = plan.stage_priority.recommended_action

    assert action["dispatch_budgets"]["A"] == 2
    assert action["dispatch_budgets"]["C"] == 1
    assert action["constraints"]["max_commands_per_cycle"] == 3
    assert len(action["selected_candidate_ids"]) == 3
    selected_stages = {
        candidate["stage"]
        for candidate in plan.candidate_portfolio
        if candidate["candidate_id"] in action["selected_candidate_ids"]
    }
    assert selected_stages == {"A", "C"}


def test_rule_engine_rejects_l3_l1_selected_candidate_mismatch():
    env = _build_c_group_env()
    harness = MESDevelopmentHarness()
    state = env.get_decision_state()

    result = harness.run(state, target_stage="C")
    by_layer = _by_layer(result.recommendations)
    by_layer["L1"].recommended_action["candidate_id"] = "CAND_C_BROKEN"

    validation = harness.service.validate_recommendations(state, result.recommendations)

    assert not validation.passed
    assert "L3_L1_CANDIDATE_MISMATCH" in validation.reasons


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
