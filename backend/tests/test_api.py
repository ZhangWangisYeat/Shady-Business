from fastapi.testclient import TestClient
import networkx as nx
from app.main import app

client=TestClient(app)

def test_health_reports_missing_graph_honestly():
    data=client.get('/api/health').json()
    assert data['status']=='ok'
    assert data['dataset_status'] in ('ready','not_loaded')
    assert data['shade_coverage'] in ('unavailable','unverified','verified')


def test_search_royce():
    response=client.get('/api/places',params={'q':'royce'})
    assert response.status_code==200
    assert response.json()['places'][0]['id']=='royce-hall'


def test_bad_coordinate_rejected():
    resp=client.post('/api/routes',json={
        'origin':{'coordinate':[0,0]},'destination':{'place_id':'royce-hall'},
        'departure_time':'2026-10-17T12:00:00-07:00','temperature_c':25})
    assert resp.status_code==422
    assert resp.json()['detail']=={
        'code':'OUTSIDE_SERVICE_AREA',
        'message':'Choose a location inside the UCLA service area.',
        'retryable':False,
        'field':'origin',
    }


def test_unknown_place_identifies_endpoint():
    resp=client.post('/api/routes',json={
        'origin':{'place_id':'missing-place'},'destination':{'place_id':'royce-hall'},
        'departure_time':'2026-10-17T12:00:00-07:00','temperature_c':25})
    assert resp.status_code==404
    assert resp.json()['detail']['code']=='PLACE_NOT_FOUND'
    assert resp.json()['detail']['field']=='origin'


def test_no_graph_not_silent_mock(monkeypatch):
    from app.routing import service
    monkeypatch.setattr(service,'load_graph',lambda:None)
    resp=client.post('/api/routes',json={
        'origin':{'place_id':'royce-hall'},'destination':{'place_id':'powell-library'},
        'departure_time':'2026-10-17T12:00:00-07:00','temperature_c':25})
    assert resp.status_code==503
    assert resp.json()['detail']['code']=='GRAPH_NOT_READY'
    assert resp.json()['detail']['retryable'] is True
    assert resp.headers['retry-after']=='3'


def test_same_snapped_node_has_specific_error(monkeypatch):
    from app.routing import service
    graph=nx.MultiDiGraph()
    graph.add_node('same',x=-118.44,y=34.07)
    monkeypatch.setattr(service,'load_graph',lambda:graph)
    resp=client.post('/api/routes',json={
        'origin':{'coordinate':[-118.44,34.07]},
        'destination':{'coordinate':[-118.440001,34.070001]},
        'departure_time':'2026-10-17T12:00:00-07:00','temperature_c':25})
    assert resp.status_code==422
    assert resp.json()['detail']['code']=='SAME_ENDPOINT'
    assert resp.json()['detail']['field']=='destination'


def test_far_endpoint_has_specific_error(monkeypatch):
    from app.routing import service
    graph=nx.MultiDiGraph()
    graph.add_node('campus',x=-118.44,y=34.07)
    monkeypatch.setattr(service,'load_graph',lambda:graph)
    resp=client.post('/api/routes',json={
        'origin':{'coordinate':[-118.48,34.09]},
        'destination':{'coordinate':[-118.44,34.07]},
        'departure_time':'2026-10-17T12:00:00-07:00','temperature_c':25})
    assert resp.status_code==422
    assert resp.json()['detail']['code']=='SNAP_TOO_FAR'
    assert resp.json()['detail']['field']=='origin'


def test_disconnected_graph_has_specific_error(monkeypatch):
    from app.routing import service
    graph=nx.MultiDiGraph()
    graph.add_node('start',x=-118.44,y=34.07)
    graph.add_node('end',x=-118.441,y=34.071)
    monkeypatch.setattr(service,'load_graph',lambda:graph)
    resp=client.post('/api/routes',json={
        'origin':{'coordinate':[-118.44,34.07]},
        'destination':{'coordinate':[-118.441,34.071]},
        'departure_time':'2026-10-17T12:00:00-07:00','temperature_c':25})
    assert resp.status_code==422
    assert resp.json()['detail']['code']=='NO_WALKABLE_PATH'


def test_shade_dataset_failure_keeps_real_fastest_route(monkeypatch):
    from app.routing import service
    from app.shade.model import ShadeDataUnavailable
    graph=nx.MultiDiGraph()
    graph.add_node('start',x=-118.44,y=34.07)
    graph.add_node('end',x=-118.441,y=34.071)
    graph.add_edge('start','end',key='walk',length=150.)
    monkeypatch.setattr(service,'load_graph',lambda:graph)
    monkeypatch.setattr(service,'load_model',lambda:(_ for _ in ()).throw(
        ShadeDataUnavailable('bad local data')))
    resp=client.post('/api/routes',json={
        'origin':{'coordinate':[-118.44,34.07]},
        'destination':{'coordinate':[-118.441,34.071]},
        'departure_time':'2026-10-17T12:00:00-07:00','temperature_c':25})
    assert resp.status_code==200,resp.text
    data=resp.json()
    assert data['conditions']['shade_model']=='unavailable'
    assert data['conditions']['shade_coverage']=='unavailable'
    assert any('could not be loaded' in note for note in data['conditions']['model_limitations'])
    assert [route['mode'] for route in data['routes']]==['fastest','recommended','maximum_shade']
    assert data['routes'][1]['same_as']=='fastest-01'
    assert data['routes'][2]['same_as']=='fastest-01'
    assert all(route['sun_seconds'] is None for route in data['routes'])


def test_openapi_publishes_g2_g3_route_contract():
    schemas=client.get('/openapi.json').json()['components']['schemas']
    route=schemas['RouteResponseItem']['properties']
    conditions=schemas['Conditions']['properties']
    assert 'coverage_fraction' in route
    assert 'coverage_fraction' not in schemas['RouteSegment']['properties']
    assert {'shade_coverage','solar_status'} <= conditions.keys()
