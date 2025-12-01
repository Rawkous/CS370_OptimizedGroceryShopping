"""
Standalone analysis + functionality test script.

Runs:
- Database item existence check
- Store scoring simulation
- User route + gas simulation

This script reuses logic.py and db.py from the Flask app,
but runs completely standalone (no Flask server required).

Run with:
    python functionsTestScript.py
"""

import sys
import random
from pathlib import Path

from dotenv import load_dotenv  # 👈 NEW

# Load environment variables from .env file
load_dotenv()  # 👈 NEW

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

# Import your existing logic + DB modules
from app import logic
from app import db


# ============================================================
# 1. DATABASE CHECK USING db.py (SSH tunnel + MySQL pool)
# ============================================================
def run_db_check():
    print("\n==============================")
    print("🔍 Checking DB Price History")
    print("==============================")

    if not db.db_smoke_ok():
        print("⚠️ DB check FAILED — SSH tunnel or DB credentials may be wrong.")
        return

    # Example query: check these items in price_history
    items = ["banana", "bread", "egg"]
    result = logic.check_items_in_price_history(items)

    print(f"Found:   {result['found']}")
    print(f"Missing: {result['missing']}")


# ============================================================
# 2. STORE SCORING
# ============================================================
def run_store_scoring():
    print("\n==============================")
    print("🏪 Store Scoring Simulation")
    print("==============================")

    best, all_rows = logic.demo_store_scoring()

    print("\nAll store comparisons:")
    for row in all_rows:
        print(row)

    print("\n🔥 Best store match:")
    print(best)


# ============================================================
# 3. USER SIMULATION + ROUTE + GAS
# ============================================================
def run_user_simulation():
    print("\n==============================")
    print("🚗 User Route & Gas Simulation")
    print("==============================")

    user_lat = random.uniform(-90, 90)
    user_lon = random.uniform(-180, 180)

    print(f"User start location: ({user_lat:.3f}, {user_lon:.3f})")

    result = logic.simulate_route(user_lat, user_lon, n=5)

    print("\nGenerated item coordinates:")
    for item in result["items"]:
        print(f" - {item}")

    print("\nRoute steps:")
    for step in result["route"]:
        loc = step["to"]
        dist = step["distance"]
        print(f" → {loc} ({dist:.2f} miles)")

    print("\nTotals:")
    print(f"Total distance: {result['total_distance_miles']} miles")
    print(f"Gas used: {result['gas_used']} gallons")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("\n===================================")
    print("🧪 Functionality Test Script Start")
    print("===================================\n")

    try:
        run_db_check()
    except Exception as e:
        print(f"⚠️ Error during DB check: {e}")

    run_store_scoring()
    run_user_simulation()

    print("\n===================================")
    print("✅ All Function Tests Complete")
    print("===================================\n")
