.ENV FILE CHANGES // Replace with own credentials

SSH_HOST=blue.cs.sonoma.edu
SSH_PORT=22
SSH_USER=USER
SSH_PASSWORD=PASSWORD
___________________________________________________________________________________________

Main Functionalities

make install     # Set up environment and install dependencies
make test        # Run test suite
make run         # Start the application
python python/functionsTestScript.py    # Run standalone functionality tests







____________________________________________________________________________________________

GrocoLoco – Setup and Usage (Windows Friendly Guide)

This project is a Python/Flask application for optimized grocery route planning, store scoring, and database item checking.
The instructions below explain how to set up and run the project on Windows using only Python.

1. Requirements

Before starting, make sure you have:

Python 3.10 or newer

pip (comes with Python)

Optionally: MySQL if you want database features

Everything else is included in this project.

2. Project Structure
CS370_OptimizedGroceryShopping/
  python/
    app.py
    functionsTestScript.py
    app/
      logic.py
      db.py
      routes.py
      ...
  html/
  photos/
  db/
  tests/
  requirements.txt
  README.md
  .env

3. Create a .env File

In the project root, create a file named .env.

For simple local use without a database:

USE_SSH_TUNNEL=0


If you have a database you want to connect to:

USE_SSH_TUNNEL=0
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=your_database


If you need SSH tunneling:

USE_SSH_TUNNEL=1
SSH_HOST=blue.cs.sonoma.edu
SSH_PORT=22
SSH_USER=your_username
SSH_PASSWORD=your_password

REMOTE_DB_HOST=127.0.0.1
REMOTE_DB_PORT=3306


Do not commit .env to Git.

4. Install Python Dependencies (No Make Required)

Open PowerShell or Command Prompt inside the project folder:

cd path/to/CS370_OptimizedGroceryShopping


Create and activate a virtual environment:

python -m venv .venv
.venv\Scripts\activate


Install dependencies:

pip install -r requirements.txt

5. Run the Flask Application

With the virtual environment activated, run:

python python/app.py


After it starts, open your browser and go to:

http://localhost:5000


This loads the full GrocoLoco web application.

6. Run the Standalone Function Tester

This script tests:

route simulation

store scoring

database checks (if configured)

Run it with:

python python/functionsTestScript.py

7. Run Automated Tests (Pytest)

To run the internal test suite:

.venv\Scripts\activate
pytest


Tests are located in the tests/ folder.

8. Summary of Commands (Windows)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python python/app.py         # Start web app
python python/functionsTestScript.py    # Run standalone tests
pytest                       # Run automated test suite




