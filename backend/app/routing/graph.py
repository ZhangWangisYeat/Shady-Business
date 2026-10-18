"""Load real OSM walking graph. Never silently substitute invented campus paths."""
from functools import lru_cache
from math import cos, radians, sqrt
import networkx as nx
from shapely import wkt
from app.settings import GRAPH_FILE, MAX_SNAP_METERS


class GraphDataUnavailable(Exception):
    pass


class SnapUnavailable(ValueError):
    pass


def meters_approx(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = a; lon2, lat2 = b
    return 111_320.0 * sqrt((lat2-lat1)**2 + ((lon2-lon1) * cos(radians((lat1+lat2)/2)))**2)


@lru_cache(maxsize=1)
def load_graph() -> nx.MultiDiGraph | None:
    if not GRAPH_FILE.is_file():
        return None
    try:
        g = nx.read_graphml(GRAPH_FILE)
        for _, info in g.nodes(data=True):
            info["x"] = float(info["x"])
            info["y"] = float(info["y"])
        for _, _, _, data in g.edges(keys=True, data=True):
            data["length"] = float(data.get("length", 0))
            if isinstance(data.get("geometry"), str):
                data["geometry"] = wkt.loads(data["geometry"])
        return g
    except (OSError, KeyError, TypeError, ValueError, nx.NetworkXError) as exc:
        raise GraphDataUnavailable("Walking graph data could not be loaded") from exc


def snap_node(g: nx.MultiDiGraph, coordinate: tuple[float, float]):
    node = min(g.nodes, key=lambda n: meters_approx(coordinate, (g.nodes[n]["x"],g.nodes[n]["y"])))
    distance = meters_approx(coordinate, (g.nodes[node]["x"],g.nodes[node]["y"]))
    if distance > MAX_SNAP_METERS:
        raise SnapUnavailable("No suitable pedestrian graph node near the requested location")
    return node


def edge_data(g: nx.MultiDiGraph, u, v, key=None) -> dict:
    options = g.get_edge_data(u, v)
    if not options:
        raise ValueError("Broken pedestrian path")
    if key is not None:
        if key not in options:
            raise ValueError("Missing pedestrian graph edge")
        return options[key]
    return min(options.values(), key=lambda d: float(d.get("length",float('inf'))))


def coords_for_edge(g: nx.MultiDiGraph, u, v, key=None) -> list[tuple[float,float]]:
    data = edge_data(g,u,v,key)
    start = (g.nodes[u]["x"],g.nodes[u]["y"])
    end = (g.nodes[v]["x"],g.nodes[v]["y"])
    line = data.get("geometry")
    coords = list(line.coords) if line is not None else [start, end]
    if meters_approx(coords[0],start) > meters_approx(coords[-1],start):
        coords.reverse()
    return [(float(x),float(y)) for x,y in coords]


def candidate_paths(g: nx.MultiDiGraph, start, end, speed_mps: float = 1.3, limit: int = 12):
    """Baseline: k shortest (not exact sun-Pareto); later replace with multiobjective search."""
    def weight(u,v,options):
        if any('length' in data for data in options.values()):
            return min(float(d.get('length',float('inf'))) for d in options.values())
        return float('inf')
    # Simple DiGraph avoids ambiguous weighted MultiGraph callback assumptions.
    simple = nx.DiGraph()
    simple.add_nodes_from(g.nodes)
    for u,v,_,data in g.edges(keys=True,data=True):
        length = float(data.get('length',float('inf')))
        if length <= 0: continue
        if not simple.has_edge(u,v) or length < simple[u][v]['length']:
            simple.add_edge(u,v,length=length)
    if start == end:
        raise ValueError("Start and destination resolve to the same pedestrian node")
    return list(__import__('itertools').islice(nx.shortest_simple_paths(simple,start,end,weight='length'),limit))
