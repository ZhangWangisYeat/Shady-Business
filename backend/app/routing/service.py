"""Real OSM edge route calculation; shade is optional and explicitly unknown without vetted data."""
from collections import OrderedDict
from datetime import datetime
import networkx as nx
from app.routing.graph import load_graph, snap_node, candidate_paths, edge_data, coords_for_edge
from app.routing.policy import Candidate, choose_routes
from app.shade.model import load_model, shadow_polygons, fraction_sun
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
    shadows=shadow_polygons(model,when) if model else None
    catalog={}
    for path in paths:
        points=[]; segments=[]; total_len=0.; total_sun=0.; total_unknown=0.; total_time=0.
        for u,v in zip(path,path[1:]):
            data=edge_data(graph,u,v)
            dist=float(data['length']); duration=dist/SPEED_MPS
            coords=coords_for_edge(graph,u,v)
            sun_fraction=fraction_sun(shadows,coords)
            # Missing obstruction geometry cannot be interpreted as proof of direct sun.
            verified = bool(model and model.coverage_complete_verified)
            state = 'unknown' if sun_fraction is None else 'shade' if sun_fraction < 0.2 else 'sun' if verified and sun_fraction > 0.8 else 'unknown'
            # A mixed edge cannot be labeled as uniformly sunny/shaded. Split later for high-resolution overlays.
            if state == 'unknown': sun=None; unknown=duration
            else: sun=round(duration * sun_fraction,4); unknown=0.
            segments.append(RouteSegment(shade_state=state,duration_s=round(duration,4),sun_seconds=sun,unknown_seconds=round(unknown,4),geometry=LineString(coordinates=coords)))
            points += coords if not points else coords[1:]
            total_len += dist; total_time += duration
            if sun is not None: total_sun += sun
            total_unknown += unknown
        candidate=Candidate(tuple(path),total_time,round(total_sun,4) if total_unknown < 0.01 else None,total_unknown)
        catalog[candidate.path]=(candidate,points,segments,total_len)
    selected=choose_routes([r[0] for r in catalog.values()],temperature_c)
    items=[]; first_for={}
    for mode,candidate in selected.items():
        c,coords,segments,distance=catalog[candidate.path]
        alias=first_for.get(candidate.path)
        if not alias: first_for[candidate.path]=mode
        items.append(RouteResponseItem(id=f"{mode}-01",mode=mode,same_as=f"{alias}-01" if alias else None,
                  duration_s=round(c.duration_s,2),distance_m=round(distance,2),sun_seconds=c.sun_s,
                  unknown_seconds=round(c.unknown_s,2),optimization_quality=('unavailable' if c.sun_s is None and mode!='fastest' else 'shortest_time' if mode=='fastest' else 'candidate_search'),
                  geometry=LineString(coordinates=coords),segments=segments))
    return RoutesResponse(conditions=Conditions(temperature_c=temperature_c,
       shade_model='geometry_estimate' if model and shadows else 'unavailable',data_as_of=model.data_as_of if model else None,
       model_limitations=['Tree shade not modeled','Sidewalk side and terrain not modeled',
         'Only real OSM graph paths are shown','Shade data missing or incomplete: alternatives may coincide'] if model else
         ['No licensed usable shadow dataset loaded; all exposure is unknown','Alternatives coincide until shade data is available']), routes=items)
