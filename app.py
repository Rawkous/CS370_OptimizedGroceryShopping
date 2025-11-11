# app.py — unified web app + SSH tunnel + DB pool + console helpers + map UI
# -----------------------------------------------------------------------------
#  Everyone uses http://10.0.0.118:5000  (http, not https)
#
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
    ssh_user = os.getenv("SSH_USER")       # no default; must be set if tunneling
    ssh_password = os.getenv("SSH_PASSWORD")  # no default; must be set if tunneling
    remote_host = os.getenv("REMOTE_DB_HOST", "127.0.0.1")
    remote_port = int(os.getenv("REMOTE_DB_PORT", "3306"))
    local_port  = int(os.getenv("LOCAL_TUNNEL_PORT", "3307"))

    if not ssh_user or not ssh_password:
        print("❌ USE_SSH_TUNNEL=1 but SSH_USER/SSH_PASSWORD not set in environment; skipping tunnel startup.")
        return

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

# ============================ DB Pool & Query ================================
def _db_config():
    """
    Pull DB settings from environment. We deliberately DO NOT default sensitive values.
    Required: DB_USER, DB_PASSWORD, DB_NAME
    Optional: DB_HOST (default blue.cs.sonoma.edu), DB_PORT (default 3306)
    """
    cfg = {
        "host": os.getenv("DB_HOST", "blue.cs.sonoma.edu"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME"),
        "autocommit": True,
        "connection_timeout": 10,
    }
    missing = [k for k, v in (("DB_USER", cfg["user"]),
                              ("DB_PASSWORD", cfg["password"]),
                              ("DB_NAME", cfg["database"])) if not v]
    if missing:
        print(f"❌ Missing required DB env vars: {', '.join(missing)}")
        print("   Make sure your .env has DB_USER, DB_PASSWORD, DB_NAME.")
    return cfg

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

# ============================ Helper Logic ===================================
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
# This fallback page includes all UX upgrades and calls our JSON APIs below.
INDEX_FALLBACK = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Closest & Cheapest</title>

  <!-- Leaflet -->
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin=""/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>

  <style>
    :root{
      --bg:#0f172a; --panel:#121a2c; --muted:#9aa3b2; --border:#1f2937; --text:#e6eef7;
      --accent:#22c55e; --accent-2:#60a5fa; --card:#0b1220; --chip:#0e1a30; --table:#0c1626;
      --btn:#1e293b; --btn-border:#253041;
    }
    body.light{
      --bg:#f6f7fb; --panel:#fff; --muted:#5b6675; --border:#e6e8ee; --text:#0f172a;
      --accent:#16a34a; --accent-2:#3b82f6; --card:#fff; --chip:#eef2ff; --table:#fff;
      --btn:#eef2ff; --btn-border:#dbe2ff;
    }
    *{box-sizing:border-box}
    body{
      font-family: system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
      margin:0;
      background:
        radial-gradient(1200px 600px at 15% -10%, #16233f 0%, transparent 60%),
        radial-gradient(1000px 500px at 110% 10%, #132530 0%, transparent 60%),
        var(--bg);
      color:var(--text);
      min-height:100vh;
    }
    .container{max-width:1100px;margin:24px auto 48px;padding:0 16px}
    h1{font-size:clamp(1.4rem,1.1rem+2vw,2.1rem);margin:0 0 14px;font-weight:800;text-shadow:0 1px 0 rgba(0,0,0,.35)}
    .panel{background:linear-gradient(180deg,rgba(255,255,255,.02),rgba(255,255,255,.01));border:1px solid var(--border);border-radius:14px;padding:14px;box-shadow:0 10px 30px rgba(0,0,0,.35)}
    .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
    .grow{flex:1 1 auto}
    label.small{font-size:12px;color:var(--muted);display:block;margin-bottom:6px}
    input,button{border-radius:10px;border:1px solid var(--border);background:var(--card);color:var(--text);padding:10px 12px;font-size:15px;outline:none}
    input::placeholder{color:#6b7280}
    button{background:linear-gradient(180deg,var(--btn),#0f172a22);border-color:var(--btn-border);cursor:pointer;transition:transform .08s,box-shadow .15s,background .2s}
    button:hover{box-shadow:0 6px 16px rgba(34,197,94,.25)}
    button:active{transform:translateY(1px)}
    .btn-accent{background:linear-gradient(180deg,var(--accent-2),#2563eb);border-color:#1d4ed8;color:#fff}
    .btn-primary{background:linear-gradient(180deg,var(--accent),#16a34a);border-color:#15803d;color:#fff}
    .chip{display:inline-block;padding:3px 8px;border-radius:999px;background:var(--chip);border:1px solid #1b2a45;font-size:12px}
    #map{height:460px;border-radius:12px;border:1px solid var(--border);background:#0d1324}
    .overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);align-items:center;justify-content:center;z-index:9999}
    .spinner{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:18px 22px;display:flex;align-items:center;gap:12px;min-width:260px;box-shadow:0 20px 50px rgba(0,0,0,.5)}
    .spinner:before{content:"";width:18px;height:18px;border-radius:50%;border:3px solid var(--border);border-top-color:var(--accent);animation:spin 1s linear infinite}
    @keyframes spin{to{transform:rotate(360deg)}}
    .card{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:12px;margin:12px 0}
    .muted{color:var(--muted)}
    .kpi{display:flex;gap:10px;flex-wrap:wrap}
    .kpi span{padding:6px 10px;border-radius:8px;background:#0c1324;border:1px solid var(--border)}
    .kpi .pill{background:var(--card)}
    .result-header{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
    .table-wrap{background:var(--panel);border:1px solid var(--border);border-radius:12px;overflow:auto;max-height:52vh}
    table{width:100%;border-collapse:collapse}
    thead th{position:sticky;top:0;background:#0e1a30;color:#cbd5e1;text-align:left;font-weight:700;font-size:13px;padding:10px;border-bottom:1px solid var(--border)}
    tbody td{padding:10px;border-bottom:1px dashed #1c2434;font-size:14px;background:var(--table)}
    tbody tr:hover{background:#0c1628}
    tr.highlight td{background:#10203a}
    #comparePanel{display:none;margin-top:10px}
    #comparePanel.active{display:block}
    .compare-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
    .compare-card{border:1px solid var(--border);border-radius:10px;padding:10px;background:var(--panel)}
    .modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.55);justify-content:center;align-items:center;z-index:9990}
    .modal-content{background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:12px;padding:16px;max-height:80vh;min-width:340px;width:min(640px,90vw);box-shadow:0 20px 60px rgba(0,0,0,.45)}
    #itemList{max-height:60vh;overflow-y:auto;border:1px solid var(--border);background:var(--card);padding:6px;border-radius:8px}
    #itemList label{display:block;padding:6px 4px;cursor:pointer}
    .spacer{flex:1}
    .toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:end}
    @media (max-width:640px){#map{height:260px}.toolbar{flex-direction:column;align-items:stretch}}
  </style>
</head>
<body>
<div class="container">
  <h1>Find the closest & cheapest store</h1>

  <div class="panel">
    <div class="toolbar">
      <div>
        <label class="small">Latitude</label>
        <input id="lat" type="number" step="any" placeholder="Latitude" style="width:220px"/>
      </div>
      <div>
        <label class="small">Longitude</label>
        <input id="lon" type="number" step="any" placeholder="Longitude" style="width:220px"/>
      </div>
      <div class="spacer"></div>
      <button id="geo" class="btn-accent">Use my location</button>
      <button id="searchBtn" class="btn-primary">Find stores</button>
      <button id="themeToggle" title="Toggle theme">🌙</button>
    </div>

    <div class="row">
      <button id="selectItemsBtn">Select items</button>
      <div id="selectedItems" class="muted">(none)</div>
    </div>

    <div class="row">
      <div style="min-width:160px">
        <label class="small">Miles radius</label>
        <input id="radius" type="number" step="1" min="1" value="10" style="width:160px"/>
      </div>
      <div style="min-width:220px">
        <label class="small">Distance penalty ( $ / mi )</label>
        <div style="display:flex;gap:8px;align-items:center">
          <input id="lambda" type="number" step="0.1" value="0.5" style="width:100px"/>
          <input id="lambdaRange" type="range" min="0" max="5" step="0.1" value="0.5" style="width:160px"/>
        </div>
      </div>
    </div>

    <div class="muted" style="margin:8px 0 10px">
      <span>Score = <b>total price</b> + λ × <b>distance (mi)</b>. Lower is better.</span>
    </div>

    <div id="map" class="panel" style="padding:0;box-shadow:none"></div>

    <div id="bestWrap" class="card" style="display:none"></div>

    <div class="row">
      <div class="grow">
        <label class="small">Filter results</label>
        <input id="resultFilter" placeholder="Type to filter by store name or city…" style="width:100%"/>
      </div>
      <div id="comparePanel" class="grow">
        <div class="compare-grid">
          <div class="compare-card" id="cmpA">Select any 2 stores to compare.</div>
          <div class="compare-card" id="cmpB"></div>
        </div>
      </div>
    </div>

    <div class="table-wrap" id="tableWrap" style="display:none">
      <table id="resultTable">
        <thead>
        <tr>
          <th style="width:38px"></th>
          <th>Store</th>
          <th>Distance</th>
          <th>Total</th>
          <th>Items Found</th>
          <th>Missing</th>
        </tr>
        </thead>
        <tbody id="resultBody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- Item Picker Modal -->
<div id="itemModal" class="modal">
  <div class="modal-content">
    <h2 style="margin:0 0 10px">Select items</h2>
    <input id="itemSearch" placeholder="Search items..." style="width:100%;padding:10px;border-radius:10px;border:1px solid var(--border);background:var(--card);color:var(--text);margin-bottom:10px;">
    <div id="itemList"></div>
    <div style="margin-top:12px;display:flex;gap:8px;justify-content:flex-end">
      <button id="cancelSelect">Cancel</button>
      <button id="confirmSelect" class="btn-accent">Use selected</button>
    </div>
  </div>
</div>

<!-- Searching overlay -->
<div id="overlay" class="overlay">
  <div class="spinner"><div></div><div>Searching nearby stores…</div></div>
</div>

<script>
  const apiBase = window.location.origin;

  // theme toggle
  const themeToggle = document.getElementById('themeToggle');
  function applyTheme(){ const t = localStorage.getItem('theme') || 'dark';
    document.body.classList.toggle('light', t === 'light');
    themeToggle.textContent = t === 'light' ? '🌞' : '🌙'; }
  function toggleTheme(){ const t = localStorage.getItem('theme') || 'dark';
    localStorage.setItem('theme', t === 'light' ? 'dark' : 'light'); applyTheme(); }
  themeToggle.onclick = toggleTheme; applyTheme();

  // map state
  let map=null, markerGroup=null, radiusCircle=null;
  let currentMarkersById=new Map();

  function ensureMap(lat, lon){
    if(!map){
      map = L.map('map').setView([lat, lon], 12);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19, attribution:'&copy; OpenStreetMap contributors'}).addTo(map);
      markerGroup = L.layerGroup().addTo(map);
    }else{
      map.setView([lat, lon], 12);
      markerGroup.clearLayers();
      currentMarkersById.clear();
    }
    L.marker([lat, lon], {title:'You'}).addTo(markerGroup).bindPopup('<b>Your location</b>').openPopup();
  }
  function drawRadius(lat, lon, miles){
    const meters = miles * 1609.34;
    if(radiusCircle){ radiusCircle.setLatLng([lat,lon]).setRadius(meters); }
    else{
      radiusCircle = L.circle([lat,lon],{radius:meters,color:'#22c55e',weight:1,fillColor:'#22c55e',fillOpacity:.08});
      radiusCircle.addTo(markerGroup);
    }
  }

  // inputs
  const $lat=document.getElementById('lat'), $lon=document.getElementById('lon');
  const $radius=document.getElementById('radius'), $lambda=document.getElementById('lambda');
  const $lambdaRange=document.getElementById('lambdaRange');
  const $overlay=document.getElementById('overlay');
  const $resultFilter=document.getElementById('resultFilter');
  const $tableWrap=document.getElementById('tableWrap');
  const $tbody=document.getElementById('resultBody');
  const $bestWrap=document.getElementById('bestWrap');

  function syncLambda(fromRange){
    if(fromRange) $lambda.value = $lambdaRange.value;
    else $lambdaRange.value = $lambda.value || 0.5;
    localStorage.setItem('lambda', $lambda.value);
  }
  $lambda.oninput = () => syncLambda(false);
  $lambdaRange.oninput = () => syncLambda(true);

  function loadPrefs(){
    $lat.value = localStorage.getItem('lat') || '';
    $lon.value = localStorage.getItem('lon') || '';
    $radius.value = localStorage.getItem('radius') || 10;
    $lambda.value = localStorage.getItem('lambda') || 0.5;
    syncLambda(false);
    const savedItems = JSON.parse(localStorage.getItem('selectedItems') || '[]');
    selectedSet = new Set(savedItems);
    showSelectedItems();
  }
  function savePrefs(lat, lon, radius){
    localStorage.setItem('lat', lat); localStorage.setItem('lon', lon);
    localStorage.setItem('radius', radius); localStorage.setItem('lambda', $lambda.value);
    localStorage.setItem('selectedItems', JSON.stringify([...selectedSet]));
  }

  // item picker
  const selectBtn=document.getElementById('selectItemsBtn');
  const modal=document.getElementById('itemModal');
  const itemListEl=document.getElementById('itemList');
  const selectedItemsEl=document.getElementById('selectedItems');
  const itemSearch=document.getElementById('itemSearch');
  const cancelBtn=document.getElementById('cancelSelect');
  const confirmBtn=document.getElementById('confirmSelect');

  let allItems=[]; let selectedSet=new Set();
  function showSelectedItems(){ selectedItemsEl.textContent = [...selectedSet].join(', ') || '(none)'; }

  async function loadItems(q=''){
    const url=new URL('/api/items', window.location.origin);
    if(q) url.searchParams.set('q', q);
    const res=await fetch(url); allItems=await res.json(); renderItemList();
  }
  function renderItemList(){
    itemListEl.innerHTML='';
    if(!allItems.length){ itemListEl.innerHTML='<div class="muted" style="padding:8px">No items found.</div>'; return; }
    allItems.forEach(name=>{
      const id=`chk_${name.replace(/\\s+/g,'_')}`;
      const row=document.createElement('div');
      row.innerHTML=\`<label><input type="checkbox" id="\${id}" value="\${name}" \${selectedSet.has(name)?'checked':''}> \${name}</label>\`;
      row.querySelector('input').addEventListener('change',e=>{
        if(e.target.checked) selectedSet.add(name); else selectedSet.delete(name);
      });
      itemListEl.appendChild(row);
    });
  }
  selectBtn.onclick = async ()=>{ modal.style.display='flex'; await loadItems(); itemSearch.value=''; itemSearch.focus(); };
  cancelBtn.onclick = ()=>{ modal.style.display='none'; };
  confirmBtn.onclick = ()=>{ modal.style.display='none'; showSelectedItems(); localStorage.setItem('selectedItems', JSON.stringify([...selectedSet])); };
  itemSearch.addEventListener('input',()=>{ const q=itemSearch.value.trim(); clearTimeout(window._itemSearchTimer); window._itemSearchTimer=setTimeout(()=>loadItems(q),250); });
  function selectedItemsCSV(){ return [...selectedSet].join(','); }

  // (call prefs AFTER picker vars exist)
  loadPrefs();

  // geolocation
  document.getElementById('geo').onclick = () => {
    if(!navigator.geolocation){
      alert('Geolocation not supported by this browser.');
      const lat=parseFloat($lat.value), lon=parseFloat($lon.value);
      if(!isNaN(lat)&&!isNaN(lon)) ensureMap(lat,lon);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      pos => {
        const lat=+pos.coords.latitude.toFixed(6), lon=+pos.coords.longitude.toFixed(6);
        $lat.value=lat; $lon.value=lon; ensureMap(lat,lon); drawRadius(lat,lon,+$radius.value||10);
      },
      err => { console.warn('Geolocation error:', err.message);
        alert(err.message+'\\nTip: open on http://127.0.0.1:5000 or allow location.'); },
      {enableHighAccuracy:true, timeout:8000}
    );
  };

  // search flow
  document.getElementById('searchBtn').onclick = doSearch;
  async function doSearch(){
    const latStr=$lat.value.trim(), lonStr=$lon.value.trim();
    if(!latStr||!lonStr) return alert("Please provide lat/lon (or click 'Use my location').");
    const lat=parseFloat(latStr), lon=parseFloat(lonStr);
    if(!map) ensureMap(lat,lon);

    const items=selectedItemsCSV();
    const radius=$radius.value.trim()||'10';
    const lambda=$lambda.value.trim()||'0.5';

    drawRadius(lat,lon,parseFloat(radius));
    savePrefs(lat,lon,radius);

    const url=new URL(apiBase+'/api/search');
    url.searchParams.set('lat', lat); url.searchParams.set('lon', lon);
    if(items) url.searchParams.set('items', items);
    url.searchParams.set('radius_miles', radius);
    url.searchParams.set('lambda_per_mile', lambda);

    setLoading(true);
    try{
      const res=await fetch(url);
      const data=await res.json();
      window._rowsCache = (data.stores_full||[]).concat(data.stores_partial||[]); // for compare wiring
      render(data);
    }catch(e){ console.error(e); alert('Search failed. Check console for details.'); }
    finally{ setLoading(false); }
  }
  function setLoading(b){ document.getElementById('searchBtn').disabled=b; document.getElementById('geo').disabled=b; $overlay.style.display=b?'flex':'none'; }

  // render results + map markers
  function render(data){
    if(data.error){ $bestWrap.style.display='block'; $bestWrap.innerHTML=\`<div class="card">Error: \${data.error}</div>\`; $tableWrap.style.display='none'; return; }

    const rows=(data.stores_full||[]).concat(data.stores_partial||[]);
    renderBest(data.best); renderTable(rows, data.best ? data.best.store_id : null);

    if(map && markerGroup){
      markerGroup.clearLayers(); currentMarkersById.clear();
      const lat=parseFloat($lat.value), lon=parseFloat($lon.value);
      L.marker([lat,lon],{title:'You'}).addTo(markerGroup).bindPopup('<b>Your location</b>');
      drawRadius(lat,lon,+$radius.value||10);

      if(rows.length){
        const bounds=L.latLngBounds();
        rows.forEach(s=>{
          const m=L.marker([s.lat,s.lon],{title:s.store_name}).addTo(markerGroup);
          m.bindPopup(\`<b>\${s.store_name}</b><br>\${s.distance_miles.toFixed(2)} mi<br>$\${(s.total_price||0).toFixed(2)}\`);
          if(data.best && s.store_id===data.best.store_id) m.setZIndexOffset(1000);
          currentMarkersById.set(s.store_id, m); bounds.extend(m.getLatLng());
          m.on('mouseover',()=>highlightRow(s.store_id,true));
          m.on('mouseout',()=>highlightRow(s.store_id,false));
          m.on('click',()=>scrollToRow(s.store_id));
        });
        markerGroup.eachLayer(l=>bounds.extend(l.getLatLng()));
        map.fitBounds(bounds,{padding:[50,50]});
      }
    }
  }
  function renderBest(best){
    if(!best){ $bestWrap.style.display='none'; return; }
    $bestWrap.style.display='block';
    $bestWrap.innerHTML = \`
      <div class="result-header">
        <h3 style="margin:0">\${best.store_name}</h3>
        <span class="chip pill"><b>\${best.distance_miles.toFixed(2)} mi</b> away</span>
        <span class="chip pill"><b>$\${(best.total_price||0).toFixed(2)}</b> total</span>
        <span class="chip pill"><b>\${best.score.toFixed(2)}</b> score</span>
      </div>
      \${Array.isArray(best.items_missing) && best.items_missing.length ? \`<div class="muted" style="margin-top:6px">Missing: \${best.items_missing.join(', ')}</div>\` : ''}\`;
  }
  function renderTable(rows, bestId){
    const $tbody=document.getElementById('resultBody');
    $tbody.innerHTML=''; rows.forEach(s=>{
      const tr=document.createElement('tr'); tr.dataset.sid=s.store_id;
      tr.innerHTML=\`
        <td><input type="checkbox" class="cmp" data-sid="\${s.store_id}"></td>
        <td>\${s.store_name}\${s.city? \` <span class="muted">· \${s.city}</span>\`:''}</td>
        <td>\${s.distance_miles.toFixed(2)} mi</td>
        <td>$\${(s.total_price||0).toFixed(2)}</td>
        <td><span class="chip">\${s.items_found}</span></td>
        <td>\${(s.items_missing||[]).join(', ')}</td>\`;
      if(s.store_id===bestId) tr.classList.add('highlight');
      tr.addEventListener('mouseenter',()=>{ const m=currentMarkersById.get(s.store_id); if(m){ m.openPopup(); } highlightRow(s.store_id,true); });
      tr.addEventListener('mouseleave',()=>highlightRow(s.store_id,false));
      $tbody.appendChild(tr);
    });
    document.getElementById('tableWrap').style.display = rows.length ? 'block' : 'none';
  }
  function highlightRow(sid,on){ const row=document.querySelector(\`tr[data-sid="\${sid}"]\`); if(row) row.classList.toggle('highlight', on); }
  function scrollToRow(sid){ const row=document.querySelector(\`tr[data-sid="\${sid}"]\`); if(!row) return; row.scrollIntoView({behavior:'smooth',block:'center'}); row.classList.add('highlight'); setTimeout(()=>row.classList.remove('highlight'),1200); }

  // instant filter
  document.getElementById('resultFilter').addEventListener('input', ()=>{ const q=document.getElementById('resultFilter').value.trim().toLowerCase();
    for(const tr of document.querySelectorAll('#resultBody tr')){ tr.style.display = tr.innerText.toLowerCase().includes(q) ? '' : 'none'; } });

  // initialize map if coords already saved
  (function initFromPrefs(){
    const lat=parseFloat(localStorage.getItem('lat')||'');
    const lon=parseFloat(localStorage.getItem('lon')||'');
    if(!isNaN(lat)&&!isNaN(lon)){ ensureMap(lat,lon); drawRadius(lat,lon,+(localStorage.getItem('radius')||10)); }
  })();
</script>
</body>
</html>"""

app = Flask(__name__)
CORS(app)

@app.get("/")
def root():
    # Serve ./index.html if present, else the built-in page so this file is standalone
    if Path("index.html").exists():
        return send_from_directory(".", "index.html")
    return Response(INDEX_FALLBACK, mimetype="text/html")

# --------- Improved Items endpoint: only items that exist in at least one store
@app.get("/api/items")
def api_items():
    """
    Return distinct product names that appear in at least one store (store_product join).
    Optional query params:
      - ?q=<substring> (LIKE; case-insensitive under default collations)
      - ?limit=<N> (default 50, max 200)
    """
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

    rows = query(sql, tuple(params))
    return jsonify([r["item_name"] for r in rows])

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

    items_raw = request.args.get("items", "")
    items_tokens = [i.strip().lower() for i in items_raw.split(",") if i.strip()]

    radius_miles = float(request.args.get("radius_miles", "10"))
    lambda_per_mile = float(request.args.get("lambda_per_mile", "0.5"))
    radius_m = radius_miles * 1609.34

    base_sql = """
        SELECT
            s.id,
            s.name,
            -- s.address,         -- <- OPTIONAL: uncomment if your schema has it
            -- s.city,            -- <- OPTIONAL: uncomment if your schema has it
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

    rows = query(base_sql, params)

    # Aggregate cheapest price per token per store
    stores = {}
    for r in rows:
        sid = r["id"]
        s = stores.setdefault(sid, {
            "store_id": sid,
            "store_name": r["name"],
            # "address": r.get("address"),   # if enabled above
            # "city": r.get("city"),         # if enabled above
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

    if items_tokens:
        full = [s for s in results if not s["items_missing"]]
        partial = [s for s in results if s["items_missing"]]
    else:
        full, partial = results, []

    full.sort(key=lambda s: (s["total_price"], s["distance_miles"]))
    partial.sort(key=lambda s: (len(s["items_missing"]), s["total_price"] or 1e9, s["distance_miles"]))

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

    _print_db_target()

    if cmd == "web":
        _db_smoke()
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
