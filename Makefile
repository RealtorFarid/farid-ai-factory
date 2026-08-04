.DEFAULT_GOAL := help
.PHONY: help install run smoke test cov lint format typecheck check \
	web web-install web-build web-check dev \
	docker-build docker-up docker-down unhide materialise clean

BACKEND := backend
WEB := apps/web

# On this machine a background process re-applies the macOS UF_HIDDEN flag to
# files under ~/Documents. CPython silently skips hidden .pth files, which
# breaks editable installs at random. Setting the source path explicitly makes
# every target immune. See "Known environment issue" in README.md.
export PYTHONPATH := src

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Create the venv and install all dependencies
	cd $(BACKEND) && uv sync --extra dev

run: ## Start the API server
	cd $(BACKEND) && uv run python -m backend.cli

smoke: ## Run one agent turn against a real model (needs credentials)
	cd $(BACKEND) && uv run python -m backend.runtime.main

test: ## Run the test suite
	cd $(BACKEND) && uv run pytest

cov: ## Run the test suite with a coverage report
	cd $(BACKEND) && uv run pytest --cov --cov-report=term-missing

lint: ## Check formatting and lint rules
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .

format: ## Apply formatting and safe lint fixes
	cd $(BACKEND) && uv run ruff format . && uv run ruff check . --fix

typecheck: ## Run mypy in strict mode
	cd $(BACKEND) && uv run mypy

check: lint typecheck cov web-check ## Run everything CI runs

# ---- Database --------------------------------------------------------------
# Persistence is opt-in: set PROPILOT_DATABASE_URL in backend/.env to turn it
# on. Without it the app runs entirely in memory, which is what the e2e suite
# and demos use.

db-start: ## Start the local Postgres service
	brew services start postgresql@17

db-create: ## Create the local development and test databases
	@createdb propilot 2>/dev/null && echo "created propilot" || echo "propilot already exists"
	@createdb propilot_test 2>/dev/null && echo "created propilot_test" || echo "propilot_test already exists"

db-migrate: ## Apply migrations to PROPILOT_DATABASE_URL
	cd $(BACKEND) && uv run alembic upgrade head

db-revision: ## Autogenerate a migration:  make db-revision m="add x"
	cd $(BACKEND) && uv run alembic revision --autogenerate -m "$(m)"

db-check: ## Fail if the models have drifted from the migrations
	cd $(BACKEND) && uv run alembic check

db-reset: ## Drop and recreate the LOCAL dev database, then migrate
	@printf 'This destroys the local propilot database. Continue? [y/N] ' && read ans && [ "$$ans" = "y" ]
	dropdb --if-exists propilot && createdb propilot
	$(MAKE) db-migrate

# ---- Web -------------------------------------------------------------------

web-install: ## Install web dependencies
	cd $(WEB) && npm install

web: ## Start the web app (expects `make run` in another shell)
	cd $(WEB) && npm run dev

web-build: ## Build the web app for production
	cd $(WEB) && npm run build

web-check: ## Typecheck, lint and build the web app
	cd $(WEB) && npm run typecheck && npm run lint && npm run build

dev: ## Start the API and the web app together
	@echo "API on :8000, web on :5173 — Ctrl-C stops both"
	@$(MAKE) run & $(MAKE) web & wait

docker-build: ## Build the container image
	docker build -t propilot-backend:local $(BACKEND)

docker-up: ## Start the stack in the background
	docker compose up --build -d

docker-down: ## Stop the stack
	docker compose down

unhide: ## Repair .pth files hidden by macOS (see README)
	@chflags nohidden $(BACKEND)/.venv/lib/python*/site-packages/*.pth 2>/dev/null \
		&& echo "Cleared UF_HIDDEN on .pth files." || echo "Nothing to repair."

materialise: ## Force-download venv files evicted by iCloud (see README)
	@echo "Materialising $(BACKEND)/.venv — this can take several minutes."
	@find $(BACKEND)/.venv -name '*.py' -type f -exec cat {} + > /dev/null 2>&1 || true
	@echo "Still dataless: $$(find $(BACKEND)/.venv -name '*.py' -flags +dataless 2>/dev/null | wc -l | tr -d ' ')"

clean: ## Remove caches and build artefacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache \
		$(BACKEND)/.coverage $(BACKEND)/coverage.xml $(BACKEND)/htmlcov
