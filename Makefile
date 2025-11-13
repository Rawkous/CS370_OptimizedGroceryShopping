SHELL := /bin/bash
VENV := .venv
ACT := source $(VENV)/bin/activate

PY := python3
PIP := $(VENV)/bin/pip

default: help

help:
	@echo "Targets:"
	@echo "  make setup         # venv + deps"
	@echo "  make run           # run app (uses .env; tunnel if USE_SSH_TUNNEL=1)"
	@echo "  make db-check      # simple SELECT 1 via app code"
	@echo "  make db-local-up   # start MariaDB container"
	@echo "  make db-local-load # load schema + seed into local MariaDB"
	@echo "  make db-local-down # stop container"
	@echo "  make clean         # remove venv/__pycache__"

setup: $(VENV)/bin/activate

$(VENV)/bin/activate:
	$(PY) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt

run:
	@$(ACT) && $(PY) app.py web

db-check:
	@$(ACT) && $(PY) app.py db-check

db-local-up:
	docker compose up -d db
	@echo "⏳ Waiting for DB to be healthy..."
	@for i in {1..30}; do \
	  docker inspect --format='{{json .State.Health.Status}}' grocery_db | grep -q healthy && break || sleep 2; \
	done && echo "✅ DB healthy."

db-local-load:
	@./scripts/seed_local_db.sh

db-local-down:
	docker compose down

clean:
	rm -rf __pycache__ */__pycache__ $(VENV)
