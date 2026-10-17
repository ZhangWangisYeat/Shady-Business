"""Real OSM edge route calculation; shade is optional and explicitly unknown without vetted data."""
from datetime import datetime
import networkx as nx
from app.routing.graph import load_graph, snap_node, candidate_paths, edge_data, coords_for_edge
from app.routing.policy import Candidate, choose_routes
from app.shade.model import load_model, build_shadow_field
from app.shade.scoring import RouteEdge, score_route
from app.api.schemas import RouteResponseItem, RouteSegment, LineString, Conditions, RoutesResponse

SPEED_MPS=1.3  # constant, not accessibility-adjusted

class GraphUnavailable(Exception): pass
class NoRoute(Exception): pass


def build_routes(origin: tuple[float,float], destination: tuple[float,float], when: datetime, temperature_c: float) -> RoutesResponse:
    graph=load_graph()
    if graph is None: raise GraphUnavailable("No OSM walking graph; run scripts/fetch_ucla_graph.py first")
    source=snap_node(graph,origin); target=snap_node(graph,destination)
    try:
        paths=candidate_paths(graph,source,target)
    except nx.NetworkXNoPath as e:
        raise NoRoute("No connected pedestrian path") from e
    model=load_model()
    field=build_shadow_field(model,when)
    catalog={}
    for path in paths:
        points=[]; segments=[]; total_len=0.; total_sun=0.; total_unknown=0.; total_time=0.
        for u,v in zip(path,path[1:]):
            data=edge_data(graph,u,v)
            dist=float(data['length']); duration=dist/SPEED_MPS
            coords=coords_for_edge(graph,u,v)
            score=score_route([RouteEdge(tuple(coords),duration)],field)
            for part in score.segments:
                # Keep the mobile v0.3 enum. At night exposure is known to be zero
                # but a daytime shade/sun overlay is not applicable.
                state='unknown' if part.shade_state=='no_direct_sun' else part.shade_state
                segments.append(RouteSegment(shade_state=state,duration_s=part.duration_s,
                    sun_seconds=part.sun_seconds,unknown_seconds=part.unknown_seconds,
                    geometry=LineString(coordinates=part.geometry['coordinates'])))
            points += coords if not points else coords[1:]
            total_len += dist; total_time += duration
            total_sun += score.known_sun_seconds
            total_unknown += score.unknown_seconds
        candidate=Candidate(tuple(path),total_time,round(total_sun,4) if total_unknown == 0 else None,total_unknown)
        catalog[candidate.path]=(candidate,points,segments,total_len)
    selected=choose_routes([r[0] for r in catalog.values()],temperature_c)
    items=[]; first_for={}
    for mode,candidate in selected.items():
        c,coords,segments,distance=catalog[candidate.path]
        alias=first_for.get(candidate.path)
        if not alias: first_for[candidate.path]=mode
        items.append(RouteResponseItem(id=f"{mode}-01",mode=mode,same_as=f"{alias}-01" if alias else None,
                  duration_s=round(c.duration_s,2),distance_m=round(distance,2),sun_seconds=c.sun_s,
                  unknown_seconds=round(c.unknown_s,2),optimization_quality=('shortest_time' if mode=='fastest' else 'unavailable' if c.sun_s is None or field.status!='daylight' else 'candidate_search'),
                  geometry=LineString(coordinates=coords),segments=segments))
    return RoutesResponse(conditions=Conditions(temperature_c=temperature_c,
       shade_model='geometry_estimate' if model and field.status=='daylight' else 'unavailable',data_as_of=field.data_as_of,
       model_limitations=list(field.limitations)+['Only real OSM graph paths are shown',
         'Incomplete shade coverage: alternatives may coincide']+
         (['Sun below horizon: no direct sunlight; daytime shade overlay is not applicable'] if field.status=='night' else
          ['No usable shadow dataset loaded; all exposure is unknown'] if model is None else [])), routes=items)
