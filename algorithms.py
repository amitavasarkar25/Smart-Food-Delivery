
from __future__ import annotations

import heapq
import math
from typing import Any, Mapping


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in kilometres for (latitude, longitude) pairs."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


def validate_graph(graph: Mapping[str, Any]) -> tuple[dict[str, dict[str, float]], list[str]]:
    raw = graph.get("edges", {})
    if not isinstance(raw, Mapping):
        raise ValueError("Graph edges must be a mapping.")
    edges: dict[str, dict[str, float]] = {}
    for node, neighbours in raw.items():
        if not isinstance(node, str) or not node:
            raise ValueError("Every graph node needs a non-empty name.")
        if not isinstance(neighbours, Mapping):
            raise ValueError(f"Neighbours for {node} must be a mapping.")
        edges[node] = {}
        for neighbour, weight in neighbours.items():
            if neighbour not in raw:
                raise ValueError(f"Graph edge points to unknown node: {neighbour}.")
            try:
                value = float(weight)
            except (TypeError, ValueError) as exc:
                raise ValueError("Graph weights must be numeric.") from exc
            if not math.isfinite(value) or value < 0:
                raise ValueError("Graph weights must be finite and non-negative.")
            edges[node][neighbour] = value
    return edges, list(edges)


def dijkstra(graph: Mapping[str, Any], start: str, end: str) -> dict[str, Any] | None:
    """Return a shortest path for a non-negative weighted graph, or None."""
    edges, nodes = validate_graph(graph)
    if start not in edges or end not in edges:
        return None
    distances = {node: math.inf for node in nodes}
    previous: dict[str, str] = {}
    distances[start] = 0.0
    queue: list[tuple[float, str]] = [(0.0, start)]
    while queue:
        current_distance, node = heapq.heappop(queue)
        if current_distance != distances[node]:
            continue
        if node == end:
            break
        for neighbour, weight in edges[node].items():
            candidate = current_distance + weight
            if candidate < distances[neighbour]:
                distances[neighbour] = candidate
                previous[neighbour] = node
                heapq.heappush(queue, (candidate, neighbour))
    if math.isinf(distances[end]):
        return None
    path = [end]
    while path[-1] != start:
        parent = previous.get(path[-1])
        if parent is None:
            return None
        path.append(parent)
    path.reverse()
    return {"path": path, "distance": round(distances[end], 2), "complexity": "O((V + E) log V)"}


def prim_mst(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Return a minimum spanning forest; connected=False if graph is disconnected."""
    edges, nodes = validate_graph(graph)
    if not nodes:
        return {"edges": [], "total": 0.0, "complexity": "O(E log V)", "connected": True, "components": 0}
    unseen = set(nodes)
    chosen: list[dict[str, Any]] = []
    total = 0.0
    components = 0
    while unseen:
        root = min(unseen)
        components += 1
        unseen.remove(root)
        candidates: list[tuple[float, str, str]] = []
        for neighbour, weight in edges[root].items():
            heapq.heappush(candidates, (weight, root, neighbour))
        while candidates:
            weight, parent, node = heapq.heappop(candidates)
            if node not in unseen:
                continue
            unseen.remove(node)
            chosen.append({"from": parent, "to": node, "distance": round(weight, 2)})
            total += weight
            for neighbour, next_weight in edges[node].items():
                if neighbour in unseen:
                    heapq.heappush(candidates, (next_weight, node, neighbour))
    return {
        "edges": chosen,
        "total": round(total, 2),
        "complexity": "O(E log V)",
        "connected": components == 1,
        "components": components,
    }


def build_location_graph(
    locations: Mapping[str, tuple[float, float]],
    distance_matrix_km: list[list[float]] | None = None,
) -> dict[str, Any]:
    """Build a complete graph from dynamic coordinates.

    If a road-distance matrix is supplied (same ordering as locations), use it;
    otherwise use Haversine distance. This function never claims straight-line
    distances are road distances.
    """
    names = list(locations)
    if distance_matrix_km is not None and len(distance_matrix_km) != len(names):
        raise ValueError("Distance matrix size does not match the location list.")
    nodes: dict[str, dict[str, float]] = {}
    edges: dict[str, dict[str, float]] = {name: {} for name in names}
    for name, coords in locations.items():
        if len(coords) != 2:
            raise ValueError(f"Invalid coordinates for {name}.")
        lat, lon = float(coords[0]), float(coords[1])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"Coordinates out of range for {name}.")
        nodes[name] = {"lat": lat, "lon": lon}
    for i, a in enumerate(names):
        for j in range(i + 1, len(names)):
            b = names[j]
            if distance_matrix_km is not None:
                try:
                    weight = float(distance_matrix_km[i][j])
                except (IndexError, TypeError, ValueError) as exc:
                    raise ValueError("Road-distance matrix is malformed.") from exc
                if not math.isfinite(weight) or weight < 0:
                    raise ValueError("Road-distance matrix contains an invalid distance.")
            else:
                weight = haversine_km(locations[a], locations[b])
            edges[a][b] = weight
            edges[b][a] = weight
    return {"nodes": nodes, "edges": edges}


