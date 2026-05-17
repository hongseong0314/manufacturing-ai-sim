from mes_api_support import client, reset_simulation_between_tests
from src.mes.api import context


def _current_run_id():
    payload = client.get("/api/v2/runs").json()
    assert payload["current_run_id"]
    return payload["current_run_id"]


def _run_a_cycle():
    run = client.post("/api/v2/harness/run-cycle", json={"target_stage": "A"})
    assert run.status_code == 200
    payload = run.json()
    command = payload["command"]
    assert command["run_id"]
    return payload, command, command["validated_command"]


def test_reset_starts_new_run_without_losing_previous_genealogy():
    first_run_id = _current_run_id()
    _payload, command, validated = _run_a_cycle()
    task_uid = validated["task_uids"][0]

    first_genealogy = client.get(
        f"/api/v2/genealogy/task/{task_uid}",
        params={"run_id": first_run_id},
    ).json()
    assert first_genealogy["found"] is True
    assert first_genealogy["run_id"] == first_run_id
    assert first_genealogy["assignments"][0]["command_id"] == command["command_id"]

    client.post("/api/v2/simulation/reset")
    second_run_id = _current_run_id()
    assert second_run_id != first_run_id

    current_genealogy = client.get(f"/api/v2/genealogy/task/{task_uid}").json()
    assert current_genealogy["found"] is True
    assert current_genealogy["run_id"] == second_run_id
    assert current_genealogy["assignments"] == []

    previous_genealogy = client.get(
        f"/api/v2/genealogy/task/{task_uid}",
        params={"run_id": first_run_id},
    ).json()
    assert previous_genealogy["found"] is True
    assert previous_genealogy["run_id"] == first_run_id
    assert previous_genealogy["assignments"][0]["command_id"] == command["command_id"]


def test_execution_ledger_and_state_at_are_run_scoped_after_reset():
    run_id = _current_run_id()
    _payload, command, validated = _run_a_cycle()
    task_uid = validated["task_uids"][0]

    client.post("/api/v2/simulation/reset")

    ledger = client.get(
        f"/api/v2/execution-ledger/{command['correlation_id']}",
        params={"run_id": run_id},
    ).json()
    assert ledger["found"] is True
    assert ledger["run_id"] == run_id
    assert ledger["command"]["command_id"] == command["command_id"]

    state = client.get(
        "/api/v2/digital-twin/state-at",
        params={"run_id": run_id, "time": 0},
    ).json()
    assert state["found"] is True
    assert state["run_id"] == run_id
    assert str(task_uid) in state["state"]["tasks"]


def test_state_at_can_read_previous_run_start_snapshot_after_reset():
    run_id = _current_run_id()

    client.post("/api/v2/simulation/reset")

    state = client.get(
        "/api/v2/digital-twin/state-at",
        params={"run_id": run_id, "time": 0},
    ).json()

    assert state["found"] is True
    assert state["run_id"] == run_id
    assert state["summary"]["stages"]["A"]["machines"] == 5
    assert state["source"].startswith("state_index:")


def test_sqlite_normalized_indexes_are_populated_for_current_run():
    run_id = _current_run_id()
    _payload, _command, validated = _run_a_cycle()

    counts = context.harness.store.normalized_index_counts(run_id)

    assert counts["run_index"] >= 1
    assert counts["command_ledger_index"] >= 1
    assert counts["event_ledger_index"] >= 1
    assert counts["assignment_index"] >= len(validated["task_uids"])
    assert counts["state_snapshot_index"] >= 1
    assert counts["task_index"] >= 1
    assert counts["lot_index"] >= 1
    assert counts["equipment_timeline_index"] >= 1
    assert counts["genealogy_edge_index"] >= 1


def test_normalized_index_api_returns_run_scoped_rows():
    run_id = _current_run_id()
    _payload, command, validated = _run_a_cycle()

    assignments = client.get(
        "/api/v2/ledger-index/assignment_index",
        params={"run_id": run_id},
    ).json()
    commands = client.get(
        "/api/v2/ledger-index/command_ledger_index",
        params={"run_id": run_id},
    ).json()

    assert assignments["run_id"] == run_id
    assert assignments["count"] >= len(validated["task_uids"])
    assert any(
        item["command_id"] == command["command_id"]
        for item in assignments["items"]
    )
    assert commands["count"] >= 1
    assert commands["items"][0]["payload"]["command_id"] == command["command_id"]


def test_control_room_exposes_genealogy_run_selector():
    html = client.get("/mes").text

    assert 'id="genealogy-run-id"' in html
    assert "/api/v2/runs" in html
