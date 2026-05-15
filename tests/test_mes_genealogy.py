from mes_api_support import client, reset_simulation_between_tests


def _run_a_cycle():
    run = client.post("/api/v2/harness/run-cycle", json={"target_stage": "A"})
    assert run.status_code == 200
    payload = run.json()
    command = payload["command"]
    validated = command["validated_command"]
    return payload, command, validated


def test_task_genealogy_links_creation_assignment_command_and_events():
    _payload, command, validated = _run_a_cycle()
    task_uid = validated["task_uids"][0]

    response = client.get(f"/api/v2/genealogy/task/{task_uid}")

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["task_uid"] == task_uid
    assert body["lot_id"]
    assert command["correlation_id"] in body["related_correlation_ids"]
    assert any(item["event_type"] == "TASK_CREATED" for item in body["timeline"])
    assert any(item["event_type"] == "COMMAND_CREATED" for item in body["timeline"])
    assert any(item["event_type"] == "COMMAND_EXECUTED" for item in body["timeline"])
    assert any(item["event_type"] == "EQUIPMENT_STARTED" for item in body["timeline"])
    assert body["assignments"][0]["equipment_id"] == validated["equipment_id"]
    assert body["assignments"][0]["command_id"] == command["command_id"]
    assert body["assignment_trace"]["correlation_id"] == command["correlation_id"]


def test_execution_ledger_contains_validation_command_simulator_action_and_state():
    _payload, command, validated = _run_a_cycle()

    response = client.get(f"/api/v2/execution-ledger/{command['correlation_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["correlation_id"] == command["correlation_id"]
    event_types = {item["event_type"] for item in body["records"]}
    assert {
        "RULE_VALIDATION_PASSED",
        "COMMAND_CREATED",
        "COMMAND_EXECUTED",
        "SIMULATOR_ACTION_APPLIED",
    } <= event_types
    assert body["command"]["command_id"] == command["command_id"]
    assert body["command"]["validated_command"]["equipment_id"] == validated["equipment_id"]
    assert body["post_state"]["time"] >= body["decision_state"]["time"]
    assert body["assignment_trace_url"].endswith(command["correlation_id"])


def test_equipment_genealogy_returns_command_timeline_for_tool():
    _payload, command, validated = _run_a_cycle()

    response = client.get(f"/api/v2/genealogy/equipment/{validated['equipment_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["equipment_id"] == validated["equipment_id"]
    assert any(item["command_id"] == command["command_id"] for item in body["commands"])
    assert any(item["event_type"] == "EQUIPMENT_STARTED" for item in body["timeline"])


def test_lot_genealogy_rolls_up_task_histories():
    _payload, _command, validated = _run_a_cycle()
    task_uid = validated["task_uids"][0]
    task_genealogy = client.get(f"/api/v2/genealogy/task/{task_uid}").json()

    response = client.get(f"/api/v2/genealogy/lot/{task_genealogy['lot_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["lot_id"] == task_genealogy["lot_id"]
    assert body["task_count"] >= 1
    assert task_uid in body["task_uids"]
    command_ids = body["command_ids"]
    assert command_ids
    assert all(command_id.startswith("CMD_") for command_id in command_ids)


def test_digital_twin_state_at_returns_replayable_state_summary():
    _payload, _command, validated = _run_a_cycle()

    response = client.get("/api/v2/digital-twin/state-at", params={"time": 0})

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["requested_time"] == 0
    assert body["state"]["time"] <= 0
    assert body["summary"]["stages"]["A"]["machines"] >= 1
    task_key = str(validated["task_uids"][0])
    assert task_key in body["state"]["tasks"]


def test_reset_clears_stale_genealogy_for_reused_task_ids():
    _run_a_cycle()

    client.post("/api/v2/simulation/reset")
    body = client.get("/api/v2/genealogy/task/0").json()

    assert body["found"] is True
    assert body["assignments"] == []
    assert not any(item["event_type"] == "COMMAND_CREATED" for item in body["timeline"])


def test_control_room_contains_genealogy_page_mount():
    html = client.get("/mes").text

    assert 'href="#genealogy"' in html
    assert 'id="genealogy-page"' in html
    assert 'id="genealogy-task-uid"' in html
    assert 'id="genealogy-ledger-body"' in html
    assert "loadGenealogy" in html
