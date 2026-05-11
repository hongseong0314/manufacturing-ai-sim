from mes_api_support import client, reset_simulation_between_tests


def test_health():
    r = client.get('/health')
    assert r.status_code == 200
    assert r.json()['status'] == 'ok'


def test_control_room_exposes_simulation_reset_button():
    r = client.get('/mes')

    assert r.status_code == 200
    html = r.text
    assert 'id="reset"' in html
    assert 'Reset' in html
    assert '/api/v2/simulation/reset' in html


def test_harness_run_and_read_back_chain():
    run = client.post('/api/v1/harness/run?target_stage=A')
    assert run.status_code == 200
    payload = run.json()
    corr = payload['generated']['plan']['correlation_id']

    rec = client.get(f'/api/v1/ai/recommendations?correlation_id={corr}')
    ev = client.get(f'/api/v1/events?correlation_id={corr}')
    assert rec.status_code == 200
    assert ev.status_code == 200
    assert rec.json()['count'] >= 4
    assert ev.json()['count'] >= 5


def test_kpi_wip_equipment_endpoints():
    for endpoint in ('/api/v1/kpis/fab', '/api/v1/wip', '/api/v1/equipment'):
        r = client.get(endpoint)
        assert r.status_code == 200
        body = r.json()
        assert 'time' in body


def test_runtime_entity_endpoints_are_store_backed():
    client.post('/api/v2/tasks/generate', json={'time_point': 120})

    lots = client.get('/api/v1/lots').json()
    wafers = client.get('/api/v1/wafers').json()
    equipment = client.get('/api/v1/equipment').json()
    recipes = client.get('/api/v1/recipes').json()

    assert lots['count'] > 0
    assert wafers['count'] >= lots['count']
    assert equipment['count'] == 11
    assert recipes['count'] >= 3
    assert {item['recipe_id'] for item in recipes['items']} >= {
        'SIM_A_BASE',
        'SIM_B_DEFAULT',
        'SIM_C_NO_RECIPE',
    }

def test_harness_run_rejected_stage_has_validation_and_no_command():
    run = client.post('/api/v1/harness/run?target_stage=B')
    assert run.status_code == 200
    payload = run.json()

    assert payload['evaluation']['status'] == 'REJECTED'
    assert payload['command'] is None
    assert payload['generated']['validation']['validation_status'] == 'REJECTED'
    assert (
        payload['generated']['validation']['correlation_id']
        == payload['generated']['plan']['correlation_id']
    )


def test_dispatch_candidates_endpoint():
    r = client.get('/api/v1/dispatch/candidates?stage=A')
    assert r.status_code == 200
    body = r.json()
    assert body['stage'] == 'A'
    assert 'items' in body
    assert 'count' in body


