# app.py — unified web app + SSH tunnel + DB pool + your console features + map UI
# -----------------------------------------------------------------------------
#  log in Everyone uses http://10.0.0.118:5000
# , not https
# Modes:
#   Web server (default):      python app.py
#   Check items (console):     python app.py check-items --items "banana,egg,bread"
#   Demo scoring (console):    python app.py demo-scoring
#   Simulate route (console):  python app.py sim-route --lat 33.7490 --lon -84.3880 --n 5 --gas 0.05
#   DB smoke check (console):  python app.py db-check
# -----------------------------------------------------------------------------

import os
import atexit
import math
import random
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from dotenv import load_dotenv
from mysql.connector import pooling, Error

# Optional dependency (only needed if USE_SSH_TUNNEL=1)
try:
    from sshtunnel import SSHTunnelForwarder
except Exception:
    SSHTunnelForwarder = None

# ----------------------------- Load .env first -------------------------------
load_dotenv()  # ensure env vars exist BEFORE we decide how to connect


# =========================== SSH Tunnel (optional) ============================
_TUNNEL = None

def maybe_start_tunnel():
    """Start an SSH tunnel if USE_SSH_TUNNEL=1 in .env."""
    if os.getenv("USE_SSH_TUNNEL", "0") != "1":
        return
    if SSHTunnelForwarder is None:
        print("⚠️  sshtunnel not installed; cannot start SSH tunnel. Set USE_SSH_TUNNEL=0 or install sshtunnel.")
        return

    global _TUNNEL
    if _TUNNEL:
        return

    ssh_host = os.getenv("SSH_HOST", "blue.cs.sonoma.edu")
    ssh_port = int(os.getenv("SSH_PORT", "22"))
    ssh_user = os.getenv("SSH_USER", "lhinson")
    ssh_password = os.getenv("SSH_PASSWORD", "Kappa123")
    remote_host = os.getenv("REMOTE_DB_HOST", "127.0.0.1")
    remote_port = int(os.getenv("REMOTE_DB_PORT", "3306"))
    local_port  = int(os.getenv("LOCAL_TUNNEL_PORT", "3307"))

    _TUNNEL = SSHTunnelForwarder(
        (ssh_host, ssh_port),
        ssh_username=ssh_user,
        ssh_password=ssh_password,
        remote_bind_address=(remote_host, remote_port),
        local_bind_address=("127.0.0.1", local_port),
    )
    _TUNNEL.start()
    # Point DB at the local tunnel
    os.environ["DB_HOST"] = "127.0.0.1"
    os.environ["DB_PORT"] = str(_TUNNEL.local_bind_port)
    print(f"🔗 SSH tunnel started → 127.0.0.1:{_TUNNEL.local_bind_port}")

def _stop_tunnel():
    global _TUNNEL
    if _TUNNEL:
        try:
            _TUNNEL.stop()
            print("🔌 SSH tunnel stopped.")
        except Exception:
            pass
        _TUNNEL = None

atexit.register(_stop_tunnel)

# Start tunnel BEFORE creating the pool
maybe_start_tunnel()


# ============================ DB Pool & Query =================================
def _db_config():
    return {
        "host": os.getenv("DB_HOST", "blue.cs.sonoma.edu"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "SDD_003_user"),
        "password": os.getenv("DB_PASSWORD", "SDD_003_29"),
        "database": os.getenv("DB_NAME", "SDD_003_database"),
        "autocommit": True,
        "connection_timeout": 10,
    }

pool = pooling.MySQLConnectionPool(pool_name="dbpool", pool_size=5, **_db_config())

def query(sql, params=()):
    conn = pool.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        try: cur.close()
        except: pass
        try: conn.close()
        except: pass


