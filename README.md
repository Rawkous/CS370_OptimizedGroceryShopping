Overview

// QUICK START AT THE BOTTOM //

Project Title: Closest & Cheapest Store Finder
Team: SDD_003
Primary Modules:

Backend (Python + Flask): RESTful API and data-processing engine

Database Layer: MariaDB (hosted via SSH on Blue.cs.sonoma.edu)

Frontend (HTML + JavaScript): Interactive UI with live map visualization (Leaflet.js)

The goal of this system is to help users identify the nearest and most cost-efficient grocery store based on their location and a list of desired products. It dynamically queries a live MariaDB database using spatial functions, ranks stores by distance and total cost, and visualizes results on an interactive map.

System Architecture

1. Database Layer (MariaDB):

Stores data for users, stores, products, and pricing history

Implements spatial indexing using POINT geometry and SRID=4326

Supports geospatial queries via ST_Distance_Sphere() to calculate accurate store-to-user distances in meters

Foreign key relationships maintain referential integrity between store, product, and store_product tables

2. Backend Layer (Flask + Python):

Establishes a secure SSH tunnel from the local app to the remote Blue server
using sshtunnel.SSHTunnelForwarder

Creates a MySQL connection pool (mysql.connector.pooling) for concurrent query handling

Exposes REST endpoints:

GET /api/search — main query endpoint combining price and location data

GET /api/check-items — verifies product names in price_history

GET /api/demo-scoring — runs mock scoring tests

GET /api/sim-route — simulates travel routes and fuel usage

3. Frontend Layer (HTML + Leaflet.js + JS Fetch API):

User interface for location input, radius, and item list

“Use my location” feature via the Geolocation API

Live Leaflet.js map renders:

User marker (blue)

Store markers (red, green for best match)

Dynamic map bounds adjusting to visible results

Search results table shows:

Store name

Distance (in miles)

Total price for listed items

Items found and missing per store

Algorithm Flow
User Inputs (lat, lon, items)
        ↓
Flask API: /api/search
        ↓
SQL Query:
  SELECT stores within radius
  JOIN store_product & product tables
  COMPUTE ST_Distance_Sphere(location, user_point)
        ↓
Python Aggregation:
  - Group results by store
  - Compute total item price
  - Score = total_price + λ * distance
        ↓
Rank & Sort Stores
        ↓
Return JSON response → Frontend
        ↓
Leaflet Map + Results Table Render

Tools & Technologies
Component	Technology
Backend Framework	Flask (Python 3.10)
Database	MariaDB (Remote, SRID-enabled)
SSH Connection	Paramiko / sshtunnel
Frontend	HTML5, CSS3, Vanilla JS
Map Visualization	Leaflet.js (OpenStreetMap tiles)
Environment Management	Python Virtual Env (venv), Makefile
Version Control	Git + GitHub
Deployment Mode	Local Flask server (development), remote DB
Testing & Validation

Unit Tests: Verified DB connection, query accuracy, and spatial calculations.

Integration Tests:

Ensured api/search returns valid stores within radius.

Validated scoring formula (price + distance weight).

UI Tests:

Map and table correctly synchronize with backend data.

Geolocation successfully centers on user’s location (127.0.0.1 environment).

Example Test Query:

GET /api/search?lat=38.341211&lon=-122.676018&items=bread,milk&radius_miles=100&lambda_per_mile=1


Response includes:

25–30 store matches within 100 miles

Correct distance ranking

Map markers dynamically rendered in Leaflet

Deployment Notes

Run locally using:

Application currently starts on: http://127.0.0.1:5000

Database tunnel: blue.cs.sonoma.edu → localhost:3307

.env file contains secure DB and SSH credentials (excluded from repo)

Works cross-platform (Windows, macOS, Linux) with minimal configuration

Future Enhancements

Integrate live API data from grocery chains (e.g., Kroger or Walmart APIs)

Add user login and saved lists from the user_account schema

Implement price trend analytics via the price_history table

Add route optimization visualization using Mapbox Directions API



## Quickstart

git clone https://github.com/Rawkous/CS370_OptimizedGroceryShopping.git
cd CS370_OptimizedGroceryShopping

# Create a venv + install deps (works everywhere)
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