def test_rules_validate_endpoint_rule_gate_rejects_invalid():
    payload = {
        'recommendations': [
            {
                'recommendation_id': 'REC_BAD',
                'recommendation_type': 'DISPATCH',
                'layer_id': 'L1',
                'objective_id': 'OBJ_RULE_ONLY_BALANCED',
                'policy_id': 'TEST',
                'model_id': 'test',
                'model_version': '0.0',
                'feature_snapshot_id': 'FS_TEST',
                'correlation_id': 'CORR_TEST',
                'recommended_action': {
                    'stage': 'A',
                    'equipment_id': 'A_999',
                    'task_uids': [999999],
                },
            }
        ]
    }
    r = client.post('/api/v1/rules/validate', json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body['validation_status'] == 'REJECTED'
    assert body['validated_command'] == {}


def test_track_in_preview_and_execute_endpoints():
    preview = client.post('/api/v1/commands/track-in/preview', json={'target_stage': 'A'})
    assert preview.status_code == 200
    p = preview.json()
    assert 'generated' in p
    assert p['generated']['validation']['validation_status'] in ('PASSED', 'REJECTED')

    execute = client.post('/api/v1/commands/track-in/execute', json={'target_stage': 'A'})
    assert execute.status_code == 200
    e = execute.json()
    assert 'generated' in e
    assert e['generated']['validation']['validation_status'] in ('PASSED', 'REJECTED')
    if e['generated']['validation']['validation_status'] == 'PASSED':
        assert e['command'] is not None
    if e['evaluation']['status'] == 'PASSED' and e['command'] is not None:
        assert e['step_result'] is not None


def test_v2_generate_tasks_by_time_point():
    before = client.get('/api/v1/wip').json()
    r = client.post('/api/v2/tasks/generate', json={'time_point': 120})
    assert r.status_code == 200
    body = r.json()
    assert body['time_point'] == 120
    assert body['inserted_count'] == 40
    assert len(body['task_uids']) == 40
    assert body['queue_a_size'] >= 40


def test_v2_run_cycle_and_decision_chain_aggregation():
    run = client.post('/api/v2/harness/run-cycle', json={'target_stage': 'A'})
    assert run.status_code == 200
    payload = run.json()
    corr = payload['generated']['plan']['correlation_id']

    chain = client.get(f'/api/v2/decision-chain/{corr}')
    assert chain.status_code == 200
    c = chain.json()
    assert c['correlation_id'] == corr
    assert c['counts']['recommendations'] >= 4
    assert c['counts']['events'] >= 5
    assert c['counts']['validations'] >= 1
    trace = c['traceability']
    assert trace['objective_id']
    assert trace['l4_policy_id'] == 'L4_CYCLE_WEIGHT_RULE'
    assert trace['l3_policy_id'] == 'L3_CANDIDATE_PORTFOLIO_RULE'
    assert trace['selected_candidate_id']
    assert trace['dispatch_budgets']
    assert trace['candidate_count'] >= 1
    assert trace['selected_candidates']
    assert trace['l2_annotation_count'] >= 1
    assert trace['command']['equipment_id']


def test_candidate_portfolio_latest_api_returns_selected_and_rejected_candidates():
    run = client.post('/api/v2/harness/run-cycle', json={'target_stage': 'A'})
    assert run.status_code == 200

    response = client.get('/api/v2/candidate-portfolio/latest')

    assert response.status_code == 200
    payload = response.json()
    assert payload['correlation_id']
    assert payload['count'] >= 1
    assert any(item['selected'] for item in payload['items'])
    assert any(not item['selected'] for item in payload['items'])
    assert all('l2_annotation' in item for item in payload['items'])
    assert all('upper_score' in item for item in payload['items'])
    assert payload['summary']['selected_count'] >= 1
    assert payload['summary']['rejected_count'] >= 1


def test_candidate_portfolio_api_can_read_by_correlation_id():
    run = client.post('/api/v2/harness/run-cycle', json={'target_stage': 'A'}).json()
    corr = run['generated']['plan']['correlation_id']

    response = client.get(f'/api/v2/candidate-portfolio/{corr}')

    assert response.status_code == 200
    payload = response.json()
    assert payload['correlation_id'] == corr
    assert payload['items']
    assert payload['summary']['l3_policy_id'] == 'L3_CANDIDATE_PORTFOLIO_RULE'


def test_decision_chain_includes_candidate_portfolio_summary():
    run = client.post('/api/v2/harness/run-cycle', json={'target_stage': 'A'}).json()
    corr = run['generated']['plan']['correlation_id']

    payload = client.get(f'/api/v2/decision-chain/{corr}').json()

    assert payload['portfolio_summary']['count'] >= 1
    assert payload['portfolio_summary']['selected_count'] >= 1
    assert 'rejected_count' in payload['portfolio_summary']


def test_control_room_html_contains_candidate_portfolio_mount():
    html = client.get('/mes').text

    assert 'id="candidate-portfolio"' in html
    assert 'id="portfolio-stage-filter"' in html
    assert 'id="portfolio-selected-only"' in html
    assert 'id="portfolio-stage-counts"' in html
    assert 'body.portfolio-page .layout > section:not(#candidate-portfolio)' in html
    assert 'word-break: keep-all' in html


def test_ai_dev_policy_stack_endpoint_exposes_active_policy_ids():
    response = client.get('/api/v2/ai-dev/policy-stack')

    assert response.status_code == 200
    payload = response.json()
    assert payload['factory_name'] == 'build_mes_policy_stack'
    assert payload['l1_policy_id'] == 'L1_FIFO_BASELINE'
    assert payload['l2_policy_id'] == 'L2_RULE_BASED_APC'
    assert payload['l3_policy_id'] == 'L3_CANDIDATE_PORTFOLIO_RULE'
    assert payload['l4_policy_id'] == 'L4_CYCLE_WEIGHT_RULE'
    assert payload['config']['scheduler_A'] == 'fifo'
    assert payload['config']['tuner_A'] == 'rule-based'
    assert payload['layers']['L3']['model_id'] == 'candidate-portfolio-meta-scheduler'


def test_ai_dev_decision_cycles_endpoint_lists_correlation_rows():
    run = client.post('/api/v2/harness/run-cycle', json={'target_stage': 'A'}).json()
    corr = run['generated']['plan']['correlation_id']

    response = client.get('/api/v2/ai-dev/decision-cycles')

    assert response.status_code == 200
    payload = response.json()
    assert payload['count'] >= 1
    rows = {row['correlation_id']: row for row in payload['items']}
    assert corr in rows
    row = rows[corr]
    assert row['candidate_count'] >= 1
    assert row['selected_count'] >= 1
    assert row['validation_status'] == 'PASSED'
    assert row['command_status'] in {'CREATED', 'EXECUTED'}


def test_ai_dev_decision_cycles_endpoint_respects_limit():
    for _ in range(3):
        client.post('/api/v2/harness/run-cycle', json={'target_stage': 'A'})

    payload = client.get('/api/v2/ai-dev/decision-cycles?limit=2').json()

    assert payload['count'] == 2
    assert len(payload['items']) == 2


def test_ai_dev_candidate_portfolio_endpoint_includes_score_and_l2_details():
    run = client.post('/api/v2/harness/run-cycle', json={'target_stage': 'A'}).json()
    corr = run['generated']['plan']['correlation_id']

    response = client.get(f'/api/v2/ai-dev/candidate-portfolio/{corr}')

    assert response.status_code == 200
    payload = response.json()
    assert payload['correlation_id'] == corr
    assert payload['items']
    candidate = payload['items'][0]
    assert 'score_components' in candidate
    assert 'final_upper_score' in candidate['score_components']
    assert 'quality_risk_penalty' in candidate['score_components']
    assert 'l2_annotation' in candidate
    assert payload['objective_weights']


def test_control_room_html_contains_ai_dev_console_mount():
    html = client.get('/mes').text

    assert 'href="#ai-dev"' in html
    assert 'id="ai-dev-console"' in html
    assert 'id="ai-dev-policy-stack"' in html
    assert 'id="ai-dev-cycle-body"' in html
    assert 'id="ai-dev-portfolio-body"' in html
    assert 'id="ai-dev-candidate-detail"' in html
    assert 'cycle-table-wrap' in html
    assert 'policy-layer-detail' in html
    assert 'AI_DEV_CYCLE_LIMIT = 25' in html


def test_v2_run_until_stops_with_max_cycles_or_conditions():
    r = client.post('/api/v2/harness/run-until', json={'target_stage': 'A', 'max_cycles': 2})
    assert r.status_code == 200
    body = r.json()
    assert body['count'] <= 2
    assert body['stop_reason'] in ('max_cycles', 'rejected', 'no_candidates')
    assert len(body['cycles']) == body['count']
