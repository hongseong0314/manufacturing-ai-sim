from fastapi.testclient import TestClient
import pytest

from src.mes.api import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_simulation_between_tests():
    client.post('/api/v2/simulation/reset')
    yield


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


def test_v2_run_until_stops_with_max_cycles_or_conditions():
    r = client.post('/api/v2/harness/run-until', json={'target_stage': 'A', 'max_cycles': 2})
    assert r.status_code == 200
    body = r.json()
    assert body['count'] <= 2
    assert body['stop_reason'] in ('max_cycles', 'rejected', 'no_candidates')
    assert len(body['cycles']) == body['count']


def test_v2_equipment_detail_exposes_a_b_quality_trends():
    client.post(
        '/api/v2/simulation/autoplay/start',
        json={'target_stage': 'AUTO', 'generate_every': 20, 'bootstrap_cycles': 0},
    )
    client.get('/api/v2/simulation/autoplay/status?step_cycles=70')

    for equipment_id, stage in (('A_0', 'A'), ('B_0', 'B')):
        r = client.get(f'/api/v2/equipment/{equipment_id}/detail')
        assert r.status_code == 200
        body = r.json()
        assert body['equipment_id'] == equipment_id
        assert body['stage'] == stage
        assert body['process_label']
        assert body['kpis']['processed'] > 0
        assert 0.0 <= body['kpis']['yield_rate'] <= 1.0
        assert body['quality_series']

        point = body['quality_series'][0]
        assert point['time'] >= 0
        assert point['quality'] > 0
        assert point['task_uids']
        assert point['recipe']
        assert point['material_state']['primary_key'] in ('u', 'v')
        assert 'target_window' in point


def test_v2_equipment_detail_exposes_c_pack_composition():
    client.post('/api/v2/simulation/reset')
    client.post(
        '/api/v2/simulation/autoplay/start',
        json={'target_stage': 'AUTO', 'generate_every': 20, 'bootstrap_cycles': 0},
    )
    client.get('/api/v2/simulation/autoplay/status?step_cycles=90')

    r = client.get('/api/v2/equipment/C_0/detail')

    assert r.status_code == 200
    body = r.json()
    assert body['equipment_id'] == 'C_0'
    assert body['stage'] == 'C'
    assert body['process_label'] == 'Packing / Material Compatibility'
    assert body['kpis']['packed_tasks'] > 0
    assert body['kpis']['packs_completed'] > 0
    assert 0.0 <= body['kpis']['avg_compatibility'] <= 1.0
    assert body['pack_series']

    pack = body['pack_series'][0]
    assert pack['task_uids']
    assert pack['material_counts']
    assert pack['color_counts']
    assert set(pack['material_counts']).issubset({'plastic', 'metal', 'composite'})
    assert set(pack['color_counts']).issubset({'red', 'blue', 'green'})
    assert 0.0 <= pack['avg_compatibility'] <= 1.0
    expected_quality = (
        (
            max(pack['material_counts'].values())
            + max(pack['color_counts'].values())
        )
        / (2 * len(pack['task_uids']))
    ) * 100
    assert pack['quality'] == expected_quality
    assert 'composition_label' in pack
