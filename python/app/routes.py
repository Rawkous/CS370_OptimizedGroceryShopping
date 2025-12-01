import os
from pathlib import Path
from flask import Blueprint, jsonify, request, send_from_directory, Response, render_template
from mysql.connector import Error  

from .db import query
from .logic import demo_store_scoring, check_items_in_price_history, simulate_route
from .index_fallback import INDEX_FALLBACK
from .kroger import search_kroger

PROJECT_ROOT = Path(__file__).resolve().parents[2]

root_bp = Blueprint("root", __name__)
api_bp  = Blueprint("api", __name__)


@root_bp.get("/")
def homepage():
    return render_template("index.html")



@root_bp.get("/page2")
def page2():
    html_dir = PROJECT_ROOT / "html"
    return send_from_directory(str(html_dir), "page2.html")



@root_bp.get("/favicon.ico")
def favicon():
    return ("", 204)


@root_bp.get("/.well-known/appspecific/com.chrome.devtools.json")
def chrome_devtools_probe():
    return jsonify({})



# HEALTH ENDPOINT

@api_bp.get("/healthz")
def health():
    try:
        rows = query("SELECT 1 AS ok", ())
        return jsonify({
            "ok": bool(rows and rows[0].get("ok") == 1),
            "host": os.getenv("DB_HOST"),
            "port": int(os.getenv("DB_PORT", "3306")),
        })
    except Error as e:
        return jsonify({
            "ok": False, "error": str(e),
            "host": os.getenv("DB_HOST"),
            "port": int(os.getenv("DB_PORT", "3306")),
        }), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500



# ITEM PICKER ENDPOINT

@api_bp.get("/api/items")
def api_items():
    q = (request.args.get("q") or "").strip()
    try:
        limit = max(1, min(200, int(request.args.get("limit", "50"))))
    except Exception:
        limit = 50

    params = []
    like_sql = ""
    if q:
        like_sql = "AND p.name LIKE %s"
        params.append(f"%{q}%")

    sql = f"""
        SELECT DISTINCT TRIM(p.name) AS item_name
        FROM store_product sp
        JOIN product p ON p.upc = sp.product_upc
        WHERE p.name IS NOT NULL AND p.name <> '' {like_sql}
        ORDER BY item_name ASC
        LIMIT %s
    """
    params.append(limit)
    try:
        rows = query(sql, tuple(params))
        return jsonify([r["item_name"] for r in rows])
    except Exception as e:
        return jsonify({"error": f"DB error: {e}"}), 500



# SEARCH ENDPOINT (DB + KROGER)
@api_bp.get("/api/search")
def api_search():
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except Exception:
        return jsonify({"error": "lat and lon are required floats"}), 400

    items_raw = request.args.get("items", "")
    items_tokens = [i.strip().lower() for i in items_raw.split(",") if i.strip()]

    try:
        radius_miles = float(request.args.get("radius_miles", "10"))
        lambda_per_mile = float(request.args.get("lambda_per_mile", "0.5"))
    except Exception:
        return jsonify({"error": "radius_miles and lambda_per_mile must be numbers"}), 400

    
    source = (request.args.get("source") or "").lower()
    if source == "kroger":
        try:
            payload = search_kroger(lat, lon, items_tokens, int(radius_miles), float(lambda_per_mile))
            return jsonify({
                "query": {
                    "lat": lat, "lon": lon,
                    "radius_miles": radius_miles,
                    "items": items_tokens,
                    "lambda_per_mile": lambda_per_mile,
                    "source": "kroger"
                },
                **payload
            })
        except Exception as e:
            return jsonify({"error": f"Kroger error: {e}"}), 500

    
    radius_m = radius_miles * 1609.34
    base_sql = """
        SELECT
            s.id,
            s.name,
            ST_Y(s.location) AS latitude,
            ST_X(s.location) AS longitude,
            ST_Distance_Sphere(s.location, POINT(%s,%s)) AS meters,
            p.name AS item_name,
            sp.price
        FROM store s
        JOIN store_product sp ON sp.store_id = s.id
        JOIN product p ON p.upc = sp.product_upc
        WHERE ST_Distance_Sphere(s.location, POINT(%s,%s)) <= %s
    """
    params = [lon, lat, lon, lat, radius_m]

    if items_tokens:
        likes = " OR ".join(["LOWER(p.name) LIKE %s"] * len(items_tokens))
        base_sql += f" AND ({likes})"
        params.extend([f"%{t}%" for t in items_tokens])

    try:
        rows = query(base_sql, params)
    except Exception as e:
        return jsonify({"error": f"DB error: {e}"}), 500

    stores = {}
    for r in rows:
        sid = r["id"]
        s = stores.setdefault(sid, {
            "store_id": sid,
            "store_name": r["name"],
            "lat": float(r["latitude"]),
            "lon": float(r["longitude"]),
            "distance_miles": float(r["meters"]) / 1609.34,
            "items": {},
        })
        item_name = (r["item_name"] or "").lower()
        price = r["price"]
        if item_name and price is not None and items_tokens:
            for token in items_tokens:
                if token in item_name:
                    prev = s["items"].get(token)
                    pval = float(price)
                    if prev is None or pval < prev:
                        s["items"][token] = pval

    results = []
    for s in stores.values():
        if items_tokens:
            missing = [t for t in items_tokens if t not in s["items"]]
            total = sum(s["items"][t] for t in items_tokens if t in s["items"])
        else:
            missing, total = [], 0.0
        s["items_found"] = len(items_tokens) - len(missing)
        s["items_missing"] = missing
        s["total_price"] = round(total, 2)
        s["score"] = round(s["total_price"] + lambda_per_mile * s["distance_miles"], 2)
        results.append(s)

    if items_tokens:
        full = [s for s in results if not s["items_missing"]]
        partial = [s for s in results if s["items_missing"]]
    else:
        full, partial = results, []

    full.sort(key=lambda s: (s["total_price"], s["distance_miles"]))
    partial.sort(key=lambda s: (len(s["items_missing"]),
                                s["total_price"] or 1e9,
                                s["distance_miles"]))

    return jsonify({
        "query": {
            "lat": lat, "lon": lon,
            "radius_miles": radius_miles,
            "items": items_tokens,
            "lambda_per_mile": lambda_per_mile
        },
        "best": (full[0] if full else (partial[0] if partial else None)),
        "stores_full": full,
        "stores_partial": partial
    })


# ADDITIONAL API ENDPOINTS
@api_bp.get("/api/check-items")
def api_check_items():
    items_raw = request.args.get("items", "")
    items = [i.strip() for i in items_raw.split(",") if i.strip()]
    try:
        return jsonify(check_items_in_price_history(items))
    except Exception as e:
        return jsonify({"error": f"DB error: {e}"}), 500


@api_bp.get("/api/demo-scoring")
def api_demo_scoring():
    best, results = demo_store_scoring()
    return jsonify({"best": best, "results": results})


@api_bp.get("/api/sim-route")
def api_sim_route():
    try:
        start_lat = float(request.args.get("start_lat"))
        start_lon = float(request.args.get("start_lon"))
    except Exception:
        return jsonify({"error": "start_lat and start_lon required floats"}), 400
    n = int(request.args.get("n", "5"))
    gas_rate = float(request.args.get("gas_rate", "0.05"))
    return jsonify(simulate_route(start_lat, start_lon, n, gas_rate))

