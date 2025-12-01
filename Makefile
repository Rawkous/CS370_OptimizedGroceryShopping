# Makefile for GroceryAppClean / grocoLoco
# Assumes structure:
#  - python/app.py (entrypoint)
#  - requirements.txt in project root
#  - db/schema.sql, db/seed.sql
#  - .env in project root

PYTHON      := python3
VENV_DIR    := .venv
VENV_PY     := $(VENV_DIR)/bin/python
PIP         := $(VENV_PY) -m pip

APP_ENTRY   := python/app.py

# --- Default target -------------------------------------------------------

.PHONY: help
help:
	@echo "Available targets:"
	@echo "  make venv        - create a virtual environment in $(VENV_DIR)/"
	@echo "  make install     - install Python dependencies into the venv"
	@echo "  make run         - run the Flask app via python/app.py"
	@echo "  make db-schema   - apply database schema (requires DB_* env vars)"
	@echo "  make db-seed     - seed the database with sample data"
	@echo "  make db-reset    - schema + seed"
	@echo "  make clean       - remove virtualenv and __pycache__ files"

# --- Virtualenv & dependencies -------------------------------------------

$(VENV_DIR):
	$(PYTHON) -m venv $(VENV_DIR)
	# Make sure pip exists in the venv even on minimal installs
	$(VENV_PY) -m ensurepip --upgrade || true

.PHONY: venv
venv: $(VENV_DIR)
	@echo "Virtual environment ready in $(VENV_DIR)/"

.PHONY: install
install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "Dependencies installed."

# --- Run app -------------------------------------------------------------

.PHONY: run
run: install
	@echo "Starting app..."
	$(VENV_PY) $(APP_ENTRY)

# --- Database helpers ----------------------------------------------------
# These assume you export the following in your shell or `.env`:
#   DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

MYSQL      := mysql

.PHONY: db-schema
db-schema:
	@if [ -z "$$DB_HOST" ] || [ -z "$$DB_USER" ] || [ -z "$$DB_NAME" ]; then \
		echo "Please set DB_HOST, DB_USER, DB_PASSWORD, DB_NAME environment variables."; \
		exit 1; \
	fi
	@echo "Applying schema from db/schema.sql..."
	@$(MYSQL) -h $$DB_HOST -u $$DB_USER -p$$DB_PASSWORD $$DB_NAME < db/schema.sql
	@echo "Schema applied."

.PHONY: db-seed
db-seed:
	@if [ -z "$$DB_HOST" ] || [ -z "$$DB_USER" ] || [ -z "$$DB_NAME" ]; then \
		echo "Please set DB_HOST, DB_USER, DB_PASSWORD, DB_NAME environment variables."; \
		exit 1; \
	fi
	@echo "Seeding database from db/seed.sql..."
	@$(MYSQL) -h $$DB_HOST -u $$DB_USER -p$$DB_PASSWORD $$DB_NAME < db/seed.sql
	@echo "Database seeded."

.PHONY: db-reset
db-reset: db-schema db-seed
	@echo "Database reset (schema + seed)."

# --- Cleanup -------------------------------------------------------------

.PHONY: clean
clean:
	@echo "Removing virtualenv and Python cache files..."
	rm -rf $(VENV_DIR)
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find . -name "*.pyc" -delete
	@echo "Clean complete."

.PHONY: test
test: install
	@echo "Running tests..."
	$(VENV_PY) -m pytest -q
