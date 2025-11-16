# app/kroger.py
import base64, os, time
from typing import Dict, Any, List, Optional
import requests

KROGER_OAUTH_URL = "https://api.kroger.com/v1/connect/oauth2/token"
KROGER_BASE_URL  = "https://api.kroger.com/v1"

# --- token cache (client credentials) ---
_client_token: Dict[str, Any] = {}

def _basic_auth_b64() -> str:
    cid = os.getenv("KROGER_CLIENT_ID", "")
    csec = os.getenv("KROGER_CLIENT_SECRET", "")
    pair = f"{cid}:{csec}".encode()
    return base64.b64encode(pair).decode()

def get_client_token(scope: Optional[str] = None) -> str:
    """
    Client-credentials token for server-to-server calls (Products/Locations).
    Cache until expiration.
    """
    global _client_token
    want_scope = scope or os.getenv("KROGER_SCOPES_CLIENT", "product.compact location.compact")
    now = time.time()
    if _client_token and _client_token.get("scope") == want_scope and _client_token.get("exp", 0) > now + 30:
        return _client_token["access_token"]

    headers = {"Authorization": f"Basic {_basic_auth_b64()}",
               "Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "client_credentials", "scope": want_scope}
    r = requests.post(KROGER_OAUTH_URL, headers=headers, data=data, timeout=15)
    r.raise_for_status()
    tok = r.json()
    _client_token = {
        "access_token": tok["access_token"],
        "exp": now + int(tok.get("expires_in", 1500)),
        "scope": want_scope,
    }
    return _client_token["access_token"]

# --- Locations ---
def kroger_locations_by_geo(lat: float, lon: float, radius_miles: int = 10, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Uses Locations API near a lat/long with radius (miles).
    """
    token = get_client_token()
    # official docs show these filters for geo searches
    # filter.latLong.near & filter.radiusInMiles
    # https://developer.kroger.com/documentation/api-products/public/locations/overview
    params = {
        "filter.latLong.near": f"{lat},{lon}",
        "filter.radiusInMiles": radius_miles,
        "filter.limit": limit,
    }
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{KROGER_BASE_URL}/locations", headers=headers, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data.get("data", [])

# --- Products (priced for a specific store) ---
def kroger_products_for_terms(location_id: str, terms: List[str], limit_per_term: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    """
    For each search term, query Products at a specific locationId (required to get price/aisle).
    Returns dict term -> [products...]
    """
    token = get_client_token()
    headers = {"Authorization": f"Bearer {token}"}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for term in terms:
        if not term:
            out[term] = []
            continue
        params = {
            "filter.term": term,
            "filter.locationId": location_id,   # required for price/aisle
            "filter.limit": limit_per_term
        }
        r = requests.get(f"{KROGER_BASE_URL}/products", headers=headers, params=params, timeout=20)
        r.raise_for_status()
        out[term] = r.json().get("data", [])
    return out

# --- Transform Kroger data into your app's search result shape ---
def search_kroger(lat: float, lon: float, items_tokens: List[str], radius_miles: int, lambda_per_mile: float):
    """
    Mirrors /api/search output fields so your UI keeps working.
    """
    # 1) find nearby Kroger stores
    locs = kroger_locations_by_geo(lat, lon, radius_miles)
    stores: List[Dict[str, Any]] = []
    for loc in locs:
        try:
            lid = loc["locationId"]
            name = loc["name"]
            coords = loc.get("geolocation", {}).get("latitudeLongitude", {})
            s_lat, s_lon = float(coords["latitude"]), float(coords["longitude"])
        except Exception:
            continue

        # 2) for each store, fetch products for each item token
        term_map = kroger_products_for_terms(lid, items_tokens)
        found_prices: Dict[str, float] = {}
        missing: List[str] = []

        # choose the lowest price per token from returned product list
        for t in items_tokens:
            prods = term_map.get(t, [])
            best = None
            for p in prods:
                # price lives under items[0].price.regular in compact payloads
                try:
                    items = p.get("items", [])
                    if not items:
                        continue
                    price = items[0].get("price", {}).get("regular")
                    if price is None:
                        continue
                    price = float(price)
                    best = price if best is None else min(best, price)
                except Exception:
                    continue
            if best is None:
                missing.append(t)
            else:
                found_prices[t] = best

        total = sum(found_prices.values()) if items_tokens else 0.0
        # distance: compute great-circle locally
        from .logic import haversine
        dist_mi = haversine(lat, lon, s_lat, s_lon)
        score = round(total + lambda_per_mile * dist_mi, 2)

        stores.append({
            "store_id": hash(lid) & 0x7fffffff,  # stable-ish int for UI
            "store_name": name,
            "city": loc.get("address", {}).get("city"),
            "lat": s_lat,
            "lon": s_lon,
            "distance_miles": round(dist_mi, 2),
            "items_found": len(items_tokens) - len(missing),
            "items_missing": missing,
            "total_price": round(total, 2),
            "score": score,
            "_kroger": {"locationId": lid}  # for debugging
        })

    # split full/partial to match your existing payload
    if items_tokens:
        full = [s for s in stores if not s["items_missing"]]
        partial = [s for s in stores if s["items_missing"]]
    else:
        full, partial = stores, []

    full.sort(key=lambda s: (s["total_price"], s["distance_miles"]))
    partial.sort(key=lambda s: (len(s["items_missing"]), s["total_price"] or 1e9, s["distance_miles"]))

    best = (full[0] if full else (partial[0] if partial else None))
    return {
        "best": best,
        "stores_full": full,
        "stores_partial": partial
    }
