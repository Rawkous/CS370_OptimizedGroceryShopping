# ---- Closest & Cheapest — Makefile -----------------------------------------
# Usage:
#   make run           # run web server (uses .env; SSH tunnel if enabled)
#   make run-no-tunnel # run web server with USE_SSH_TUNNEL=0
#   make setup         # create venv + install deps
#   make check         # DB smoke check via CLI
#   make health        # ping /healthz
#   make db-reset      # apply schema + seed (requires DB_* in .env)
#   make db-apply      # apply schema only

# Optional .env include (no error if missing)
ENV ?= .env
-include $(ENV)

# Project-local virtualenv
VENV ?= .venv
PY   := $(VENV)/bin/python3
PIP  := $(VENV)/bin/pip

.PHONY: help venv setup install run run-no-tunnel check health db-reset db-apply

help:
	@echo "Targets:"
	@echo "  make run            - run web server (uses .env; SSH tunnel if enabled)"
	@echo "  make run-no-tunnel  - run web server with USE_SSH_TUNNEL=0"
	@echo "  make setup          - create venv and install requirements"
	@echo "  make check          - DB smoke check via CLI"
	@echo "  make health         - curl /healthz"
	@echo "  make db-reset       - apply schema + seed (requires DB_* in .env)"
	@echo "  make db-apply       - apply schema only"

venv:
	@test -d $(VENV) || python3 -m venv $(VENV)

setup: venv
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt

# Run via our CLI entrypoint (loads env, starts optional tunnel, registers blueprints)
run: setup
	$(PY) -m app.cli web

# Force-disable the SSH tunnel for quick UI testing
run-no-tunnel: setup
	USE_SSH_TUNNEL=0 $(PY) -m app.cli web

check: setup
	$(PY) -m app.cli db-check

health:
	curl -s http://127.0.0.1:5000/healthz | jq .

db-reset:
	@test -n "$(DB_HOST)" || (echo "DB_HOST missing in .env"; exit 1)
	@test -n "$(DB_PORT)" || (echo "DB_PORT missing in .env"; exit 1)
	@test -n "$(DB_USER)" || (echo "DB_USER missing in .env"; exit 1)
	@test -n "$(DB_PASSWORD)" || (echo "DB_PASSWORD missing in .env"; exit 1)
	@echo "Applying schema..."
	mysql --host="$(DB_HOST)" --port="$(DB_PORT)" --user="$(DB_USER)" --password="$(DB_PASSWORD)" < db/schema.sql
	@echo "Seeding data..."
	mysql --host="$(DB_HOST)" --port="$(DB_PORT)" --user="$(DB_USER)" --password="$(DB_PASSWORD)" SDD_003_database < db/seed.sql

db-apply:
	@test -n "$(DB_HOST)" || (echo "DB_HOST missing in .env"; exit 1)
	@test -n "$(DB_PORT)" || (echo "DB_PORT missing in .env"; exit 1)
	@test -n "$(DB_USER)" || (echo "DB_USER missing in .env"; exit 1)
	@test -n "$(DB_PASSWORD)" || (echo "DB_PASSWORD missing in .env"; exit 1)
	mysql --host="$(DB_HOST)" --port="$(DB_PORT)" --user="$(DB_USER)" --password="$(DB_PASSWORD)" SDD_003_database < db/schema.sql
