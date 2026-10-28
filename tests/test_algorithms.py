import unittest
from algorithms import build_location_graph, dijkstra, haversine_km, prim_mst


class AlgorithmTests(unittest.TestCase):
    def test_dijkstra_finds_shortest_path(self):
        graph = {"nodes": {}, "edges": {
            "A": {"B": 2, "C": 10},
            "B": {"A": 2, "C": 3},
            "C": {"A": 10, "B": 3},
        }}
        result = dijkstra(graph, "A", "C")
        self.assertEqual(result["path"], ["A", "B", "C"])
        self.assertEqual(result["distance"], 5)

    def test_dijkstra_unknown_or_unreachable_node(self):
        graph = {"nodes": {}, "edges": {"A": {}, "B": {}}}
        self.assertIsNone(dijkstra(graph, "A", "B"))
        self.assertIsNone(dijkstra(graph, "A", "missing"))

    def test_prim_mst_weight(self):
        graph = {"nodes": {}, "edges": {
            "A": {"B": 2, "C": 4},
            "B": {"A": 2, "C": 1},
            "C": {"A": 4, "B": 1},
        }}
        result = prim_mst(graph)
        self.assertEqual(result["total"], 3)
        self.assertTrue(result["connected"])
        self.assertEqual(len(result["edges"]), 2)

    def test_prim_disconnected_graph_reports_forest(self):
        graph = {"nodes": {}, "edges": {"A": {}, "B": {}}}
        result = prim_mst(graph)
        self.assertFalse(result["connected"])
        self.assertEqual(result["components"], 2)

    def test_dynamic_graph_uses_coordinates_and_road_matrix(self):
        locations = {"Restaurant": (30.75, 76.63), "Order #5": (30.76, 76.64)}
        graph = build_location_graph(locations, [[0, 3.4], [3.4, 0]])
        self.assertEqual(graph["edges"]["Restaurant"]["Order #5"], 3.4)
        self.assertEqual(graph["nodes"]["Order #5"]["lat"], 30.76)

    def test_haversine_same_point_is_zero(self):
        self.assertAlmostEqual(haversine_km((30.75, 76.63), (30.75, 76.63)), 0.0)

    def test_invalid_coordinates_rejected(self):
        with self.assertRaises(ValueError):
            build_location_graph({"bad": (100, 0)})

    def test_negative_edge_weight_rejected(self):
        graph = {"nodes": {}, "edges": {"A": {"B": -1}, "B": {"A": -1}}}
        with self.assertRaises(ValueError):
            dijkstra(graph, "A", "B")


if __name__ == "__main__":
    unittest.main()
