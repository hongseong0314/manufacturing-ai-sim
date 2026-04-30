from fastapi.testclient import TestClient

from src.mes.api import app


client = TestClient(app)


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
