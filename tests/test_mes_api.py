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


def test_v2_run_until_stops_with_max_cycles_or_conditions():
    r = client.post('/api/v2/harness/run-until', json={'target_stage': 'A', 'max_cycles': 2})
    assert r.status_code == 200
    body = r.json()
    assert body['count'] <= 2
    assert body['stop_reason'] in ('max_cycles', 'rejected', 'no_candidates')
    assert len(body['cycles']) == body['count']
