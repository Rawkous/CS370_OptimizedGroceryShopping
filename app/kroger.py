# app/kroger.py
from __future__ import annotations
import base64, os, time, math, json
from typing import Dict, Any, List, Tuple, Optional
import requests

# ---- Config / base URLs ------------------------------------------------------

def _api_base() -> str:
    # Allow switching between prod and cert via env. Defaults to prod.
    return os.getenv("KROGER_BASE", os.getenv("KROGER_ENV", "").lower() == "cert" and
                     "https://api-ce.kroger.com" or "https://api.kroger.com")

def _token_url() -> str:
    return f"{_api_base()}/v1/connect/oauth2/token"

LOC_URL  = lambda: f"{_api_base()}/v1/locations"
PROD_URL = lambda: f"{_api_base()}/v1/products"

# ---- Token cache -------------------------------------------------------------

_token_cache: Dict[str, Any] = {"access_token": None, "exp": 0, "key": ""}

def _b64_client() -> str:
    cid = os.getenv("KROGER_CLIENT_ID", "").strip()
    sec = os.getenv("KROGER_CLIENT_SECRET", "").strip()
    if not cid or not sec:
        raise RuntimeError("KROGER_CLIENT_ID / KROGER_CLIENT_SECRET missing from .env")
    return base64.b64encode(f"{cid}:{sec}".encode()).decode()

