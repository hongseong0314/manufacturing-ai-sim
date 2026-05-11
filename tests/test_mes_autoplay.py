from mes_api_support import client, reset_simulation_between_tests


def test_machine_counts_and_live():
    live = client.get('/api/v2/fab/live')
    assert live.status_code == 200
    body = live.json()
    assert len(body['stages']['A']['machines']) == 5
    assert len(body['stages']['B']['machines']) == 3
    assert len(body['stages']['C']['machines']) == 3
    assert {machine['batch_size'] for machine in body['stages']['A']['machines']} == {3}
    assert {machine['batch_size'] for machine in body['stages']['B']['machines']} == {2}


def test_autoplay_start_and_status_step():
    s = client.post(
        '/api/v2/simulation/autoplay/start',
        json={'target_stage': 'A', 'generate_every': 5, 'bootstrap_cycles': 1},
    )
    assert s.status_code == 200
    st = client.get('/api/v2/simulation/autoplay/status?step_cycles=3')
    assert st.status_code == 200
    b = st.json()
    assert b['enabled'] is True
    assert b['stepped_cycles'] == 3
    stop = client.post('/api/v2/simulation/autoplay/stop')
    assert stop.status_code == 200
    assert stop.json()['enabled'] is False


def test_auto_cycle_dispatches_across_idle_a_equipment():
    client.post('/api/v2/simulation/reset')
    run = client.post('/api/v2/harness/run-cycle', json={'target_stage': 'AUTO'})
    assert run.status_code == 200

    payload = run.json()
    a_actions = payload['combined_actions']['A']
    assert len(a_actions) > 1
    assert sorted(a_actions)[:3] == ['A_0', 'A_1', 'A_2']
    assert payload['count'] >= len(a_actions)


def test_auto_cycle_uses_l3_budget_plan_for_parallel_dispatch():
    client.post('/api/v2/simulation/reset')
    run = client.post('/api/v2/harness/run-cycle', json={'target_stage': 'AUTO'})
    assert run.status_code == 200

    payload = run.json()
    budget_plan = payload['budget_plan']
    selected_ids = budget_plan['selected_candidate_ids']

    assert payload['selection_source'] == 'l3_budget_plan'
    assert budget_plan['dispatch_budgets']['A'] == len(payload['combined_actions']['A'])
    assert budget_plan['constraints']['max_commands_per_cycle'] == len(selected_ids)
    assert payload['count'] == len(selected_ids)


def test_auto_cycle_exposes_full_budget_candidate_portfolio_as_latest():
    client.post('/api/v2/simulation/reset')
    run = client.post('/api/v2/harness/run-cycle', json={'target_stage': 'AUTO'})
    assert run.status_code == 200

    payload = run.json()
    portfolio = client.get('/api/v2/candidate-portfolio/latest').json()

    assert portfolio['correlation_id'] == payload['budget_correlation_id']
    assert portfolio['count'] >= payload['count']
    assert portfolio['summary']['stage_counts']['A'] >= payload['count']
    assert portfolio['summary']['rejected_count'] > 0


def test_latest_candidate_portfolio_prefers_last_actionable_over_empty_cycle():
    client.post('/api/v2/simulation/reset')
    first = client.post('/api/v2/harness/run-cycle', json={'target_stage': 'AUTO'}).json()
    second = client.post('/api/v2/harness/run-cycle', json={'target_stage': 'AUTO'}).json()

    latest = client.get('/api/v2/candidate-portfolio/latest').json()
    empty = client.get(
        f"/api/v2/candidate-portfolio/{second['budget_correlation_id']}"
    ).json()

    assert latest['kind'] == 'ACTIONABLE'
    assert latest['is_actionable'] is True
    assert latest['correlation_id'] == first['budget_correlation_id']
    assert latest['last_actionable_correlation_id'] == first['budget_correlation_id']
    assert latest['latest_empty_correlation_id'] == second['budget_correlation_id']
    assert empty['kind'] == 'EMPTY'
    assert empty['is_actionable'] is False
    assert empty['empty_reason'] in {
        'ALL_EQUIPMENT_BUSY',
        'NO_ELIGIBLE_CANDIDATES',
        'NO_WAIT_POOL',
        'BATCH_NOT_READY',
        'RULE_INELIGIBLE',
    }
    assert empty['diagnostics']['stages']['A']['idle_machines'] == 0


def test_mes_screen_serves_live_control_room():
    r = client.get('/mes')
    assert r.status_code == 200
    assert 'Fab Control Room' in r.text
    assert '/api/v2/fab/live' in r.text
    assert '/api/v2/gantt' in r.text
    assert '/api/v2/equipment/${equipmentId}/detail' in r.text
    assert 'Global Gantt' in r.text
    assert 'Machine Detail' in r.text
    assert 'packing composition quality' in r.text
    assert 'Candidate Portfolio' in r.text
    assert 'Budget Plan' in r.text
    assert 'selectable-gantt-bar' in r.text
    assert 'data-machine-id' in r.text
    assert 'openAssignmentTraceFromBar(bar)' in r.text
    assert 'data-correlation-id' in r.text
    assert 'Assignment Trace Inspector' in r.text
    assert '["A", "B", "C"].includes(String(eq.stage || "").toUpperCase())' in r.text


def test_auto_mode_moves_tasks_through_completed_flow():
    client.post('/api/v2/simulation/reset')
    client.post(
        '/api/v2/simulation/autoplay/start',
        json={'target_stage': 'AUTO', 'generate_every': 20, 'bootstrap_cycles': 0},
    )
    live = {}
    for _ in range(35):
        live = client.get(
            '/api/v2/simulation/autoplay/status?step_cycles=1'
        ).json()['live']
    assert live['time'] >= 35
    assert live['kpis']['completed'] > 0
    assert live['kpis']['total_wip'] >= 0
    assert live['active_chain']['counts']['recommendations'] >= 4
