"""Bounded route-candidate search over scored pedestrian edges."""
from dataclasses import dataclass
from itertools import islice
from math import isfinite

import networkx as nx

EdgeRef = tuple[object, object, object]


@dataclass(frozen=True)
class EdgeCost:
    duration_s: float
    sun_s: float


def _duration_graph(graph: nx.MultiDiGraph, speed_mps: float) -> nx.DiGraph:
    simple = nx.DiGraph()
    simple.add_nodes_from(graph.nodes)
    for u, v, key, data in graph.edges(keys=True, data=True):
        length = float(data.get("length", float("inf")))
        if not isfinite(length) or length <= 0:
            continue
        duration = length / speed_mps
        candidate = (duration, repr(key))
        existing = simple.get_edge_data(u, v)
        if existing is None or candidate < (existing["duration_s"], repr(existing["edge_ref"][2])):
            simple.add_edge(u, v, duration_s=duration, edge_ref=(u, v, key))
    return simple


def fastest_edge_path(
    graph: nx.MultiDiGraph, start, end, speed_mps: float
) -> tuple[tuple[EdgeRef, ...], float]:
    if start == end:
        raise ValueError("Start and destination resolve to the same pedestrian node")
    simple = _duration_graph(graph, speed_mps)
    nodes = nx.shortest_path(simple, start, end, weight="duration_s")
    edges = tuple(simple[u][v]["edge_ref"] for u, v in zip(nodes, nodes[1:]))
    duration = sum(simple[u][v]["duration_s"] for u, v in zip(nodes, nodes[1:]))
    return edges, duration


def bounded_edge_refs(
    graph: nx.MultiDiGraph, start, end, max_duration_s: float, speed_mps: float
) -> tuple[EdgeRef, ...]:
    """Edges that can participate in a route within the hard duration cap."""
    simple = _duration_graph(graph, speed_mps)
    from_start = nx.single_source_dijkstra_path_length(
        simple, start, cutoff=max_duration_s, weight="duration_s"
    )
    to_end = nx.single_source_dijkstra_path_length(
        simple.reverse(copy=False), end, cutoff=max_duration_s, weight="duration_s"
    )
    eligible = []
    for u, v, key, data in graph.edges(keys=True, data=True):
        length = float(data.get("length", float("inf")))
        if not isfinite(length) or length <= 0 or u not in from_start or v not in to_end:
            continue
        if from_start[u] + length / speed_mps + to_end[v] <= max_duration_s + 1e-6:
            eligible.append((u, v, key))
    return tuple(eligible)


def _weighted_graph(costs: dict[EdgeRef, EdgeCost], sun_weight: float) -> nx.DiGraph:
    simple = nx.DiGraph()
    for edge_ref, cost in costs.items():
        if not all(isfinite(value) and value >= 0 for value in (cost.duration_s, cost.sun_s)):
            raise ValueError("Candidate edge costs must be finite and nonnegative")
        u, v, key = edge_ref
        weight = cost.duration_s + sun_weight * cost.sun_s
        candidate = (weight, cost.duration_s, repr(key))
        existing = simple.get_edge_data(u, v)
        if existing is None or candidate < (
            existing["weight"], existing["duration_s"], repr(existing["edge_ref"][2])
        ):
            simple.add_edge(
                u, v, weight=weight, duration_s=cost.duration_s, edge_ref=edge_ref
            )
    return simple


def candidate_edge_paths(
    costs: dict[EdgeRef, EdgeCost],
    start,
    end,
    sun_weights: tuple[float, ...],
    per_weight: int = 4,
) -> list[tuple[EdgeRef, ...]]:
    """Explore a small deterministic union of time/shade weighted simple paths."""
    if per_weight < 1:
        raise ValueError("per_weight must be positive")
    paths: list[tuple[EdgeRef, ...]] = []
    seen = set()
    for sun_weight in dict.fromkeys(sun_weights):
        if not isfinite(sun_weight) or sun_weight < 0:
            raise ValueError("Sun weights must be finite and nonnegative")
        simple = _weighted_graph(costs, sun_weight)
        try:
            node_paths = islice(
                nx.shortest_simple_paths(simple, start, end, weight="weight"), per_weight
            )
            for nodes in node_paths:
                edge_path = tuple(simple[u][v]["edge_ref"] for u, v in zip(nodes, nodes[1:]))
                if edge_path and edge_path not in seen:
                    seen.add(edge_path)
                    paths.append(edge_path)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
    if not paths:
        raise nx.NetworkXNoPath("No connected pedestrian candidate path")
    return paths
