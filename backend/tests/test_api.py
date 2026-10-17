from fastapi.testclient import TestClient
from app.main import app

client=TestClient(app)

def test_health_reports_missing_graph_honestly():
    data=client.get('/api/health').json()
    assert data['status']=='ok'
    assert data['dataset_status'] in ('ready','not_loaded')


def test_search_royce():
    response=client.get('/api/places',params={'q':'royce'})
    assert response.status_code==200
    assert response.json()['places'][0]['id']=='royce-hall'


def test_bad_coordinate_rejected():
    resp=client.post('/api/routes',json={
        'origin':{'coordinate':[0,0]},'destination':{'place_id':'royce-hall'},
        'departure_time':'2026-10-17T12:00:00-07:00','temperature_c':25})
    assert resp.status_code==422


def test_no_graph_not_silent_mock():
    from app.routing.graph import load_graph
    if load_graph() is not None: return
    resp=client.post('/api/routes',json={
        'origin':{'place_id':'royce-hall'},'destination':{'place_id':'powell-library'},
        'departure_time':'2026-10-17T12:00:00-07:00','temperature_c':25})
    assert resp.status_code==503
