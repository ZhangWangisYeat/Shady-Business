"""Real OSM edge route calculation; shade is optional and explicitly unknown without vetted data."""
from datetime import datetime
import logging
import networkx as nx
from app.routing.candidates import EdgeCost, bounded_edge_refs, candidate_edge_paths, fastest_edge_path
from app.routing.graph import GraphDataUnavailable, SnapUnavailable, load_graph, snap_node, edge_data, coords_for_edge
from app.routing.policy import Candidate, choose_routes, shade_weight
from app.shade.model import ShadeDataUnavailable, load_model, build_shadow_field, model_coverage_status
from app.shade.scoring import RouteEdge, score_route
from app.routing.directions import Leg, build_steps
from app.api.schemas import RouteResponseItem, RouteSegment, LineString, Conditions, RoutesResponse

SPEED_MPS=1.3  # constant, not accessibility-adjusted
logger=logging.getLogger(__name__)

class GraphUnavailable(Exception): pass
class NoRoute(Exception): pass
class SameEndpoint(Exception): pass


class EndpointTooFar(Exception):
    def __init__(self, field: str):
        self.field=field
        super().__init__(f"{field} is too far from the pedestrian network")


def build_routes(origin: tuple[float,float], destination: tuple[float,float], when: datetime, temperature_c: float) -> RoutesResponse:
    # HTTP contract uses Celsius; routing policy uses Fahrenheit.
    temperature_f = temperature_c * 9 / 5 + 32
    try:
        graph=load_graph()
    except GraphDataUnavailable as exc:
        raise GraphUnavailable("Walking routes are temporarily unavailable") from exc
    if graph is None: raise GraphUnavailable("Walking routes are temporarily unavailable")
    try:
        source=snap_node(graph,origin)
    except SnapUnavailable as exc:
        raise EndpointTooFar("origin") from exc
    try:
        target=snap_node(graph,destination)
    except SnapUnavailable as exc:
        raise EndpointTooFar("destination") from exc
    if source == target:
        raise SameEndpoint("Start and destination are too close")
    try:
        fastest_path,fastest_duration=fastest_edge_path(graph,source,target,SPEED_MPS)
    except nx.NetworkXNoPath as e:
        raise NoRoute("No connected pedestrian path") from e
    shade_data_failed=False
    try:
        model=load_model()
    except ShadeDataUnavailable as exc:
        logger.warning("Shade dataset unavailable; returning unknown exposure: %s", exc)
        model=None
        shade_data_failed=True
    field=build_shadow_field(model,when)
    profiles={}

    def profile(edge_ref):
        if edge_ref in profiles: return profiles[edge_ref]
        u,v,key=edge_ref
        data=edge_data(graph,u,v,key)
        distance=float(data['length']); duration=distance/SPEED_MPS
        coords=coords_for_edge(graph,u,v,key)
        score=score_route([RouteEdge(tuple(coords),duration)],field)
        profiles[edge_ref]=(distance,duration,coords,score)
        return profiles[edge_ref]

    paths=[fastest_path]
    # the shade search can only help when the fastest path itself has known
    # exposure everywhere; otherwise its result is discarded below. scoring the
    # fastest path first skips scoring thousands of nearby edges for nothing in
    # places we have no data for yet. when better shade data (for example a
    # vision model filling in unknown areas) adds shadows or coverage to the
    # field, those paths pass this check and get the full search automatically.
    def known(edge_ref):
        score=profile(edge_ref)[3]
        return score.sun_seconds is not None and score.unknown_seconds <= .01
    fastest_known=all(known(edge_ref) for edge_ref in fastest_path)
    if fastest_known and field.status=='daylight' and field.coverage_geometry is not None:
        max_duration=min(fastest_duration*1.6,fastest_duration+720)
        edge_refs=bounded_edge_refs(graph,source,target,max_duration,SPEED_MPS)
        costs={}
        for edge_ref in edge_refs:
            _,duration,_,score=profile(edge_ref)
            if score.sun_seconds is None or score.unknown_seconds > .01:
                continue
            costs[edge_ref]=EdgeCost(duration,float(score.sun_seconds))
        if all(edge_ref in costs for edge_ref in fastest_path):
            weights=(0.,shade_weight(temperature_f),.5,1.,2.,4.,8.)
            searched=candidate_edge_paths(costs,source,target,weights)
            paths=list(dict.fromkeys((fastest_path,*searched)))

    catalog={}
    for path in paths:
        points=[]; segments=[]; legs=[]; total_len=0.; total_sun=0.; total_unknown=0.; total_time=0.
        for edge_ref in path:
            dist,duration,coords,score=profile(edge_ref)
            u,v,key=edge_ref
            data=edge_data(graph,u,v,key)
            legs.append(Leg(coords,dist,data.get('name'),data.get('highway')))
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
        candidate=Candidate(tuple(path),total_time,round(total_sun,4) if total_unknown <= .01 else None,total_unknown)
        catalog[candidate.path]=(candidate,points,segments,total_len,build_steps(legs))
    selected=choose_routes([r[0] for r in catalog.values()],temperature_f)
    items=[]; first_for={}
    for mode,candidate in selected.items():
        c,coords,segments,distance,steps=catalog[candidate.path]
        alias=first_for.get(candidate.path)
        if not alias: first_for[candidate.path]=mode
        duration_s=round(c.duration_s,2)
        unknown_seconds=round(c.unknown_s,2)
        items.append(RouteResponseItem(id=f"{mode}-01",mode=mode,same_as=f"{alias}-01" if alias else None,
                  duration_s=duration_s,distance_m=round(distance,2),sun_seconds=c.sun_s,
                  unknown_seconds=unknown_seconds,optimization_quality=('shortest_time' if mode=='fastest' else 'unavailable' if c.sun_s is None or field.status!='daylight' else 'candidate_search'),
                  coverage_fraction=round(max(0.,min(1.,1-unknown_seconds/duration_s)),4),
                  geometry=LineString(coordinates=coords),segments=segments,steps=steps))
    coverage_status=model_coverage_status(model)
    limitations=list(field.limitations)+['Only real OSM graph paths are shown']
    if coverage_status == 'unverified':
        limitations.append('Incomplete shade coverage: alternatives may coincide')
    elif field.status == 'daylight' and any(item.unknown_seconds > .01 for item in items):
        limitations.append('Some route segments fall outside verified shade coverage')
    if field.status == 'night':
        limitations.append('Sun below horizon: no direct sunlight; daytime shade overlay is not applicable')
    elif model is None:
        limitations.append('No usable shadow dataset loaded; all exposure is unknown')
    if shade_data_failed:
        limitations.append('Shade data could not be loaded; walking routes remain available with unknown exposure')
    return RoutesResponse(conditions=Conditions(temperature_c=temperature_c,
       shade_model='geometry_estimate' if model else 'unavailable',
       shade_coverage=coverage_status,solar_status=field.status,data_as_of=field.data_as_of,
       model_limitations=limitations), routes=items)
