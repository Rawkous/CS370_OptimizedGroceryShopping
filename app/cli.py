# app/cli.py
import os
import argparse
from dotenv import load_dotenv

from .tunnel import maybe_start_tunnel
from . import create_app
from .db import db_smoke_ok
from .logic import check_items_in_price_history, demo_store_scoring, simulate_route
from .kroger import (  # NEW
    _get_token as kroger_get_token,
    _get_locations as kroger_locations,
    _get_products as kroger_products,
    search_kroger as kroger_search,
)

def _print_db_target():
    print(
        f"DB target → host={os.getenv('DB_HOST')} "
        f"port={os.getenv('DB_PORT')} user={os.getenv('DB_USER')} db={os.getenv('DB_NAME')}"
    )

def main():
    load_dotenv()
    maybe_start_tunnel()

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

    # ---- Kroger smoke tests ----
    sub.add_parser("kroger-token", help="Fetch OAuth token (client_credentials)")
    p_k_loc = sub.add_parser("kroger-locations", help="List Kroger locations near lat/lon")
    p_k_loc.add_argument("--lat", type=float, required=True)
    p_k_loc.add_argument("--lon", type=float, required=True)
    p_k_loc.add_argument("--radius", type=int, default=10)

    p_k_prod = sub.add_parser("kroger-products", help="Search Kroger products at a location")
    p_k_prod.add_argument("--loc", required=True, help="locationId")
    p_k_prod.add_argument("--term", required=True)
    p_k_prod.add_argument("--limit", type=int, default=10)

    p_k_check = sub.add_parser("kroger-check", help="End-to-end Kroger ranking")
    p_k_check.add_argument("--lat", type=float, required=True)
    p_k_check.add_argument("--lon", type=float, required=True)
    p_k_check.add_argument("--radius", type=int, default=10)
    p_k_check.add_argument("--items", required=True, help="Comma list, e.g. 'milk,eggs,bread'")
    p_k_check.add_argument("--lambda_per_mile", type=float, default=0.5)

    args = parser.parse_args()
    cmd = args.cmd or "web"

    _print_db_target()

    if cmd == "web":
        print("✅ DB OK" if db_smoke_ok() else "❌ DB FAILED: see logs above")
        app = create_app()
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
        out = simulate_route(args.lat, args.lon, args.n, args.gas)
        print("Route:", out["route"])
        print(f"Total distance: {out['total_distance_miles']:.2f} mi   Gas used: {out['gas_used']:.2f} gal")

    elif cmd == "db-check":
        print("✅ DB OK" if db_smoke_ok() else "❌ DB FAILED")

    # ---- Kroger CLI handlers ----
    elif cmd == "kroger-token":
        try:
            tok = kroger_get_token()
            print("✅ token acquired (len):", len(tok))
        except Exception as e:
            print("❌", e)

    elif cmd == "kroger-locations":
        try:
            locs = kroger_locations(args.lat, args.lon, args.radius)
            for l in locs[:10]:
                lid = l.get("locationId")
                name = l.get("name") or (l.get("address") or {}).get("addressLine1")
                city = (l.get("address") or {}).get("city")
                print(f"{lid} - {name} @ {city}")
            print(f"Total: {len(locs)}")
        except Exception as e:
            print("❌", e)

    elif cmd == "kroger-products":
        try:
            prods = kroger_products(args.term, args.loc, args.limit)
            for p in prods:
                brand = (p.get("brand") or "").strip()
                desc  = (p.get("description") or "").strip()
                items = p.get("items") or []
                price = None
                if items:
                    pr = items[0].get("price") or {}
                    price = pr.get("promo") or pr.get("regular")
                print(f"- {brand} | {desc[:80]} | ${price}")
            print(f"Total: {len(prods)}")
        except Exception as e:
            print("❌", e)

    elif cmd == "kroger-check":
        try:
            items = [t.strip() for t in args.items.split(",") if t.strip()]
            out = kroger_search(args.lat, args.lon, items, int(args.radius), float(args.lambda_per_mile))
            best = out["best"]
            print("=== Best ===")
            if best:
                print(best["store_name"], f"({best['distance_miles']:.2f} mi)", "score:", best["score"], "total:", best["total_price"])
                print("Items:", best["items"])
                print("Missing:", best["items_missing"])
            else:
                print("No matching stores.")
            print("stores_full:", len(out["stores_full"]), "stores_partial:", len(out["stores_partial"]))
        except Exception as e:
            print("❌", e)
