🧩 Contributing Guide

Project: Closest & Cheapest Store Finder
Team: SDD_003

We welcome contributions from all team members to maintain and improve this project.
Please follow the standards below to keep the codebase consistent, testable, and easy to review.

🧱 Branching Strategy

Create a new branch for each change:

feature/<short-description>   → for new features  
fix/<short-description>       → for bug fixes  
refactor/<short-description>  → for cleanup / optimization  
docs/<short-description>      → for documentation-only updates


Example:

feature/add-leaflet-map
fix/db-connection-timeout

💬 Commit Messages

Use clear, descriptive messages written in the present tense.
Examples:

Add Flask route for /api/check-items
Fix distance calculation using ST_Distance_Sphere
Refactor map rendering logic for index.html
Update README with database setup instructions


Keep messages under ~72 characters for readability.

Group related changes in one commit; avoid mixing unrelated fixes.

🧠 Code Style (Python)

We follow PEP 8 guidelines with minor project-specific conventions:

General

Use 4 spaces for indentation (no tabs).

Keep lines ≤ 100 characters when possible.

Use descriptive variable names (e.g. user_location, store_results).

Prefer f-strings for formatting over string concatenation.

Add docstrings to all major functions and classes.

Example
def find_shortest_route(start, items):
    """
    Compute the shortest route connecting all items using the haversine formula.
    Returns a list of route segments and total distance.
    """
    route = []
    current = start
    total_distance = 0.0
    for loc in items:
        dist = haversine(current[0], current[1], loc[0], loc[1])
        route.append({"to": loc, "distance": dist})
        total_distance += dist
        current = loc
    return route, total_distance

🧩 Code Style (Frontend)

Use semantic HTML5 (<header>, <section>, <button>).

Keep CSS modular — prefer class-based styling.

JavaScript should use ES6+ features and avoid global variables.

Fetch calls must handle errors gracefully (try/catch + alerts or console logs).

⚙️ Environment & Dependencies

Use the project’s virtual environment:

python -m venv .venv
source .venv/bin/activate        # or .venv\Scripts\activate on Windows
pip install -r requirements.txt


Do not commit your .venv folder. It’s ignored via .gitignore.

Add any new dependencies to requirements.txt after testing:

pip freeze > requirements.txt

🧪 Testing Guidelines

Before submitting a pull request:

Run your feature locally:

python app.py


Confirm that:

/api/search returns valid JSON.

The map, geolocation, and results table load without errors.

The database tunnel connects successfully.

If you modify the database schema, update:

schema.mariadb.sql

seed.mariadb.sql

The .env.example file (if new variables are required).

📤 Pull Requests

Open a PR once your code is ready for review.

Link related issues in your PR description (if applicable).

Include:

Summary of changes

Testing steps

Screenshots (for UI updates)

At least one teammate approval required before merging.

All tests and the application must run without errors.

🧭 Code Review Checklist

Before approving a PR, check that:

 The code runs locally without errors.

 There are no syntax or logic issues.

 Changes are well-commented and meaningful.

 Database queries are safe and parameterized (no raw SQL injection).

 UI/UX is responsive and readable.

🧹 Housekeeping

Keep the README.md and Makefile up to date when adding new features.

Remove unused files and commented-out code before pushing.

Use consistent naming across backend and frontend for shared fields
(e.g., store_id, lat, lon).

👥 Example Workflow
# 1. Create new branch
git checkout -b feature/add-api-endpoint

# 2. Develop and test locally
python app.py

# 3. Commit and push
git add .
git commit -m "Add new /api/store-details endpoint"
git push origin feature/add-api-endpoint

# 4. Open Pull Request on GitHub
