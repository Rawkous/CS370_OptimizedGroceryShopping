from __future__ import annotations
import base64
import os
import time
import math
from typing import Dict, Any, List, Tuple
import requests

# ----- Config -----
KROGER_BASE = os.getenv("KROGER_BASE", "https://api.kroger.com").rstrip("/")
TOKEN_URL   = f"{KROGER_BASE}/v1/connect/oauth2/token"
LOC_URL     = f"{KROGER_BASE}/v1/locations"
PROD_URL    = f"{KROGER_BASE}/v1/products"

_token_cache: Dict[str, Any] = {"access_token": None, "exp": 0}


def _b64_client() -> str:
    cid = os.getenv("KROGER_CLIENT_ID", "")
    sec = os.getenv("KROGER_CLIENT_SECRET", "")
    if not cid or not sec:
        raise RuntimeError("KROGER_CLIENT_ID / KROGER_CLIENT_SECRET missing from .env")
    raw = f"{cid}:{sec}".encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _get_token() -> str:
    """
    Get (or reuse) an OAuth2 access token using client_credentials.
    Raises RuntimeError with a helpful message on failure.
    """
    now = time.time()
    if _token_cache["access_token"] and _token_cache["exp"] > now + 30:
        return _token_cache["access_token"]

    scope_str = os.getenv("KROGER_SCOPES_CLIENT", "").strip()

    headers = {
        "Authorization": f"Basic {_b64_client()}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    data = {"grant_type": "client_credentials"}
    if scope_str:
        data["scope"] = scope_str

    resp = requests.post(TOKEN_URL, headers=headers, data=data, timeout=15)

    if resp.status_code == 401:
        # Bubble up exactly what Kroger said – super useful while debugging
        try:
            err = resp.json()
        except Exception:
            err = resp.text
        raise RuntimeError(f"Token error: Kroger token request failed (401): {err}")

    if not resp.ok:
        try:
            err = resp.json()
        except Exception:
            err = resp.text
        raise RuntimeError(
            f"Token error: HTTP {resp.status_code} from Kroger token endpoint: {err}"
        )

    j = resp.json()
    tok = j.get("access_token")
    if not tok:
        raise RuntimeError(f"Token error: no access_token in response: {j}")

    _token_cache["access_token"] = tok
    _token_cache["exp"] = now + int(j.get("expires_in", 1700))
    return tok


def _auth_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Accept": "application/json",
    }


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = (
        math.sin(dLat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dLon / 2) ** 2
    )
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _get_locations(lat: float, lon: float, radius_miles: int, limit: int = 20) -> List[Dict[str, Any]]:
    params = {
        "filter.latLong.near": f"{lat},{lon}",
        "filter.radiusInMiles": str(max(1, min(radius_miles, 100))),
        "filter.limit": str(limit),
    }
    resp = requests.get(LOC_URL, headers=_auth_headers(), params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("data", [])


def _get_products(term: str, location_id: str, limit: int = 8) -> List[Dict[str, Any]]:
    params = {
        "filter.term": term,
        "filter.locationId": location_id,
        "filter.limit": str(limit),
    }
    resp = requests.get(PROD_URL, headers=_auth_headers(), params=params, timeout=20)
    resp.raise_for_status()
    return resp.json().get("data", [])


def _pick_cheapest_item(products_json: List[Dict[str, Any]]) -> Tuple[float, Dict[str, Any]] | None:
    best: Tuple[float, Dict[str, Any]] | None = None
    for p in products_json:
        brand = p.get("brand") or ""
        desc = p.get("description") or ""
        items = p.get("items") or []
        for it in items:
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


def search_kroger(
    lat: float,
    lon: float,
    items_tokens: List[str],
    radius_miles: int,
    lambda_per_mile: float,
) -> Dict[str, Any]:
    locs = _get_locations(lat, lon, radius_miles, limit=25)

    stores: List[Dict[str, Any]] = []
    for L in locs:
        sid = L.get("locationId")
        if not sid:
            continue

        name = L.get("name") or "Store"
        geo = (L.get("geolocation") or {})
        s_lat = geo.get("latitude")
        s_lon = geo.get("longitude")
        if s_lat is None or s_lon is None:
            continue

        distance_miles = _haversine(lat, lon, float(s_lat), float(s_lon))

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

        stores.append(
            {
                "store_id": sid,
                "store_name": name,
                "city": city,
                "lat": float(s_lat),
                "lon": float(s_lon),
                "distance_miles": round(distance_miles, 2),
                "items": found_map,
                "items_details": details,
                "items_found": len(found_map),
                "items_missing": missing,
                "total_price": round(total, 2),
                "score": round(score, 2),
            }
        )

    if items_tokens:
        full = [s for s in stores if not s["items_missing"]]
        partial = [s for s in stores if s["items_missing"]]
    else:
        full, partial = stores, []

    full.sort(key=lambda s: (s["total_price"], s["distance_miles"]))
    partial.sort(
        key=lambda s: (len(s["items_missing"]), s["total_price"] or 1e9, s["distance_miles"])
    )

    best = full[0] if full else (partial[0] if partial else None)
    return {"best": best, "stores_full": full, "stores_partial": partial}
