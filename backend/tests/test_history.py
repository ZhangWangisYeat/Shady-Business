"""Offline history contract checks; route results here are explicit test fixtures."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import main
from app.api.schemas import RouteRequest, RoutesResponse
from app.routing import history


@pytest.fixture
def setup_history(tmp_path, monkeypatch):
    monkeypatch.setenv('ROUTE_HISTORY_DB', str(tmp_path / 'history.sqlite3'))
    calls = []

    def calculate(origin, destination, when, temperature):
        calls.append((origin, destination))
        return RoutesResponse(conditions={
            'temperature_c': temperature, 'shade_coverage': 'unavailable',
            'solar_status': 'unavailable', 'model_limitations': ['Test fixture'],
        }, routes=[])

    monkeypatch.setattr(main, 'build_routes', calculate)
    return TestClient(main.app), {'X-Route-History-Key': str(uuid4())}, calls


def query(origin='royce-hall', destination='ackerman-union', temperature=25):
    return {'origin': {'place_id': origin}, 'destination': {'place_id': destination},
            'departure_time': '2026-10-17T12:00:00-07:00', 'temperature_c': temperature}


def test_snapshot_replay_never_recalculates_and_preserves_original_conditions(setup_history):
    client, headers, calls = setup_history
    calculated = client.post('/api/routes', headers=headers, json=query())
    assert calculated.status_code == 200
    assert calculated.headers['X-Route-History-Saved'] == 'true'
    listing = client.get('/api/routes/history', headers=headers)
    assert listing.headers['cache-control'] == 'no-store'
    item = listing.json()['items'][0]
    assert item['result'] == calculated.json()
    assert item['request'] == RouteRequest.model_validate(query()).model_dump(mode='json')
    assert item['is_historical'] is True
    assert item['saved_at'].endswith('Z')
    # A fresh client/connection still reads the same persisted SQLite snapshot.
    replay = TestClient(main.app).get('/api/routes/history/' + item['id'], headers=headers)
    assert replay.status_code == 200
    assert replay.json() == item
    assert len(calls) == 1


def test_five_distinct_searches_repeated_pair_updates_and_eviction(setup_history):
    client, headers, _ = setup_history
    pairs = [('royce-hall', 'ackerman-union'), ('ackerman-union', 'royce-hall'),
             ('royce-hall', 'powell-library'), ('powell-library', 'ackerman-union'),
             ('bruin-plaza', 'royce-hall'), ('royce-hall', 'bruin-plaza')]
    ids = []
    for origin, destination in pairs:
        assert client.post('/api/routes', headers=headers, json=query(origin, destination)).status_code == 200
        ids.append(client.get('/api/routes/history', headers=headers).json()['items'][0]['id'])
    items = client.get('/api/routes/history', headers=headers).json()['items']
    assert [item['id'] for item in items] == ids[:0:-1]
    assert client.get('/api/routes/history/' + ids[0], headers=headers).status_code == 404
    client.post('/api/routes', headers=headers, json=query(*pairs[1], temperature=30))
    items = client.get('/api/routes/history', headers=headers).json()['items']
    assert len(items) == 5
    assert items[0]['request']['temperature_c'] == 30
    assert items[0]['request']['origin']['place_id'] == pairs[1][0]
    assert client.get('/api/routes/history/' + ids[1], headers=headers).status_code == 404


def test_device_isolation_validation_and_no_implicit_shared_history(setup_history):
    client, headers, _ = setup_history
    client.post('/api/routes', headers=headers, json=query())
    entry = client.get('/api/routes/history', headers=headers).json()['items'][0]
    other = {'X-Route-History-Key': str(uuid4())}
    assert client.get('/api/routes/history', headers=other).json() == {'items': []}
    assert client.get('/api/routes/history/' + entry['id'], headers=other).status_code == 404
    assert client.get('/api/routes/history').status_code == 422
    assert client.get('/api/routes/history', headers={'X-Route-History-Key': 'invalid'}).status_code == 422
    client.post('/api/routes', json=query('ackerman-union', 'royce-hall'))
    assert len(client.get('/api/routes/history', headers=headers).json()['items']) == 1


def test_gps_and_failed_queries_never_persist(setup_history):
    client, headers, _ = setup_history
    body = query()
    body['origin'] = {'coordinate': [-118.4422, 34.0728]}
    response = client.post('/api/routes', headers=headers, json=body)
    assert response.status_code == 200
    assert response.headers['X-Route-History-Saved'] == 'false'
    assert client.post('/api/routes', headers=headers, json=query('missing')).status_code == 404
    assert client.get('/api/routes/history', headers=headers).json() == {'items': []}


def test_gps_routes_save_only_behind_the_test_switch(setup_history, monkeypatch):
    client, headers, _ = setup_history
    monkeypatch.setenv('ROUTE_HISTORY_INCLUDE_GPS', '1')
    for spot in ([-118.4422, 34.0728], [-118.4430, 34.0725]):
        body = query()
        body['origin'] = {'coordinate': spot}
        response = client.post('/api/routes', headers=headers, json=body)
        assert response.headers['X-Route-History-Saved'] == 'true'
    items = client.get('/api/routes/history', headers=headers).json()['items']
    # both walks start at "your location", so the second replaces the first
    assert len(items) == 1
    assert items[0]['request']['origin'] == {'place_id': None, 'coordinate': [-118.443, 34.0725]}


def test_storage_failure_preserves_route_and_returns_structured_read_error(setup_history, monkeypatch):
    client, headers, _ = setup_history

    def unavailable(*args):
        raise OSError('Test storage failure')

    monkeypatch.setattr(history, 'save', unavailable)
    response = client.post('/api/routes', headers=headers, json=query())
    assert response.status_code == 200
    assert response.headers['X-Route-History-Saved'] == 'false'
    monkeypatch.setattr(history, 'read', unavailable)
    response = client.get('/api/routes/history', headers=headers)
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'HISTORY_UNAVAILABLE'


def test_concurrent_writes_keep_five_snapshots_and_do_not_store_private_key(setup_history):
    from concurrent.futures import ThreadPoolExecutor
    import os
    import sqlite3

    client, headers, _ = setup_history
    key = headers['X-Route-History-Key']
    client.post('/api/routes', headers=headers, json=query())
    result = history.read(key)[0].result
    places = ['royce-hall', 'ackerman-union', 'powell-library', 'bruin-plaza']
    requests = [RouteRequest.model_validate(query(a, b)) for a in places for b in places if a != b]
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(lambda body: history.save(key, body, result), requests))
    items = history.read(key)
    assert len(items) == 5
    assert len({(item.request.origin.place_id, item.request.destination.place_id) for item in items}) == 5
    with sqlite3.connect(os.environ['ROUTE_HISTORY_DB']) as connection:
        assert connection.execute('SELECT COUNT(*) FROM route_history').fetchone()[0] == 5
        assert all(row[0] != key for row in connection.execute('SELECT owner FROM route_history'))
