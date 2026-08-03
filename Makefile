.DEFAULT_GOAL := help
.PHONY: help install run smoke test cov lint format typecheck check docker-build docker-up docker-down unhide clean

BACKEND := backend

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

check: lint typecheck cov ## Run everything CI runs

docker-build: ## Build the container image
	docker build -t propilot-backend:local $(BACKEND)

docker-up: ## Start the stack in the background
	docker compose up --build -d

docker-down: ## Stop the stack
	docker compose down

unhide: ## Repair .pth files hidden by macOS (see README)
	@chflags nohidden $(BACKEND)/.venv/lib/python*/site-packages/*.pth 2>/dev/null \
		&& echo "Cleared UF_HIDDEN on .pth files." || echo "Nothing to repair."

clean: ## Remove caches and build artefacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache \
		$(BACKEND)/.coverage $(BACKEND)/coverage.xml $(BACKEND)/htmlcov
