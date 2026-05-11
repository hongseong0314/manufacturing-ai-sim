from mes_api_support import client


def test_assignment_trace_lookup_by_equipment_and_task_returns_full_layer_chain():
    run = client.post('/api/v2/harness/run-cycle', json={'target_stage': 'A'}).json()
    command = run['command']
    validated = command['validated_command']

    response = client.get(
        '/api/v2/assignment-trace',
        params={
            'equipment_id': validated['equipment_id'],
            'task_uid': validated['task_uids'][0],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['found'] is True
    assert payload['assignment']['correlation_id'] == command['correlation_id']
    assert payload['assignment']['equipment_id'] == validated['equipment_id']
    assert validated['task_uids'][0] in payload['assignment']['task_uids']
    assert payload['task_snapshots']
    assert payload['machine_snapshot']['status'] in {'idle', 'busy'}
    assert payload['simulator_action']
    for layer in ('L4', 'L3', 'L1', 'L2', 'RULE_ENGINE', 'COMMAND'):
        assert layer in payload['layers']
    assert payload['layers']['L1']['recommended_action']['candidate_id'] == validated['candidate_id']
    assert payload['layers']['L2']['recommended_action']['candidate_id'] == validated['candidate_id']
    assert payload['layers']['RULE_ENGINE']['validation_status'] == 'PASSED'
    assert payload['layers']['COMMAND']['command_id'] == command['command_id']


def test_assignment_trace_includes_selected_and_rejected_portfolio_rows():
    run = client.post('/api/v2/harness/run-cycle', json={'target_stage': 'A'}).json()
    candidate_id = run['command']['validated_command']['candidate_id']

    payload = client.get(
        '/api/v2/assignment-trace',
        params={'candidate_id': candidate_id},
    ).json()

    assert payload['found'] is True
    items = payload['candidate_portfolio']['items']
    assert any(item['selected'] for item in items)
    assert any(not item['selected'] for item in items)
    assert payload['assignment']['candidate_id'] == candidate_id


def test_assignment_trace_missing_task_returns_found_false():
    response = client.get(
        '/api/v2/assignment-trace',
        params={'equipment_id': 'A_0', 'task_uid': 999999},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['found'] is False
    assert payload['reason'] == 'NO_MATCHING_COMMAND'


def test_gantt_bars_include_assignment_trace_keys_after_execution():
    run = client.post('/api/v2/harness/run-cycle', json={'target_stage': 'A'}).json()
    command = run['command']
    validated = command['validated_command']

    gantt = client.get('/api/v2/gantt').json()
    bars = [
        bar for bar in gantt['bars']
        if bar['machine_id'] == validated['equipment_id']
        and validated['task_uids'][0] in (bar.get('batch_task_uids') or bar.get('task_uids') or [])
    ]

    assert bars
    assert any(bar.get('correlation_id') == command['correlation_id'] for bar in bars)
    assert any(bar.get('command_id') == command['command_id'] for bar in bars)
    assert any(bar.get('candidate_id') == validated['candidate_id'] for bar in bars)
