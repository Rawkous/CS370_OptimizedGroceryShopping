import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import mysql.connector
from mysql.connector import pooling

from dotenv import load_dotenv
load_dotenv()


# -------- DB pool (reads .env) --------
def _db_config():
    return {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME"),
        "autocommit": True,
    }

pool = pooling.MySQLConnectionPool(pool_name="dbpool", pool_size=5, **_db_config())

def query(sql, params):
    conn = pool.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        rows = cur.fetchall()
        return rows
    finally:
        try: cur.close()
        except: pass
        try: conn.close()
        except: pass

# -------- App --------
app = Flask(__name__)
CORS(app)

@app.get("/")
def root():
    # serve the index.html sitting next to app.py
    return send_from_directory(".", "index.html")

@app.get("/healthz")
def health():
    # quick smoke check
    rows = query("SELECT 1 AS ok", ())
    return jsonify({"ok": rows[0]["ok"] == 1})

@app.get("/api/search")
def api_search():
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except Exception:
        return jsonify({"error": "lat and lon are required floats"}), 400

    # Items as comma-separated names; default empty list = show store inventory/prices without cart total
    items_raw = request.args.get("items", "")
    items = [i.strip() for i in items_raw.split(",") if i.strip()]
    items_lower = [i.lower() for i in items]

    radius_miles = float(request.args.get("radius_miles", "10"))
    lambda_per_mile = float(request.args.get("lambda_per_mile", "0.5"))
    radius_m = radius_miles * 1609.34

    # One SQL to fetch candidate stores+prices; aggregate in Python
    # NOTE: POINT expects (lon, lat)
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
    if items:
        placeholders = ", ".join(["%s"] * len(items))
        base_sql += f" AND p.name IN ({placeholders})"
        params.extend(items)

    rows = query(base_sql, params)

    # Aggregate: min price per item per store
    stores = {}
    for r in rows:
        sid = r["id"]
        if sid not in stores:
            stores[sid] = {
                "store_id": sid,
                "store_name": r["name"],
                "lat": float(r["latitude"]),
                "lon": float(r["longitude"]),
                "distance_miles": float(r["meters"]) / 1609.34,
                "items": {},  # item_name(lower) -> min price
            }
        if r["item_name"] and r["price"] is not None:
            key = r["item_name"].lower()
            price = float(r["price"])
            prev = stores[sid]["items"].get(key)
            if prev is None or price < prev:
                stores[sid]["items"][key] = price

    # Compute totals / coverage / score
    results = []
    for s in stores.values():
        if items:
            missing = [n for n in items_lower if n not in s["items"]]
            total = sum(s["items"][n] for n in items_lower if n in s["items"])
        else:
            missing, total = [], 0.0

        s["items_found"] = len(items_lower) - len(missing)
        s["items_missing"] = missing
        s["total_price"] = round(total, 2)
        s["score"] = round(s["total_price"] + lambda_per_mile * s["distance_miles"], 2)
        results.append(s)

    # Prefer stores that have ALL items; then sort by (total, distance)
    if items:
        full = [s for s in results if not s["items_missing"]]
        partial = [s for s in results if s["items_missing"]]
    else:
        full, partial = results, []

    full.sort(key=lambda s: (s["total_price"], s["distance_miles"]))
    partial.sort(key=lambda s: (len(s["items_missing"]), s["total_price"] or 1e9, s["distance_miles"]))

    return jsonify({
        "query": {
            "lat": lat, "lon": lon, "radius_miles": radius_miles,
            "items": items, "lambda_per_mile": lambda_per_mile
        },
        "best": (full[0] if full else (partial[0] if partial else None)),
        "stores_full": full,
        "stores_partial": partial
    })

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
