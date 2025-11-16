# app/kroger.py
from __future__ import annotations
import base64, os, time, math
from typing import Dict, Any, List, Tuple
import requests

KROGER_BASE = "https://api.kroger.com"
TOKEN_URL   = f"{KROGER_BASE}/v1/connect/oauth2/token"
LOC_URL     = f"{KROGER_BASE}/v1/locations"
PROD_URL    = f"{KROGER_BASE}/v1/products"

_token_cache: Dict[str, Any] = {"access_token": None, "exp": 0}

def _b64_client():
    cid = os.getenv("KROGER_CLIENT_ID", "")
    sec = os.getenv("KROGER_CLIENT_SECRET", "")
    if not cid or not sec:
        raise RuntimeError("KROGER_CLIENT_ID / KROGER_CLIENT_SECRET missing from .env")
    return base64.b64encode(f"{cid}:{sec}".encode()).decode()

def _get_token() -> str:
    now = time.time()
    if _token_cache["access_token"] and _token_cache["exp"] > now + 30:
        return _token_cache["access_token"]

    scope = os.getenv("KROGER_SCOPE", "").strip()  # e.g. "product.compact profile.compact cart.basic:write"
    headers = {
        "Authorization": f"Basic {_b64_client()}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    data = {"grant_type": "client_credentials"}
    if scope:
        data["scope"] = scope

    r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=15)
    if r.status_code == 401:
        raise RuntimeError("Kroger token request unauthorized (check client id/secret and that you used Basic auth).")
    r.raise_for_status()
    j = r.json()
    _token_cache["access_token"] = j["access_token"]
    _token_cache["exp"] = now + int(j.get("expires_in", 1700))
    return _token_cache["access_token"]

def _auth_headers():
    return {"Authorization": f"Bearer {_get_token()}", "Accept": "application/json"}

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = (math.sin(dLat/2)**2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dLon/2)**2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def _get_locations(lat: float, lon: float, radius_miles: int, limit: int=20) -> List[Dict[str, Any]]:
    # Public Locations API – supports lat/long and radius
    params = {
        "filter.latLong": f"{lat},{lon}",
        "filter.radiusInMiles": str(max(1, min(radius_miles, 100))),
        "filter.limit": str(limit),
    }
    r = requests.get(LOC_URL, headers=_auth_headers(), params=params, timeout=15)
    r.raise_for_status()
    return r.json().get("data", [])

def _get_products(term: str, location_id: str, limit: int=8) -> List[Dict[str, Any]]:
    params = {
        "filter.term": term,
        "filter.locationId": location_id,
        "filter.limit": str(limit),
    }
    r = requests.get(PROD_URL, headers=_auth_headers(), params=params, timeout=20)
    r.raise_for_status()
    return r.json().get("data", [])

def _pick_cheapest_item(products_json: List[Dict[str, Any]]) -> Tuple[float, Dict[str, Any]] | None:
    """
    From Kroger product payload, pick the cheapest item (by regular or promo price).
    Returns (price, friendly_meta) or None.
    """
    best = None
    for p in products_json:
        brand = p.get("brand") or ""
        desc  = p.get("description") or ""
        items = p.get("items") or []
        for it in items:
            size = it.get("size") or it.get("packageSize") or ""
            price = None
            pr = (it.get("price") or {})  # {"regular": X, "promo": Y}
            if "promo" in pr and pr["promo"] not in (None, 0):
                price = float(pr["promo"])
            elif "regular" in pr and pr["regular"] not in (None, 0):
                price = float(pr["regular"])
            if price is None:
                continue
            meta = {"brand": brand, "desc": desc, "size": size}
            if best is None or price < best[0]:
                best = (price, meta)
    return best

def search_kroger(lat: float, lon: float, items_tokens: List[str], radius_miles: int, lambda_per_mile: float) -> Dict[str, Any]:
    """
    Shape the response to match your existing /api/search output:
      { best, stores_full, stores_partial }
    """
    locs = _get_locations(lat, lon, radius_miles, limit=25)

    stores: List[Dict[str, Any]] = []
    for L in locs:
        sid = L.get("locationId") or L.get("locationId", "")
        name = L.get("name") or "Store"
        geo  = (L.get("geolocation") or {}).get("coordinates") or {}
        s_lat, s_lon = geo.get("latitude"), geo.get("longitude")
        if s_lat is None or s_lon is None:
            continue
        distance_miles = _haversine(lat, lon, float(s_lat), float(s_lon))

        # For each token (e.g. 'milk', 'bananas'), query products at this location and pick the cheapest
        found_map: Dict[str, float] = {}
        missing: List[str] = []
        details: Dict[str, Any] = {}  # token -> {price, brand, size, desc}
        for t in items_tokens:
            try:
                prods = _get_products(t, sid, limit=10)
                pick = _pick_cheapest_item(prods)
                if pick:
                    price, meta = pick
                    found_map[t] = price
                    details[t] = {"price": round(price, 2), **meta}
                else:
                    missing.append(t)
            except requests.HTTPError as e:
                # Don’t explode the whole search on a single token failure
                missing.append(t)

        total = sum(found_map.values()) if items_tokens else 0.0
        score = total + lambda_per_mile * distance_miles

        addr = (L.get("address") or {})
        city = addr.get("city") or ""
        stores.append({
            "store_id": sid,
            "store_name": name,
            "city": city,
            "lat": float(s_lat),
            "lon": float(s_lon),
            "distance_miles": round(distance_miles, 2),
            "items": found_map,
            "items_details": details,  # <-- for richer UI
            "items_found": len(found_map),
            "items_missing": missing,
            "total_price": round(total, 2),
            "score": round(score, 2),
        })

    # Split into full/partial and sort similar to DB path
    if items_tokens:
        full = [s for s in stores if not s["items_missing"]]
        partial = [s for s in stores if s["items_missing"]]
    else:
        full, partial = stores, []

    full.sort(key=lambda s: (s["total_price"], s["distance_miles"]))
    partial.sort(key=lambda s: (len(s["items_missing"]), s["total_price"] or 1e9, s["distance_miles"]))

    best = full[0] if full else (partial[0] if partial else None)
    return {"best": best, "stores_full": full, "stores_partial": partial}
