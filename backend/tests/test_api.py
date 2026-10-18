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


def test_route_from_raw_gps_coordinate():
    # the app's default start is wherever the phone is, which is a coordinate
    # that usually isn't any catalog place, so this path has to keep working.
    from app.routing.graph import load_graph
    if load_graph() is None: return
    resp=client.post('/api/routes',json={
        'origin':{'coordinate':[-118.4426,34.0722]},'destination':{'place_id':'ackerman-union'},
        'departure_time':'2026-10-17T12:00:00-07:00','temperature_c':25})
    assert resp.status_code==200
    route=resp.json()['routes'][0]
    assert route['distance_m']>0 and route['steps'][-1]['maneuver']=='arrive'