# ============================ Helper Logic (yours) ============================
def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance (miles)."""
    R = 3958.8
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = (math.sin(dLat/2)**2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dLon/2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def find_shortest_route(start, items):
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

def demo_store_scoring():
    stores = [
        {"name": "Supermarket", "inventory": ['banana','egg','bread','soda','cookies','sugar'], "distance": 5},
        {"name": "MiniMart",   "inventory": ['banana','milk','bread','chips'],                "distance": 3},
        {"name": "OrganicShop","inventory": ['bread','sugar','apple','lettuce'],             "distance": 8},
        {"name": "CornerStore","inventory": ['banana','egg'],                                 "distance": 2},
    ]
    userItems = ['banana','egg','bread','sugar']

    best, results = None, []
    best_score = -1
    for s in stores:
        matches = set(s["inventory"]) & set(userItems)
        score = len(matches) / s["distance"] if s["distance"] else float("inf")
        row = {
            "Store": s["name"], "Distance": s["distance"],
            "MatchedItems": sorted(list(matches)),
            "MatchCount": len(matches), "Score": round(score, 3)
        }
        results.append(row)
        if score > best_score:
            best, best_score = row, score
    return best, results

def check_items_in_price_history(items):
    """Check item names via product join (price_history.product_upc -> product.upc)."""
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


# ============================ Flask App & Routes ==============================
INDEX_FALLBACK = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Closest & Cheapest</title>

<link
  rel="stylesheet"
  href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
  crossorigin=""
/>
<script
  src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
  crossorigin=""
></script>

<style>
body{font-family:system-ui,Arial,sans-serif;margin:24px;max-width:900px}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
input,button{padding:8px;font-size:15px}
.card{border:1px solid #ddd;border-radius:8px;padding:12px;margin:8px 0}
table{width:100%;border-collapse:collapse}
th,td{border-bottom:1px solid #eee;padding:8px;text-align:left}
.muted{color:#666}
#map{height:400px;margin-top:16px;border-radius:8px;}
</style>
</head><body>
<h1>Find the closest & cheapest store</h1>
<div class="row">
  <button id="geo">Use my location</button>
  <input id="lat" type="number" step="any" placeholder="Latitude"/>
  <input id="lon" type="number" step="any" placeholder="Longitude"/>
</div>
<div class="row">
  <input id="items" style="min-width:380px" placeholder="Items (comma-separated): banana, egg, bread"/>
  <input id="radius" type="number" step="0.1" value="10" style="width:120px"/> miles radius
  <input id="lambda" type="number" step="0.1" value="0.5" style="width:120px"/> $/mile weight
  <button id="search">Search</button>
</div>
<div id="map"></div>
<div id="result"></div>

<script>
const apiBase = window.location.origin;
let map = null, markerGroup = null;

function initMap(lat, lon){
  const mapEl = document.getElementById('map');
  if (!map){
    map = L.map('map').setView([lat, lon], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);
    markerGroup = L.layerGroup().addTo(map);
  } else {
    map.setView([lat, lon], 13);
    markerGroup.clearLayers();
  }
  const user = L.marker([lat, lon], { title: 'You' })
    .addTo(markerGroup)
    .bindPopup('<b>Your location</b>');
  user.openPopup();
}

function getInputs(){
  const lat = parseFloat(document.getElementById('lat').value);
  const lon = parseFloat(document.getElementById('lon').value);
  return { lat, lon };
}

document.getElementById('geo').onclick = () => {
  // Geolocation only works on https, http://localhost or http://127.0.0.1
  if (!navigator.geolocation){
    alert('Geolocation not supported by this browser.');
    const {lat, lon} = getInputs();
    if (!isNaN(lat) && !isNaN(lon)) initMap(lat, lon);
    return;
  }
  navigator.geolocation.getCurrentPosition(
    pos => {
      const lat = +pos.coords.latitude.toFixed(6);
      const lon = +pos.coords.longitude.toFixed(6);
      document.getElementById('lat').value = lat;
      document.getElementById('lon').value = lon;
      initMap(lat, lon);
    },
    err => {
      console.warn('Geolocation error:', err.message);
      alert(err.message + '\\nTip: open the app on http://127.0.0.1:5000 or enable location.');
      const {lat, lon} = getInputs();
      if (!isNaN(lat) && !isNaN(lon)) initMap(lat, lon);
    },
    { enableHighAccuracy:true, timeout:8000 }
  );
};

document.getElementById('search').onclick = async () => {
  const latStr = document.getElementById('lat').value.trim();
  const lonStr = document.getElementById('lon').value.trim();
  if (!latStr || !lonStr) return alert("Please provide lat/lon (or click 'Use my location').");

  const lat = parseFloat(latStr), lon = parseFloat(lonStr);
  if (!map) initMap(lat, lon);

  const items = document.getElementById('items').value.trim();
  const radius = document.getElementById('radius').value.trim() || '10';
  const lambda = document.getElementById('lambda').value.trim() || '0.5';

  const url = new URL(apiBase + '/api/search');
  url.searchParams.set('lat', lat); url.searchParams.set('lon', lon);
  if (items) url.searchParams.set('items', items);
  url.searchParams.set('radius_miles', radius);
  url.searchParams.set('lambda_per_mile', lambda);

  const res = await fetch(url);
  const data = await res.json();
  render(data);
};

function render(data){
  const el = document.getElementById('result');
  if (data.error){
    el.innerHTML = `<div class="card">Error: ${data.error}</div>`;
    return;
  }

  let html = '';
  if (data.best){
    const b = data.best;
    html += `<div class="card"><h3>Best store: ${b.store_name}</h3>
      <div class="muted">${b.distance_miles.toFixed(2)} miles • Total $${b.total_price.toFixed(2)} • Score ${b.score.toFixed(2)}</div>
      ${Array.isArray(b.items_missing) && b.items_missing.length ? `<div class="muted">Missing: ${b.items_missing.join(', ')}</div>` : ''}</div>`;
  } else {
    html += `<div class="card">No stores found in the selected radius.</div>`;
  }

  const rows = (data.stores_full||[]).concat(data.stores_partial||[]);
  if (rows.length){
    html += `<table><thead><tr><th>Store</th><th>Distance</th><th>Total</th><th>Items Found</th><th>Missing</th></tr></thead><tbody>`;
    for (const s of rows){
      html += `<tr><td>${s.store_name}</td>
        <td>${s.distance_miles.toFixed(2)} mi</td>
        <td>$${(s.total_price||0).toFixed(2)}</td>
        <td>${s.items_found}</td>
        <td>${(s.items_missing||[]).join(', ')}</td></tr>`;
    }
    html += `</tbody></table>`;
  }
  el.innerHTML = html;

  if (map && markerGroup){
    markerGroup.clearLayers();
    const userLat = parseFloat(document.getElementById('lat').value);
    const userLon = parseFloat(document.getElementById('lon').value);
    L.marker([userLat, userLon], { title: 'You' })
      .addTo(markerGroup)
      .bindPopup('<b>Your location</b>');

    if (rows.length){
      const best = data.best ? data.best.store_id : null;
      for (const s of rows){
        const m = L.marker([s.lat, s.lon], { title: s.store_name }).addTo(markerGroup);
        m.bindPopup(`<b>${s.store_name}</b><br>${s.distance_miles.toFixed(2)} mi<br>$${(s.total_price||0).toFixed(2)}`);
        if (s.store_id === best) m.setZIndexOffset(1000);
      }
      const bounds = L.latLngBounds();
      markerGroup.eachLayer(l => bounds.extend(l.getLatLng()));
      map.fitBounds(bounds, { padding: [50, 50] });
    }
  }
}
</script>
  </body></html>
           """
