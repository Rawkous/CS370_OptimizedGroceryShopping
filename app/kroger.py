# app/kroger.py
from __future__ import annotations
import base64, os, time, math
from typing import Dict, Any, List, Tuple, Optional
import requests

# Read base from .env so you can use CERT or PROD
KROGER_BASE = os.getenv("KROGER_BASE", "https://api.kroger.com").rstrip("/")
TOKEN_URL   = f"{KROGER_BASE}/v1/connect/oauth2/token"
LOC_URL     = f"{KROGER_BASE}/v1/locations"
PROD_URL    = f"{KROGER_BASE}/v1/products"

_token_cache: Dict[str, Any] = {"access_token": None, "exp": 0, "base": KROGER_BASE}

def _b64_client():
    cid = os.getenv("KROGER_CLIENT_ID", "")
    sec = os.getenv("KROGER_CLIENT_SECRET", "")
    if not cid or not sec:
        raise RuntimeError("KROGER_CLIENT_ID / KROGER_CLIENT_SECRET missing from .env")
    return base64.b64encode(f"{cid}:{sec}".encode()).decode()

def _desired_scope() -> str:
    # Prefer KROGER_SCOPE; fall back to KROGER_SCOPES_CLIENT; allow empty for Locations-only
    s = (os.getenv("KROGER_SCOPE") or os.getenv("KROGER_SCOPES_CLIENT") or "").strip()
    return " ".join(s.split())

def _get_token() -> str:
    now = time.time()

    # Invalidate cache if base changed
    if _token_cache.get("base") != KROGER_BASE:
        _token_cache.update({"access_token": None, "exp": 0, "base": KROGER_BASE})

    if _token_cache["access_token"] and _token_cache["exp"] > now + 30:
        return _token_cache["access_token"]

    scope = _desired_scope()
    headers = {
        "Authorization": f"Basic {_b64_client()}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    data = {"grant_type": "client_credentials"}
    if scope:
        data["scope"] = scope

    r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=20)
    if r.status_code >= 400:
        try:
            details = r.json()
        except Exception:
            details = {"text": r.text}
        raise RuntimeError(f"Token error: Kroger token request failed ({r.status_code}): {details}")

    j = r.json()
    _token_cache["access_token"] = j["access_token"]
    _token_cache["exp"] = now + int(j.get("expires_in", 1700))
    _token_cache["base"] = KROGER_BASE
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

def _extract_lat_lon(L: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """Support both old and new shapes: {geolocation:{latitude,longitude}} OR latLng string, OR coordinates{}."""
    geo = L.get("geolocation") or {}
    lat = geo.get("latitude")
    lon = geo.get("longitude")
    if lat is None or lon is None:
        coords = geo.get("coordinates") or {}
        lat = lat or coords.get("latitude")
        lon = lon or coords.get("longitude")
    if (lat is None or lon is None) and isinstance(geo.get("latLng"), str):
        try:
            s = geo["latLng"].split(",")
            lat = float(s[0].strip()); lon = float(s[1].strip())
        except Exception:
            return None
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)

def _get_locations(lat: float, lon: float, radius_miles: int, limit: int=20, chain: Optional[str]=None) -> List[Dict[str, Any]]:
    # NOTE: use the correct parameter name per the OpenAPI: filter.latLong.near
    params = {
        "filter.latLong.near": f"{lat},{lon}",
        "filter.radiusInMiles": str(max(1, min(int(radius_miles), 100))),
        "filter.limit": str(max(1, min(int(limit), 200))),
    }
    if chain:
        params["filter.chain"] = chain

    r = requests.get(LOC_URL, headers=_auth_headers(), params=params, timeout=20)
    if r.status_code >= 400:
        try:
            details = r.json()
        except Exception:
            details = {"text": r.text}
        raise RuntimeError(f"Locations error ({r.status_code}): {details}")
    return r.json().get("data", []) or []

def _get_products(term: str, location_id: str, limit: int=8) -> List[Dict[str, Any]]:
    params = {
        "filter.term": term,
        "filter.locationId": location_id,
        "filter.limit": str(max(1, min(int(limit), 50))),
    }
    r = requests.get(PROD_URL, headers=_auth_headers(), params=params, timeout=25)
    if r.status_code >= 400:
        try:
            details = r.json()
        except Exception:
            details = {"text": r.text}
        raise RuntimeError(f"Products error ({r.status_code}) for loc {location_id} term '{term}': {details}")
    return r.json().get("data", []) or []

def _pick_cheapest_item(products_json: List[Dict[str, Any]]) -> Optional[Tuple[float, Dict[str, Any]]]:
    best = None
    for p in products_json:
        brand = p.get("brand") or ""
        desc  = p.get("description") or ""
        for it in p.get("items") or []:
            size = it.get("size") or it.get("packageSize") or ""
            pr = it.get("price") or {}
            price = None
            if pr.get("promo") not in (None, 0):
                price = float(pr["promo"])
            elif pr.get("regular") not in (None, 0):
                price = float(pr["regular"])
            if price is None:
                continue
            meta = {"brand": brand, "desc": desc, "size": size}
            if best is None or price < best[0]:
                best = (price, meta)
    return best

def search_kroger(lat: float, lon: float, items_tokens: List[str], radius_miles: int, lambda_per_mile: float, chain: Optional[str]=None) -> Dict[str, Any]:
    locs = _get_locations(lat, lon, radius_miles, limit=25, chain=chain)

    stores: List[Dict[str, Any]] = []
    for L in locs:
        coords = _extract_lat_lon(L)
        if not coords:
            continue
        s_lat, s_lon = coords
        distance_miles = _haversine(lat, lon, s_lat, s_lon)

        sid = L.get("locationId") or ""
        name = L.get("name") or "Store"
        addr = L.get("address") or {}
        city = addr.get("city") or ""

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
            except Exception:
                missing.append(t)

        total = sum(found_map.values()) if items_tokens else 0.0
        score = total + lambda_per_mile * distance_miles

        stores.append({
            "store_id": sid,
            "store_name": name,
            "city": city,
            "lat": s_lat,
            "lon": s_lon,
            "distance_miles": round(distance_miles, 2),
            "items": found_map,
            "items_details": details,
            "items_found": len(found_map),
            "items_missing": missing,
            "total_price": round(total, 2),
            "score": round(score, 2),
        })

    if items_tokens:
        full = [s for s in stores if not s["items_missing"]]
        partial = [s for s in stores if s["items_missing"]]
    else:
        full, partial = stores, []

    full.sort(key=lambda s: (s["total_price"], s["distance_miles"]))
    partial.sort(key=lambda s: (len(s["items_missing"]), s["total_price"] or 1e9, s["distance_miles"]))

    best = full[0] if full else (partial[0] if partial else None)
    return {"best": best, "stores_full": full, "stores_partial": partial}
