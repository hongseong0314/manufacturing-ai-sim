from mes_api_support import client, reset_simulation_between_tests


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
