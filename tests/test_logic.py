import math
from python.app import logic


def test_haversine_zero_distance():
    assert logic.haversine(0, 0, 0, 0) == 0


def test_haversine_known_distance():
    d = logic.haversine(40.7128, -74.0060, 34.0522, -118.2437)
    assert 2400 < d < 2500


def test_find_shortest_route_ordering():
    start = (0, 0)
    pts = [
        (0, 1), 
        (0, 5), 
        (0, 3), 
    ]
    route, total = logic.find_shortest_route(start, pts)

    assert route[0]["to"] == (0, 1)

    assert total > 0


def test_demo_store_scoring_returns_best_and_all():
    best, rows = logic.demo_store_scoring()

    assert isinstance(best, dict)
    assert isinstance(rows, list)
    assert "Store" in best
    assert "Score" in best

    scores = [r["Score"] for r in rows]
    assert best["Score"] == max(scores)


def test_simulate_route_shape():
    result = logic.simulate_route(10.0, 20.0, n=5)

    assert "start" in result
    assert "route" in result
    assert "items" in result

    assert len(result["items"]) == 5
    assert len(result["route"]) == 5

    assert result["total_distance_miles"] >= 0
    assert result["gas_used"] >= 0

