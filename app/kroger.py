# app/kroger.py
from __future__ import annotations

import base64
import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

KROGER_BASE = "https://api.kroger.com"
TOKEN_URL = f"{KROGER_BASE}/v1/connect/oauth2/token"
LOC_URL = f"{KROGER_BASE}/v1/locations"
PROD_URL = f"{KROGER_BASE}/v1/products"

# Very simple in-memory token cache
_token_cache: Dict[str, Any] = {"access_token": None, "exp": 0}


# ---------- auth helpers ----------

def _b64_client() -> str:
    cid = os.getenv("KROGER_CLIENT_ID", "")
    sec = os.getenv("KROGER_CLIENT_SECRET", "")
    if not cid or not sec:
        raise RuntimeError(
            "KROGER_CLIENT_ID / KROGER_CLIENT_SECRET missing from .env"
        )
    raw = f"{cid}:{sec}".encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")


def _get_token() -> str:
    """
    Client-credentials token for Kroger APIs.
    Uses KROGER_SCOPES_CLIENT (preferred) or KROGER_SCOPE (fallback).
    """
    now = time.time()
    if _token_cache["access_token"] and _token_cache["exp"] > now + 30:
        return _token_cache["access_token"]

    # Prefer the new name, fall back to the old one
    scope = (
        os.getenv("KROGER_SCOPES_CLIENT")
        or os.getenv("KROGER_SCOPE", "")
    ).strip()

    headers = {
        "Authorization": f"Basic {_b64_client()}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    data = {"grant_type": "client_credentials"}
    if scope and scope.upper() != "N/A":
        data["scope"] = scope

    r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=15)
    if r.status_code == 401:
        # Surface a very clear auth error
        try:
            body = r.json()
        except Exception:
            body = r.text
        raise RuntimeError(
            f"Kroger token request unauthorized (401). "
            f"Check client id/secret and scopes. Response: {body}"
        )
    try:
        r.raise_for_status()
    except requests.HTTPError:
        # Bubble up full body for easier debugging
        try:
            body = r.json()
        except Exception:
            body = r.text
        raise RuntimeError(f"Kroger token HTTP {r.status_code}: {body}")

    j = r.json()
    _token_cache["access_token"] = j["access_token"]
    _token_cache["exp"] = now + int(j.get("expires_in", 1700))
    return _token_cache["access_token"]


def _auth_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Accept": "application/json",
    }


# ---------- small math helper ----------

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance in miles between two lat/lon points.
    """
    R = 3958.8  # Earth radius in miles
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------- low-level Kroger API wrappers ----------

def _get_locations(
    lat: float,
    lon: float,
    radius_miles: int,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Call Locations API: GET /v1/locations

    Uses filter.latLong.near, filter.radiusInMiles, filter.limit
    as shown in the OpenAPI document you pasted.
    """
    radius = max(1, min(int(radius_miles), 100))
    limit = max(1, min(int(limit), 200))

    params = {
        # NOTE: .near suffix to match spec
        "filter.latLong.near": f"{lat},{lon}",
        "filter.radiusInMiles": str(radius),
        "filter.limit": str(limit),
        # optional: filter.chain, filter.department, etc could go here
    }

    r = requests.get(LOC_URL, headers=_auth_headers(), params=params, timeout=15)
    try:
        r.raise_for_status()
    except requests.HTTPError:
        try:
            body = r.json()
        except Exception:
            body = r.text
        raise RuntimeError(f"Kroger locations HTTP {r.status_code}: {body}")

    j = r.json() or {}
    return j.get("data", [])


def _get_products(
    term: str,
    location_id: str,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    """
    Call Products API: GET /v1/products

    Requires product.compact scope on the token.
    """
    limit = max(1, min(int(limit), 50))
    params = {
        "filter.term": term,
        "filter.locationId": location_id,
        "filter.limit": str(limit),
    }

    r = requests.get(PROD_URL, headers=_auth_headers(), params=params, timeout=20)
    try:
        r.raise_for_status()
    except requests.HTTPError:
        try:
            body = r.json()
        except Exception:
            body = r.text
        raise RuntimeError(
            f"Kroger products HTTP {r.status_code} for term={term!r}, "
            f"location_id={location_id!r}: {body}"
        )

    j = r.json() or {}
    return j.get("data", [])


def _pick_cheapest_item(
    products_json: List[Dict[str, Any]]
) -> Optional[Tuple[float, Dict[str, Any]]]:
    """
    From Kroger product payload, pick the cheapest item (by regular or promo price).
    Returns (price, friendly_meta) or None.
    """
    best: Optional[Tuple[float, Dict[str, Any]]] = None

    for p in products_json:
        brand = p.get("brand") or ""
        desc = p.get("description") or ""
        items = p.get("items") or []
        for it in items:
            size = it.get("size") or it.get("packageSize") or ""
            pr = it.get("price") or {}  # {"regular": X, "promo": Y}
            price: Optional[float] = None
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


# ---------- main integration used by /api/search ----------

def search_kroger(
    lat: float,
    lon: float,
    items_tokens: List[str],
    radius_miles: int,
    lambda_per_mile: float,
) -> Dict[str, Any]:
    """
    Shape the response to match your existing /api/search output:
      { best, stores_full, stores_partial }
    """
    locs = _get_locations(lat, lon, radius_miles, limit=25)

    stores: List[Dict[str, Any]] = []

    for L in locs:
        sid = str(L.get("locationId") or "")
        name = L.get("name") or "Store"

        geo = L.get("geolocation") or {}
        s_lat = geo.get("latitude")
        s_lon = geo.get("longitude")
        if s_lat is None or s_lon is None:
            # Skip locations without geo
            continue

        s_lat = float(s_lat)
        s_lon = float(s_lon)
        distance_miles = _haversine(lat, lon, s_lat, s_lon)

        addr = L.get("address") or {}
        city = addr.get("city") or ""

        # For each token (e.g. 'milk', 'bananas'), query products at this location
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
            except Exception as e:
                # Don't blow up the whole store because one term failed
                print(f"[kroger] product lookup failed for {t!r} at {sid}: {e}")
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
            "items_details": details,  # for richer UI
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
    partial.sort(
        key=lambda s: (
            len(s["items_missing"]),
            s["total_price"] or 1e9,
            s["distance_miles"],
        )
    )

    best = full[0] if full else (partial[0] if partial else None)

    return {
        "best": best,
        "stores_full": full,
        "stores_partial": partial,
    }
