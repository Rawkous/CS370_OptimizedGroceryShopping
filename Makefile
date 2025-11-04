# Detect Windows vs *nix paths
ifeq ($(OS),Windows_NT)
PY   = .\.venv\Scripts\python.exe
PIP  = .\.venv\Scripts\pip.exe
SET  = set
AND  = &&
SHELL := cmd
else
PY   = ./.venv/bin/python
PIP  = ./.venv/bin/pip
SET  = env
AND  = ;
SHELL := /bin/bash
endif

.PHONY: venv install run run-tunnel run-direct db-check check-items demo-scoring sim-route freeze clean-pyc help

venv:
	python -m venv .venv

install: venv
	$(PY) -m pip install --upgrade pip
	$(PIP) install -r requirements.txt

# === your original target (uses whatever .env says) ===
run:
	$(PY) app.py

# Force tunnel ON for this run (ignores .env USE_SSH_TUNNEL)
run-tunnel:
ifeq ($(OS),Windows_NT)
	$(SET) USE_SSH_TUNNEL=1 $(AND) $(PY) app.py
else
	USE_SSH_TUNNEL=1 $(PY) app.py
endif

# Force direct to Blue (no tunnel) for this run
run-direct:
ifeq ($(OS),Windows_NT)
	$(SET) USE_SSH_TUNNEL=0 $(AND) $(PY) app.py
else
	USE_SSH_TUNNEL=0 $(PY) app.py
endif

# Quick smoke test to the DB
db-check:
	$(PY) app.py db-check

# Use your API-less console flows
check-items:
	$(PY) app.py check-items --items "banana,egg,bread"

demo-scoring:
	$(PY) app.py demo-scoring

sim-route:
	$(PY) app.py sim-route --lat 33.7490 --lon -84.3880 --n 5 --gas 0.05

freeze:
	$(PIP) freeze > requirements.txt

# Clean Python caches (works on *nix; Windows cmd falls back)
clean-pyc:
	- find . -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
	- rmdir /S /Q __pycache__ 2> NUL || exit 0

help: ## show targets
	@echo Available targets:
	@echo "  make install        - create venv and install requirements"
	@echo "  make run            - run web app using current .env"
	@echo "  make run-tunnel     - run web app forcing USE_SSH_TUNNEL=1"
	@echo "  make run-direct     - run web app forcing USE_SSH_TUNNEL=0"
	@echo "  make db-check       - DB health probe"
	@echo "  make check-items    - console: check banana, egg, bread"
	@echo "  make demo-scoring   - console: demo store scoring"
	@echo "  make sim-route      - console: route+gas simulation"
	@echo "  make freeze         - write requirements.txt from current venv"
	@echo "  make clean-pyc      - remove __pycache__"
