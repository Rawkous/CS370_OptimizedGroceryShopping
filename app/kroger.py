# app/kroger.py
from __future__ import annotations
import base64, os, time, math
from typing import Dict, Any, List, Tuple
import requests

KROGER_BASE = os.getenv("KROGER_BASE", "https://api.kroger.com")
TOKEN_URL   = f"{KROGER_BASE}/v1/connect/oauth2/token"
LOC_URL     = f"{KROGER_BASE}/v1/locations"
PROD_URL    = f"{KROGER_BASE}/v1/products"

_token_cache: Dict[str, Any] = {"access_token": None, "exp": 0}

def _client() -> Tuple[str, str]:
    cid = os.getenv("KROGER_CLIENT_ID", "")
    sec = os.getenv("KROGER_CLIENT_SECRET", "")
    if not cid or not sec:
        raise RuntimeError("KROGER_CLIENT_ID / KROGER_CLIENT_SECRET missing from .env")
    return cid, sec

def _scope() -> str:
    # Support either env name (your earlier .env used KROGER_SCOPES_CLIENT)
    return (os.getenv("KROGER_SCOPE") or os.getenv("KROGER_SCOPES_CLIENT") or
            "product.compact location.compact").strip()

def _basic_auth_b64() -> str:
    cid, sec = _client()
    return base64.b64encode(f"{cid}:{sec}".encode()).decode()

def _get_token() -> str:
    now = time.time()
    if _token_cache["access_token"] and _token_cache["exp"] > now + 30:
        return _token_cache["access_token"]

    headers = {
        "Authorization": f"Basic {_basic_auth_b64()}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    data = {"grant_type": "client_credentials", "scope": _scope()}
    r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=20)
    if r.status_code == 401:
        raise RuntimeError(
            "Kroger token request unauthorized. Check client id/secret, ensure Basic auth, and scopes."
        )
    r.raise_for_status()
    j = r.json()
    _token_cache["access_token"] = j["access_token"]
    _token_cache["exp"] = now + int(j.get("expires_in", 1700))
    return _token_cache["access_token"]

def _auth_headers() -> Dict[str, str]:
    cid, _ = _client()
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Accept": "application/json",
        # REQUIRED for many Kroger endpoints:
        "X-Client-Id": cid,
    }

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = (math.sin(dLat/2)**2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dLon/2)**2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def _get_locations(lat: float, lon: float, radius_miles: int, limit: int = 25) -> List[Dict[str, Any]]:
    # Public Locations API – these filters work reliably:
    params = {
        "filter.lat.near": f"{lat:.6f}",
        "filter.lon.near": f"{lon:.6f}",
        "filter.radiusInMiles": str(max(1, min(int(radius_miles), 100))),
        "filter.limit": str(min(int(limit), 100)),
    }
    r = requests.get(LOC_URL, headers=_auth_headers(), params=params, timeout=20)
    r.raise_for_status()
    return r.json().get("data", [])

def _get_products(term: str, location_id: str, limit: int = 8) -> List[Dict[str, Any]]:
    params = {
        "filter.term": term,
        "filter.locationId": location_id,
        "filter.limit": str(min(int(limit), 50)),
    }
    r = requests.get(PROD_URL, headers=_auth_headers(), params=params, timeout=25)
    r.raise_for_status()
    return r.json().get("data", [])

def _pick_cheapest_item(products_json: List[Dict[str, Any]]) -> Tuple[float, Dict[str, Any]] | None:
    """
    From Kroger product payload, pick the cheapest item (by promo or regular price).
    Returns (price, friendly_meta) or None.
    """
    best: Tuple[float, Dict[str, Any]] | None = None
    for p in products_json:
        brand = (p.get("brand") or "").strip()
        desc  = (p.get("description") or "").strip()
        items = p.get("items") or []
        for it in items:
            size = it.get("size") or it.get("packageSize") or ""
            price = None
            pr = it.get("price") or {}
            if pr.get("promo"):
                price = float(pr["promo"])
            elif pr.get("regular"):
                price = float(pr["regular"])
            if price is None:
                continue
            meta = {"brand": brand, "desc": desc, "size": size}
            if best is None or price < best[0]:
                best = (price, meta)
    return best

def search_kroger(lat: float, lon: float, items_tokens: List[str],
                  radius_miles: int, lambda_per_mile: float) -> Dict[str, Any]:
    """
    Return the same shape used by /api/search for the UI:
        {"best", "stores_full", "stores_partial"}
    """
    locs = _get_locations(lat, lon, radius_miles, limit=25)

    stores: List[Dict[str, Any]] = []
    for L in locs:
        sid = L.get("locationId") or L.get("locationId", "")
        name = (L.get("name") or
                (L.get("address") or {}).get("addressLine1") or
                "Store")

        geo = (L.get("geolocation") or {})
        s_lat = geo.get("latitude") or (geo.get("coordinates") or {}).get("latitude")
        s_lon = geo.get("longitude") or (geo.get("coordinates") or {}).get("longitude")
        if s_lat is None or s_lon is None:
            continue
        s_lat, s_lon = float(s_lat), float(s_lon)

        distance_miles = _haversine(lat, lon, s_lat, s_lon)

        found_map: Dict[str, float] = {}
        missing: List[str] = []
        details: Dict[str, Any] = {}

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
            except requests.HTTPError:
                missing.append(t)

        total = sum(found_map.values()) if items_tokens else 0.0
        score = total + lambda_per_mile * distance_miles

        addr = (L.get("address") or {})
        city = addr.get("city") or ""
        stores.append({
            "store_id": sid,
            "store_name": name,
            "city": city,
            "lat": s_lat,
            "lon": s_lon,
            "distance_miles": round(distance_miles, 2),
            "items": found_map,
            "items_details": details,  # richer UI (brand/size/desc)
            "items_found": len(found_map),
            "items_missing": missing,
            "total_price": round(total, 2),
            "score": round(score, 2),
        })

    # Split / sort like DB path
    if items_tokens:
        full = [s for s in stores if not s["items_missing"]]
        partial = [s for s in stores if s["items_missing"]]
    else:
        full, partial = stores, []

    full.sort(key=lambda s: (s["total_price"], s["distance_miles"]))
    partial.sort(key=lambda s: (len(s["items_missing"]), s["total_price"] or 1e9, s["distance_miles"]))

    best = full[0] if full else (partial[0] if partial else None)
    return {"best": best, "stores_full": full, "stores_partial": partial}
