from mes_api_support import client, reset_simulation_between_tests


def test_gantt_endpoint_exposes_flow_and_stage_schedule():
    client.post('/api/v2/simulation/reset')
    initial = client.get('/api/v2/gantt')
    assert initial.status_code == 200
    body = initial.json()
    assert [item['stage'] for item in body['flow']] == ['A', 'B', 'C']
    assert body['horizon']['end'] > body['horizon']['start']
    planned_a = next(
        bar for bar in body['bars']
        if bar['stage'] == 'A' and bar['status'] == 'planned'
    )
    assert planned_a['duration'] == 20
    assert planned_a['label'].startswith('Next T')

    client.post('/api/v2/harness/run-cycle', json={'target_stage': 'AUTO'})
    active = client.get('/api/v2/gantt').json()
    assert active['time'] >= 1
    assert active['stage_views']['A']['rows']
    assert any(
        bar['source'] == 'event_log' and bar['stage'] == 'A'
        for bar in active['stage_views']['A']['bars']
    )


def test_v2_control_room_traceability_links_chain_gantt_and_equipment():
    run = client.post('/api/v2/harness/run-cycle', json={'target_stage': 'AUTO'})
    assert run.status_code == 200
    payload = run.json()
    assert payload['cycles']
    assert all(cycle['evaluation']['status'] == 'PASSED' for cycle in payload['cycles'])

    live = client.get('/api/v2/fab/live')
    assert live.status_code == 200
    active_chain = live.json()['active_chain']
    trace = active_chain['traceability']
    equipment_id = trace['command']['equipment_id']

    assert active_chain['counts']['commands'] >= 1
    assert trace['selected_candidates']
    assert trace['final_l1_action']['candidate_id'] == trace['selected_candidate_id']
    assert trace['final_l2_action']['candidate_id'] == trace['selected_candidate_id']

    gantt = client.get('/api/v2/gantt')
    assert gantt.status_code == 200
    bars = gantt.json()['bars']
    assert any(bar['machine_id'] == equipment_id for bar in bars)

    detail = client.get(f'/api/v2/equipment/{equipment_id}/detail')
    assert detail.status_code == 200
    assert detail.json()['equipment_id'] == equipment_id


def test_gantt_window_and_a_apc_prevent_rework_wall():
    client.post('/api/v2/simulation/reset')
    client.post(
        '/api/v2/simulation/autoplay/start',
        json={'target_stage': 'AUTO', 'generate_every': 20, 'bootstrap_cycles': 0},
    )
    live = client.get(
        '/api/v2/simulation/autoplay/status?step_cycles=90'
    ).json()['live']

    assert live['time'] >= 90
    assert live['kpis']['yield_proxy'] >= 0.95
    assert live['stages']['A']['rework'] == 0

    gantt = client.get('/api/v2/gantt').json()
    assert gantt['horizon']['start'] > 0
    assert gantt['horizon']['span'] <= 48
    assert gantt['visible_bar_count'] < gantt['total_bar_count']
    assert any(
        bar['stage'] == 'C'
        and bar['task_type'] == 'pack'
        and bar['duration'] == 2
        and bar['stack_size'] > 1
        for bar in gantt['bars']
    )
    assert all(row['machine_id'] != 'C_BUFFER' for row in gantt['rows'])
    assert all(bar['machine_id'] != 'C_BUFFER' for bar in gantt['bars'])
    assert all(
        len(bar.get('batch_task_uids', [])) == 4
        for bar in gantt['bars']
        if bar['stage'] == 'C' and bar['task_type'] == 'pack'
    )
