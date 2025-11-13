PY=python3
PIP=python3 -m pip
ENV?=.env
include $(ENV) 2>/dev/null || true

VENV?=.venv
ACTIVATE=. $(VENV)/bin/activate

setup:
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt

venv:
	@test -d $(VENV) || python3 -m venv $(VENV)
	@echo "Run: source $(VENV)/bin/activate"

run:
	$(PY) app.py web

db-reset:
	@test -n "$(DB_HOST)" || (echo "DB_HOST missing in .env"; exit 1)
	@echo "Applying schema..."
	mysql --host="$(DB_HOST)" --port="$(DB_PORT)" --user="$(DB_USER)" --password="$(DB_PASSWORD)" < db/schema.sql
	@echo "Seeding data..."
	mysql --host="$(DB_HOST)" --port="$(DB_PORT)" --user="$(DB_USER)" --password="$(DB_PASSWORD)" SDD_003_database < db/seed.sql

db-apply:
	mysql --host="$(DB_HOST)" --port="$(DB_PORT)" --user="$(DB_USER)" --password="$(DB_PASSWORD)" SDD_003_database < db/schema.sql

health:
	curl -s http://127.0.0.1:5000/healthz | jq .

check:
	$(PY) app.py db-check
