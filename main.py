# ============================================================
#  Imports
# ============================================================
from sshtunnel import SSHTunnelForwarder
import mysql.connector
import random
import math


# ============================================================
#  Database + SSH Connection Setup
# ============================================================

def connect_database():
    """
    Opens an SSH tunnel to the remote server and connects to MySQL.
    Returns (connection, cursor) pair.
    """
    tunnel = SSHTunnelForwarder(
        ('blue.cs.sonoma.edu', 22),
        ssh_username='lhinson',
        ssh_password='Kappa123',
        remote_bind_address=('127.0.0.1', 3306)
    )
    tunnel.start()

    mydb = mysql.connector.connect(
        host='127.0.0.1',
        port=tunnel.local_bind_port,
        user='SDD_003_user',
        password='SDD_003_29',
        database='SDD_003_database'
    )
    cursor = mydb.cursor()
    print("✅ Connected to MySQL through SSH tunnel!")
    return mydb, cursor, tunnel


# ============================================================
#  Database Query: Check for Item Existence
# ============================================================

def check_items_in_price_history(cursor):
    """
    Automatically detects the likely name column and checks
    which items exist or are missing in price_history.
    """
    # Detect columns
    cursor.execute("SHOW COLUMNS FROM price_history;")
    columns = [col[0] for col in cursor.fetchall()]
    print("🔍 Columns in price_history:", columns)

    # Find the likely item name column
    name_column = None
    for c in columns:
        if "name" in c.lower() or "item" in c.lower() or "product" in c.lower():
            name_column = c
            break

    if not name_column:
        print("❌ Could not find an item-name-like column in price_history.")
        return [], []

    print(f"✅ Using column '{name_column}' for item matching.\n")

    # Items to check
    items = ['banana', 'egg', 'bread']

    # Build query dynamically
    placeholders = ','.join(['%s'] * len(items))
    query = f"SELECT {name_column} FROM price_history WHERE {name_column} IN ({placeholders})"
    cursor.execute(query, tuple(items))

    found = [row[0] for row in cursor.fetchall()]
    missing = [i for i in items if i not in found]

    print("✅ Found in price_history:", found)
    print("❌ Missing from price_history:", missing)
    return found, missing


# ============================================================
#  Store Scoring and Matching Logic
# ============================================================

def GetDistance():
    return [10]


def get_store_data():
    stores = [
        {
            "name": "Supermarket",
            "inventory": ['banana', 'egg', 'bread', 'soda', 'cookies', 'sugar'],
            "distance": 5
        },
        {
            "name": "MiniMart",
            "inventory": ['banana', 'milk', 'bread', 'chips'],
            "distance": 3
        },
        {
            "name": "OrganicShop",
            "inventory": ['bread', 'sugar', 'apple', 'lettuce'],
            "distance": 8
        },
        {
            "name": "CornerStore",
            "inventory": ['banana', 'egg'],
            "distance": 2
        }
    ]

    userItems = ['banana', 'egg', 'bread', 'sugar']

    best_store = None
    best_score = -1
    results = []

    for store in stores:
        inventory = store["inventory"]
        distance = store["distance"]
        matches = set(inventory) & set(userItems)
        match_count = len(matches)

        score = float('inf') if distance == 0 else match_count / distance

        store_result = {
            "Store": store["name"],
            "Distance": distance,
            "MatchedItems": list(matches),
            "MatchCount": match_count,
            "Score": round(score, 3)
        }
        results.append(store_result)

        if score > best_score:
            best_score = score
            best_store = store_result

    print("\n=== Store Comparison Results ===\n")
    for r in results:
        print(f"Store: {r['Store']}")
        print(f"  Distance: {r['Distance']} miles")
        print(f"  MatchCount: {r['MatchCount']}")
        print(f"  MatchedItems: {r['MatchedItems']}")
        print(f"  Score (Match/Distance): {r['Score']}\n")

    print("=== Best Fit Store ===")
    if best_store:
        print(f"Store: {best_store['Store']}")
        print(f"Distance: {best_store['Distance']} miles")
        print(f"MatchedItems: {best_store['MatchedItems']}")
        print(f"MatchCount: {best_store['MatchCount']}")
        print(f"Score: {best_store['Score']}\n")
    else:
        print("No suitable store found.")


# ============================================================
#  User Route & Gas Simulation
# ============================================================

def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates in miles."""
    R = 3958.8  # miles
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * \
        math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


class User:
    def __init__(self, ID, latitude, longitude):
        self.id = ID
        self.latitude = latitude
        self.longitude = longitude
        self.items = []

    def getID(self):
        return self.id

    def getLatitude(self):
        return self.latitude

    def getLongitude(self):
        return self.longitude

    def getItems(self):
        return self.items

    def genItems(self, num_items=5):
        for _ in range(num_items):
            lat = random.uniform(-90, 90)
            lon = random.uniform(-180, 180)
            self.items.append((lat, lon))


def genUsers(numUsers=1):
    users = []
    for _ in range(numUsers):
        ID = random.randint(100000, 999999)
        lat = random.uniform(-90, 90)
        lon = random.uniform(-180, 180)
        user = User(ID, lat, lon)
        user.genItems()
        users.append(user)
    return users


def find_shortest_route(start, items):
    route = []
    current = start
    total_distance = 0.0
    remaining = items.copy()

    while remaining:
        next_item = min(remaining, key=lambda loc: haversine(
            current[0], current[1], loc[0], loc[1]))
        dist = haversine(current[0], current[1], next_item[0], next_item[1])
        total_distance += dist
        route.append((next_item, dist))
        current = next_item
        remaining.remove(next_item)

    return route, total_distance


def find_total_gas_used(total_distance, gas_per_mile):
    return total_distance * gas_per_mile


# ============================================================
#  Main Program Flow
# ============================================================

if __name__ == "__main__":
    # --- Connect to database and check items ---
    try:
        mydb, cursor, tunnel = connect_database()
        check_items_in_price_history(cursor)
        cursor.close()
        mydb.close()
        tunnel.stop()
    except Exception as e:
        print(f"⚠️ Database connection or query failed: {e}")

    # --- Run store scoring logic ---
    get_store_data()

    # --- Run user + route simulation ---
    gas_rate = 0.05  # gallons per mile
    users = genUsers()

    for user in users:
        print(f"User ID: {user.getID()}")
        print(f"Start Location: {user.getLatitude():.6f}, {user.getLongitude():.6f}")
        print("Item Locations:")
        for item in user.getItems():
            print(f"{item[0]:.6f}, {item[1]:.6f}")

        start_location = (user.getLatitude(), user.getLongitude())
        route, total_distance = find_shortest_route(start_location, user.getItems())
        gas_used = find_total_gas_used(total_distance, gas_rate)

        print("\nRoute Taken (lat, lon, distance in miles):")
        for loc, dist in route:
            print(f"{loc[0]:.6f}, {loc[1]:.6f}, {dist:.2f}")

        print(f"Total Distance Traveled: {total_distance:.2f} miles")
        print(f"Total Gas Used: {gas_used:.2f} gallons\n")