from dataclasses import replace

from src.agents.factory import build_mes_policy_stack
from src.mes import MESDevelopmentHarness
from src.mes.services import MESDecisionService

from mes_harness_support import (
    _ForceStageL3Policy,
    _build_b_wait_env,
    _build_c_fifo_env,
    _build_c_group_env,
    _build_env,
    _build_multi_stage_budget_env,
    _by_layer,
)


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


def test_planner_records_candidate_portfolio_snapshot_with_selected_and_rejected_rows():
    env = _build_c_group_env()
    harness = MESDevelopmentHarness(config={**env.config, "mes_l1_C": "grouped"})

    plan = harness.planner.plan(env.get_decision_state(), target_stage="C")
    snapshot = next(
        item for item in plan.feature_snapshots if item.layer_id == "PORTFOLIO"
    )
    rows = snapshot.features["candidates"]

    assert snapshot.correlation_id == plan.correlation_id
    assert len(rows) >= 2
    selected_rows = [row for row in rows if row["selected"]]
    rejected_rows = [row for row in rows if not row["selected"]]
    assert selected_rows
    assert rejected_rows
    assert {
        "correlation_id",
        "candidate_id",
        "stage",
        "candidate_type",
        "group_key",
        "equipment_id",
        "task_uids",
        "local_score",
        "local_rank",
        "l2_annotation",
        "upper_score",
        "score_components",
        "selected",
        "rejection_reason",
        "linked_recommendation_ids",
    } <= set(rows[0])


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
