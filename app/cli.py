# app/cli.py
import os
import argparse
from dotenv import load_dotenv

from .tunnel import maybe_start_tunnel
from . import create_app
from .db import query, db_smoke_ok
from .logic import check_items_in_price_history, demo_store_scoring, simulate_route

def _print_db_target():
    print(f"DB target → host={os.getenv('DB_HOST')} port={os.getenv('DB_PORT')} "
          f"user={os.getenv('DB_USER')} db={os.getenv('DB_NAME')}")

def main():
    # Ensure env and (optional) tunnel are ready for *all* commands.
    load_dotenv()
    maybe_start_tunnel()

    parser = argparse.ArgumentParser(description="Closest & Cheapest — multi-mode app")
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
        ok = db_smoke_ok()
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
