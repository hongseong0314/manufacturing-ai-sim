from src.mes.runtime.context import MESAPIContext
from src.mes.runtime.experiments import (
    capture_scenario,
    list_policy_variants,
    list_scenarios,
    run_experiment,
)


def test_capture_scenario_freezes_current_decision_state():
    context = MESAPIContext()

    payload = capture_scenario(context)

    assert payload["scenario_id"].startswith("SCN_")
    assert payload["time"] == context.env.time
    assert payload["decision_state"]["A"]
    assert payload["decision_state"]["B"]
    assert payload["decision_state"]["C"]
    assert payload["source_correlation_id"] is None
    context.env.time += 100
    assert list_scenarios(context)["items"][0]["time"] != context.env.time


def test_policy_variants_include_baseline_and_alternatives():
    payload = list_policy_variants()

    variant_ids = {item["variant_id"] for item in payload["items"]}
    assert {
        "baseline_fifo_rule",
        "c_grouped_packing",
        "l3_due_date_aggressive",
    } <= variant_ids


def test_experiment_replays_variants_without_mutating_live_env():
    context = MESAPIContext()
    before_time = context.env.time
    scenario = capture_scenario(context)

    payload = run_experiment(
        context,
        {
            "scenario_id": scenario["scenario_id"],
            "variant_ids": ["baseline_fifo_rule", "c_grouped_packing"],
        },
    )

    assert payload["experiment_id"].startswith("EXP_")
    assert payload["scenario_id"] == scenario["scenario_id"]
    assert context.env.time == before_time
    assert [row["variant_id"] for row in payload["results"]] == [
        "baseline_fifo_rule",
        "c_grouped_packing",
    ]
    for row in payload["results"]:
        assert row["correlation_id"]
        assert row["l4_objective_id"]
        assert "l3_policy_id" in row
        assert "candidate_count" in row
        assert "command_valid" in row
        assert "portfolio" in row
        assert "kpi_delta" in row
