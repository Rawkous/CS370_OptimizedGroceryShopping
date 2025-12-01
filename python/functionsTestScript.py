"""
Standalone analysis + functionality test script.
Runs:
- Database item existence check
- Store scoring simulation
- User route + gas simulation
This script reuses logic.py and db.py from the Flask app,
but runs completely standalone.
Run with:
    python functionsTestScript.py
"""

import sys
import random
from pathlib import Path

from dotenv import load_dotenv  

# Load environment
load_dotenv()  

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app import logic
from app import db



# 1. DATABASE CHECK 
def run_db_check():
    print("\n==============================")
    print("Checking DB Price History")
    print("==============================")

    if not db.db_smoke_ok():
        print("DB check FAILED")
        return
        
    items = ["banana", "bread", "egg"]
    result = logic.check_items_in_price_history(items)

    print(f"Found:   {result['found']}")
    print(f"Missing: {result['missing']}")



# 2. STORE SCORING
def run_store_scoring():
    print("\n==============================")
    print("Store Scoring Simulation")
    print("==============================")

    best, all_rows = logic.demo_store_scoring()

    print("\nAll store comparisons:")
    for row in all_rows:
        print(row)

    print("\nBest store match:")
    print(best)


# 3. USER SIM
def run_user_simulation():
    print("\n==============================")
    print("User Route & Gas Simulation")
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



if __name__ == "__main__":
    print("\n===================================")
    print("Functionality Test Script Start")
    print("===================================\n")

    try:
        run_db_check()
    except Exception as e:
        print(f"Error during DB check: {e}")

    run_store_scoring()
    run_user_simulation()

    print("\n===================================")
    print("✅ ALL Complete")
    print("===================================\n")