app = Flask(__name__)
CORS(app)

@app.get("/")
def root():
    # Serve ./index.html if present, else a built-in page so this file is standalone
    if Path("index.html").exists():
        return send_from_directory(".", "index.html")
    return Response(INDEX_FALLBACK, mimetype="text/html")

@app.get("/healthz")
def health():
    try:
        rows = query("SELECT 1 AS ok", ())
        return jsonify({"ok": rows and rows[0]["ok"] == 1,
                        "host": os.getenv("DB_HOST"), "port": int(os.getenv("DB_PORT", "3306"))})
    except Error as e:
        return jsonify({"ok": False, "error": str(e),
                        "host": os.getenv("DB_HOST"), "port": int(os.getenv("DB_PORT", "3306"))}), 500

@app.get("/api/search")
def api_search():
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except Exception:
        return jsonify({"error": "lat and lon are required floats"}), 400

    # tokens user typed, lowercased
    items_raw = request.args.get("items", "")
    items_tokens = [i.strip().lower() for i in items_raw.split(",") if i.strip()]

    radius_miles = float(request.args.get("radius_miles", "10"))
    lambda_per_mile = float(request.args.get("lambda_per_mile", "0.5"))
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

    # fuzzy name match so "bread" finds "White Bread"
    if items_tokens:
        likes = " OR ".join(["LOWER(p.name) LIKE %s"] * len(items_tokens))
        base_sql += f" AND ({likes})"
        params.extend([f"%{t}%" for t in items_tokens])

    rows = query(base_sql, params)

    # Aggregate cheapest price per requested token per store
    stores = {}
    for r in rows:
        sid = r["id"]
        s = stores.setdefault(sid, {
            "store_id": sid,
            "store_name": r["name"],
            "lat": float(r["latitude"]),
            "lon": float(r["longitude"]),
            "distance_miles": float(r["meters"]) / 1609.34,
            "items": {},  # token -> min price
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

    # Build results and scores
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

    # Prefer stores with all items, then sort by total then distance
    if items_tokens:
        full = [s for s in results if not s["items_missing"]]
        partial = [s for s in results if s["items_missing"]]
    else:
        full, partial = results, []

    full.sort(key=lambda s: (s["total_price"], s["distance_miles"]))
    partial.sort(key=lambda s: (len(s["items_missing"]),
                                s["total_price"] or 1e9, s["distance_miles"]))

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

@app.get("/api/check-items")
def api_check_items():
    items_raw = request.args.get("items", "")
    items = [i.strip() for i in items_raw.split(",") if i.strip()]
    return jsonify(check_items_in_price_history(items))

@app.get("/api/demo-scoring")
def api_demo_scoring():
    best, results = demo_store_scoring()
    return jsonify({"best": best, "results": results})

@app.get("/api/sim-route")
def api_sim_route():
    try:
        start_lat = float(request.args.get("start_lat"))
        start_lon = float(request.args.get("start_lon"))
    except Exception:
        return jsonify({"error": "start_lat and start_lon required floats"}), 400
    n = int(request.args.get("n", "5"))
    gas_rate = float(request.args.get("gas_rate", "0.05"))
    items = [(random.uniform(-90, 90), random.uniform(-180, 180)) for _ in range(n)]
    route, total_distance = find_shortest_route((start_lat, start_lon), items)
    gas_used = total_distance * gas_rate
    return jsonify({
        "start": {"lat": start_lat, "lon": start_lon},
        "items": items, "route": route,
        "total_distance_miles": round(total_distance, 2),
        "gas_used": round(gas_used, 2)
    })


# ============================== CLI Entrypoint ================================
def _print_db_target():
    print(f"DB target → host={os.getenv('DB_HOST')} port={os.getenv('DB_PORT')} "
          f"user={os.getenv('DB_USER')} db={os.getenv('DB_NAME')}")

def _db_smoke():
    try:
        rows = query("SELECT 1 AS ok", ())
        print("✅ DB OK", rows)
    except Exception as e:
        print("❌ DB FAILED:", e)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Closest & Cheapest — unified app")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("web", help="Run the web server (default)")

    p_check = sub.add_parser("check-items", help="Console: check item names in price_history via product join")
    p_check.add_argument("--items", required=True, help="Comma-separated list, e.g. 'banana,egg,bread'")

    sub.add_parser("demo-scoring", help="Console: run demo store scoring")
    p_sim = sub.add_parser("sim-route", help="Console: simulate route + gas")
    p_sim.add_argument("--lat", type=float, required=True)
    p_sim.add_argument("--lon", type=float, required=True)
    p_sim.add_argument("--n", type=int, default=5)
    p_sim.add_argument("--gas", type=float, default=0.05)

    sub.add_parser("db-check", help="Console: simple DB health check")

    args = parser.parse_args()
    cmd = args.cmd or "web"

    # Sanity print
    _print_db_target()

    if cmd == "web":
        # quick DB smoke on startup
        _db_smoke()
        # 0.0.0.0 so teammates on your LAN can access http://<your-ip>:5000
        app.run(host=os.getenv("HOST", "0.0.0.0"),
                port=int(os.getenv("PORT", "5000")),
                debug=True, use_reloader=False)

    elif cmd == "check-items":
        items = [i.strip() for i in args.items.split(",") if i.strip()]
        res = check_items_in_price_history(items)
        print("Found:", res["found"])
        print("Missing:", res["missing"])

    elif cmd == "demo-scoring":
        best, results = demo_store_scoring()
        print("=== Demo store scoring ===")
        for r in results:
            print(r)
        print("Best:", best)

    elif cmd == "sim-route":
        start = (args.lat, args.lon)
        items = [(random.uniform(-90, 90), random.uniform(-180, 180)) for _ in range(args.n)]
        route, total = find_shortest_route(start, items)
        gas_used = total * args.gas
        print("Route:", route)
        print(f"Total distance: {total:.2f} mi   Gas used: {gas_used:.2f} gal")

    elif cmd == "db-check":
        _db_smoke()
