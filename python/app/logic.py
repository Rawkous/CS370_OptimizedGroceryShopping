# app/logic.py
import math
import random
from typing import List, Tuple, Dict, Any

from .db import query

# --- geometry ---
def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance (miles)."""
    R = 3958.8
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = (
        math.sin(dLat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dLon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def find_shortest_route(start: Tuple[float, float], items: List[Tuple[float, float]]):
    """Greedy nearest-neighbor route."""
    route = []
    current = start
    total_distance = 0.0
    remaining = items.copy()
    while remaining:
        nxt = min(remaining, key=lambda loc: haversine(current[0], current[1], loc[0], loc[1]))
        dist = haversine(current[0], current[1], nxt[0], nxt[1])
        total_distance += dist
        route.append({"to": nxt, "distance": dist})
        current = nxt
        remaining.remove(nxt)
    return route, total_distance

# --- demo scoring ---
def demo_store_scoring():
    stores = [
        {"name": "Supermarket", "inventory": ['banana', 'egg', 'bread', 'soda', 'cookies', 'sugar'], "distance": 5},
        {"name": "MiniMart",   "inventory": ['banana', 'milk', 'bread', 'chips'],                  "distance": 3},
        {"name": "OrganicShop","inventory": ['bread', 'sugar', 'apple', 'lettuce'],               "distance": 8},
        {"name": "CornerStore","inventory": ['banana', 'egg'],                                     "distance": 2},
    ]
    userItems = ['banana', 'egg', 'bread', 'sugar']

    best, results = None, []
    best_score = -1
    for s in stores:
        matches = set(s["inventory"]) & set(userItems)
        score = len(matches) / s["distance"] if s["distance"] else float("inf")
        row = {
            "Store": s["name"],
            "Distance": s["distance"],
            "MatchedItems": sorted(list(matches)),
            "MatchCount": len(matches),
            "Score": round(score, 3),
        }
        results.append(row)
        if score > best_score:
            best, best_score = row, score
    return best, results

# --- item existence check (via price_history join) ---
def check_items_in_price_history(items: List[str]) -> Dict[str, Any]:
    if not items:
        return {"found": [], "missing": []}
    placeholders = ", ".join(["%s"] * len(items))
    sql = f"""
        SELECT DISTINCT LOWER(p.name) AS item_name
        FROM price_history ph
        JOIN product p ON p.upc = ph.product_upc
        WHERE LOWER(p.name) IN ({placeholders})
    """
    rows = query(sql, tuple(i.lower() for i in items))
    found = [r["item_name"] for r in rows]
    missing = [i for i in (x.lower() for x in items) if i not in found]
    return {"found": found, "missing": missing}

# --- simulation helper used by API and CLI ---
def simulate_route(start_lat: float, start_lon: float, n: int = 5, gas_rate: float = 0.05):
    items = [(random.uniform(-90, 90), random.uniform(-180, 180)) for _ in range(n)]
    route, total_distance = find_shortest_route((start_lat, start_lon), items)
    gas_used = total_distance * gas_rate
    return {
        "start": {"lat": start_lat, "lon": start_lon},
        "items": items,
        "route": route,
        "total_distance_miles": round(total_distance, 2),
        "gas_used": round(gas_used, 2),
    }
