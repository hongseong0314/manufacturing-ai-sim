from fastapi.testclient import TestClient
from src.mes.api import app

client = TestClient(app)


def test_machine_counts_and_live():
    live = client.get('/api/v2/fab/live')
    assert live.status_code == 200
    body = live.json()
    assert len(body['stages']['A']['machines']) == 10
    assert len(body['stages']['B']['machines']) == 5
    assert len(body['stages']['C']['machines']) == 3


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


def test_mes_screen_serves_live_control_room():
    r = client.get('/mes')
    assert r.status_code == 200
    assert 'Fab Control Room' in r.text
    assert '/api/v2/fab/live' in r.text


def test_auto_mode_moves_tasks_through_completed_flow():
    client.post('/api/v2/simulation/reset')
    client.post(
        '/api/v2/simulation/autoplay/start',
        json={'target_stage': 'AUTO', 'generate_every': 20, 'bootstrap_cycles': 0},
    )
    live = {}
    for _ in range(20):
        live = client.get(
            '/api/v2/simulation/autoplay/status?step_cycles=1'
        ).json()['live']
    assert live['time'] >= 20
    assert live['kpis']['completed'] > 0
    assert live['kpis']['total_wip'] >= 0
    assert live['active_chain']['counts']['recommendations'] >= 4
