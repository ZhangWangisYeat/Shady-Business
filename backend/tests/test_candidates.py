import networkx as nx
from shapely.geometry import LineString, box
from shapely.ops import unary_union

from app.routing.candidates import EdgeCost, bounded_edge_refs, candidate_edge_paths, fastest_edge_path
from app.routing.policy import Candidate, choose_routes
from app.shade.model import INVERSE_PROJECTION, PROJECTION, ShadeModel, ShadowField


def fixture_graph():
    graph=nx.MultiDiGraph()
    for node in ("s","fast","balanced","shade","too-long","t"):
        graph.add_node(node,x=-118.44,y=34.07)
    graph.add_edge("s","fast",key="sf",length=300.)
    graph.add_edge("fast","t",key="ft",length=300.)
    graph.add_edge("s","balanced",key="sb",length=330.)
    graph.add_edge("balanced","t",key="bt",length=330.)
    graph.add_edge("s","shade",key="ss",length=435.)
    graph.add_edge("shade","t",key="st",length=435.)
    graph.add_edge("s","too-long",key="sl",length=600.)
    graph.add_edge("too-long","t",key="lt",length=600.)
    return graph


def test_weighted_candidates_feed_three_route_policy_with_hard_cap():
    graph=fixture_graph()
    fastest,duration=fastest_edge_path(graph,"s","t",1.)
    assert duration == 600
    eligible=bounded_edge_refs(graph,"s","t",960,1.)
    assert ("s","too-long","sl") not in eligible
    sun={"sf":240,"ft":240,"sb":105,"bt":105,"ss":17.5,"st":17.5}
    costs={edge:EdgeCost(graph.edges[edge]["length"],sun[edge[2]]) for edge in eligible}
    paths=candidate_edge_paths(costs,"s","t",(0.,1.,2.),per_weight=1)
    candidates=[]
    for path in paths:
        candidates.append(Candidate(path,sum(costs[e].duration_s for e in path),sum(costs[e].sun_s for e in path),0))
    selected=choose_routes(candidates,38)
    assert selected["fastest"].duration_s == 600
    assert selected["recommended"].duration_s == 660
    assert selected["maximum_shade"].duration_s == 870


def test_parallel_edges_keep_the_selected_edge_key():
    graph=nx.MultiDiGraph()
    graph.add_nodes_from(("s","t"))
    graph.add_edge("s","t",key="fast-sunny",length=600.)
    graph.add_edge("s","t",key="slow-shaded",length=650.)
    fastest,_=fastest_edge_path(graph,"s","t",1.)
    assert fastest == (("s","t","fast-sunny"),)
    costs={
        ("s","t","fast-sunny"):EdgeCost(600,500),
        ("s","t","slow-shaded"):EdgeCost(650,0),
    }
    paths=candidate_edge_paths(costs,"s","t",(0.,2.),per_weight=1)
    assert paths == [(("s","t","fast-sunny"),),(("s","t","slow-shaded"),)]


def test_route_api_ignores_unknown_side_branch_when_complete_candidates_exist(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.routing import service

    x,y=PROJECTION.transform(-118.44,34.07)
    metric={
        "s":(x,y), "fast":(x+50,y), "balanced":(x+50,y+30),
        "shade":(x+50,y+60), "too-long":(x+50,y-30),
        "unknown":(x+50,y-80), "t":(x+100,y),
    }
    graph=nx.MultiDiGraph()
    for node,point in metric.items():
        lon,lat=INVERSE_PROJECTION.transform(*point)
        graph.add_node(node,x=lon,y=lat)
    for u,v,key,length in (
        ("s","fast","sf",300.),("fast","t","ft",300.),
        ("s","balanced","sb",330.),("balanced","t","bt",330.),
        ("s","shade","ss",435.),("shade","t","st",435.),
        ("s","too-long","sl",600.),("too-long","t","lt",600.),
        ("s","unknown","su",400.),("unknown","t","ut",400.),
    ):
        graph.add_edge(u,v,key=key,length=length)
    shadows=unary_union((
        LineString((metric["balanced"],metric["t"])).buffer(1),
        LineString((metric["s"],metric["shade"],metric["t"])).buffer(1),
    ))
    field=ShadowField(shadows,box(x-10,y-40,x+110,y+70),"daylight","fixture","synthetic",())
    monkeypatch.setattr(service,"load_graph",lambda:graph)
    monkeypatch.setattr(service,"load_model",lambda:ShadeModel(
        (), "fixture", True, field.coverage_geometry, "synthetic"))
    monkeypatch.setattr(service,"build_shadow_field",lambda model,when:field)
    origin=[graph.nodes["s"]["x"],graph.nodes["s"]["y"]]
    destination=[graph.nodes["t"]["x"],graph.nodes["t"]["y"]]
    response=TestClient(app).post("/api/routes",json={
        "origin":{"coordinate":origin},"destination":{"coordinate":destination},
        "departure_time":"2026-10-17T15:00:00-07:00","temperature_c":38,
    })
    assert response.status_code == 200, response.text
    routes=response.json()["routes"]
    conditions=response.json()["conditions"]
    assert conditions["shade_coverage"] == "verified"
    assert conditions["solar_status"] == "daylight"
    assert not any("Incomplete shade coverage" in note
                   for note in conditions["model_limitations"])
    assert [route["mode"] for route in routes] == ["fastest","recommended","maximum_shade"]
    assert [round(route["duration_s"]) for route in routes] == [462,508,669]
    assert all(route["same_as"] is None for route in routes)
    assert all(route["coverage_fraction"] == 1 for route in routes)
    assert routes[2]["duration_s"] <= min(routes[0]["duration_s"]*1.6,routes[0]["duration_s"]+720)
    assert routes[0]["sun_seconds"] > routes[1]["sun_seconds"] > routes[2]["sun_seconds"]