def _get_token() -> str:
    """
    Client-credentials token. For Locations, scope is N/A (omit).
    For Products, include product.compact if you set it in .env.
    """
    now = time.time()
    # Cache key should include base URL and scope (tokens differ across env/scope)
    scope = os.getenv("KROGER_SCOPES_CLIENT", "").strip()
    cache_key = f"{_api_base()}|{scope}"
    if _token_cache["access_token"] and _token_cache["exp"] > now + 30 and _token_cache["key"] == cache_key:
        return _token_cache["access_token"]

    headers = {
        "Authorization": f"Basic {_b64_client()}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    data = {"grant_type": "client_credentials"}
    # Only include scope if non-empty; Locations explicitly say N/A
    if scope:
        data["scope"] = scope

    r = requests.post(_token_url(), headers=headers, data=data, timeout=20)
    if r.status_code == 401:
        raise RuntimeError("Kroger token unauthorized (check client id/secret and scopes).")
    try:
        r.raise_for_status()
    except Exception as e:
        # Surface Kroger's JSON error for easier debugging
        try:
            raise RuntimeError(f"Token error: {r.status_code} {r.text}") from e
        except Exception:
            raise

    j = r.json()
    _token_cache.update({
        "access_token": j["access_token"],
        "exp": now + int(j.get("expires_in", 1700)),
        "key": cache_key,
    })
    return _token_cache["access_token"]

def _auth_headers():
    return {"Authorization": f"Bearer {_get_token()}", "Accept": "application/json"}

# ---- Helpers ----------------------------------------------------------------

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = (math.sin(dLat/2)**2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dLon/2)**2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def _safe_coord(loc: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    # Spec: geolocation.latitude / geolocation.longitude; fallback to latLng "lat,lon"
    geo = (loc.get("geolocation") or {})
    lat = geo.get("latitude")
    lon = geo.get("longitude")
    if lat is None or lon is None:
        latlng = (geo.get("latLng") or "").split(",")
        if len(latlng) == 2:
            try:
                lat = float(latlng[0].strip()); lon = float(latlng[1].strip())
            except Exception:
                lat, lon = None, None
    try:
        return (None if lat is None else float(lat),
                None if lon is None else float(lon))
    except Exception:
        return (None, None)

# ---- API calls (aligned to the OpenAPI JSON you pasted) ---------------------

def _get_locations(
    lat: float,
    lon: float,
    radius_miles: int,
    limit: int = 25,
    chain: Optional[str] = None,
) -> List[Dict[str, Any]]:
    params = {
        # NOTE: spec uses *.near keys
        "filter.latLong.near": f"{lat},{lon}",
        "filter.radiusInMiles": str(max(1, min(int(radius_miles), 100))),
        "filter.limit": str(max(1, min(int(limit), 200))),
    }
    if chain:
        params["filter.chain"] = chain

    r = requests.get(LOC_URL(), headers=_auth_headers(), params=params, timeout=20)
    if r.status_code >= 400:
        # Include Kroger's error json if available
        try:
            err = r.json()
            raise RuntimeError(f"Locations error {r.status_code}: {json.dumps(err)}")
        except Exception:
            r.raise_for_status()
    data = r.json().get("data", [])
    return data

def _get_products(term: str, location_id: str, limit: int = 8) -> List[Dict[str, Any]]:
    """
    Products Public API (unchanged): needs product.compact scope on the token.
    """
    params = {
        "filter.term": term,
        "filter.locationId": location_id,
        "filter.limit": str(max(1, min(int(limit), 50))),
    }
    r = requests.get(PROD_URL(), headers=_auth_headers(), params=params, timeout=25)
    if r.status_code == 401:
        raise RuntimeError("Products call unauthorized — token must include 'product.compact' scope.")
    if r.status_code >= 400:
        try:
            raise RuntimeError(f"Products error {r.status_code}: {r.text}")
        except Exception:
            r.raise_for_status()
    return r.json().get("data", [])

def _pick_cheapest_item(products_json: List[Dict[str, Any]]) -> Tuple[float, Dict[str, Any]] | None:
    best = None
    for p in products_json:
        brand = p.get("brand") or ""
        desc  = p.get("description") or ""
        items = p.get("items") or []
        for it in items:
            size = it.get("size") or it.get("packageSize") or ""
            pr = (it.get("price") or {})  # {"regular": X, "promo": Y}
            price = None
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

# ---- Orchestrator used by /api/search --------------------------------------

def search_kroger(
    lat: float,
    lon: float,
    items_tokens: List[str],
    radius_miles: int,
    lambda_per_mile: float,
    chain: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns { best, stores_full, stores_partial } matching the app's shape.
    """
    locs = _get_locations(lat, lon, radius_miles, limit=200, chain=chain)

    stores: List[Dict[str, Any]] = []
    for L in locs:
        sid  = L.get("locationId") or ""
        name = L.get("name") or "Store"
        city = ((L.get("address") or {}).get("city")) or ""
        s_lat, s_lon = _safe_coord(L)
        if s_lat is None or s_lon is None or not sid:
            continue

        distance_miles = _haversine(lat, lon, s_lat, s_lon)

        found_map: Dict[str, float] = {}
        missing: List[str] = []
        details: Dict[str, Any] = {}

        # Per-item product lookup (cheapest)
        for t in items_tokens:
            try:
                prods = _get_products(t, sid, limit=15)
                pick = _pick_cheapest_item(prods)
                if pick:
                    price, meta = pick
                    found_map[t] = price
                    details[t] = {"price": round(price, 2), **meta}
                else:
                    missing.append(t)
            except Exception as e:
                # Soft-fail this token only; keep the rest
                missing.append(t)

        total = sum(found_map.values()) if items_tokens else 0.0
        score = total + lambda_per_mile * distance_miles

        stores.append({
            "store_id": sid,
            "store_name": name,
            "city": city,
            "chain": L.get("chain"),
            "lat": float(s_lat),
            "lon": float(s_lon),
            "distance_miles": round(distance_miles, 2),
            "items": found_map,
            "items_details": details,
            "items_found": len(found_map),
            "items_missing": missing,
            "total_price": round(total, 2),
            "score": round(score, 2),
        })

    # Split & sort
    if items_tokens:
        full    = [s for s in stores if not s["items_missing"]]
        partial = [s for s in stores if s["items_missing"]]
    else:
        full, partial = stores, []

    full.sort(key=lambda s: (s["total_price"], s["distance_miles"]))
    partial.sort(key=lambda s: (len(s["items_missing"]), s["total_price"] or 1e9, s["distance_miles"]))

    best = full[0] if full else (partial[0] if partial else None)
    return {"best": best, "stores_full": full, "stores_partial": partial}
