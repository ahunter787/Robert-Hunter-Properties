# RHP — developer and operator entry points.
#
# Docker Compose is the canonical runtime for both development and production.
# COMPOSE is overridable so a host without the compose v2 plugin can point at a
# standalone binary:   make up COMPOSE=docker-compose
#
# Host-side Python tooling (tests, lint, Django checks) runs through uv, which
# owns pyproject.toml/uv.lock. The application image stays dependency-lean
# because it installs runtime dependencies only.

COMPOSE ?= docker compose
PROD    := $(COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml
MANAGE  := $(COMPOSE) exec web python manage.py
UV      ?= uv

.DEFAULT_GOAL := help
.PHONY: help init env assets build up down dev logs migrate migrations shell superuser psql wait-ready test lint format check check-deploy health up-prod down-prod prod-logs

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

init: env assets build up wait-ready migrate ## First run: .env, CSS assets, image, stack, migrations
	@echo ""
	@echo "RHP is running at http://localhost:8000"
	@echo "Create the first admin account with: make superuser"

env: ## Create .env from .env.example with generated secrets
	@if [ -f .env ]; then \
		echo ".env already exists; leaving it untouched"; \
	else \
		secret=$$(python3 -c "import secrets; print(secrets.token_urlsafe(64))"); \
		pgpass=$$(python3 -c "import secrets; print(secrets.token_urlsafe(24))"); \
		sed -e "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$$secret|" \
		    -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$$pgpass|" \
		    .env.example > .env; \
		chmod 600 .env; \
		echo "Created .env with a generated DJANGO_SECRET_KEY and POSTGRES_PASSWORD"; \
	fi

assets: ## Build the Tailwind stylesheet into static/css/rhp.css (requires Node)
	npm install --no-audit --no-fund
	npm run build:css

build: ## Build the application image
	$(COMPOSE) build

up: ## Start the development stack in the background
	$(COMPOSE) up -d
	@echo "RHP is starting — http://localhost:8000 (logs: make logs)"

dev: ## Run the development stack in the foreground
	$(COMPOSE) up

down: ## Stop the development stack
	$(COMPOSE) down

logs: ## Follow application logs
	$(COMPOSE) logs -f web

migrate: ## Apply database migrations in the running web container
	$(MANAGE) migrate

migrations: ## Create migrations from model changes (host-side, so new files are yours)
	$(UV) run python manage.py makemigrations

wait-ready: ## Wait until the application answers /healthz (up to 60s)
	@for i in $$(seq 1 60); do \
		if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then \
			echo "RHP is responding on http://localhost:8000"; exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "RHP did not become ready within 60s - check 'make logs'"; exit 1

shell: ## Open a Django shell in the web container
	$(MANAGE) shell

superuser: ## Create an admin account
	$(MANAGE) createsuperuser

psql: ## Open a psql session on the project database
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-rhp} -d $${POSTGRES_DB:-rhp}

test: ## Run the test suite (needs the dev stack's published database)
	$(UV) run pytest

lint: ## Check lint rules and formatting
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format: ## Auto-format and auto-fix
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

check: ## Run Django system checks (development settings)
	$(UV) run python manage.py check

check-deploy: ## Run Django deployment checks against production settings
	DJANGO_SETTINGS_MODULE=config.settings.production \
	DJANGO_SECRET_KEY=deploy-check-only-not-a-real-secret-0f3c5e7a9d1b2f4c6e8a0d3f5b7c9e1a \
	DJANGO_ALLOWED_HOSTS=localhost \
	DJANGO_SECURE_PROXY_SSL_HEADER=1 \
	RHP_TRUST_PROXY_HEADERS=1 \
	DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend \
	DJANGO_EMAIL_HOST=smtp.example.com \
	DJANGO_EMAIL_HOST_USER=rhp@example.com \
	DJANGO_EMAIL_HOST_PASSWORD=deploy-check-only \
	$(UV) run python manage.py check --deploy

health: ## Probe the running application
	curl -fsS http://localhost:8000/healthz && echo

up-prod: ## Start the production stack (Caddy + gunicorn)
	$(PROD) up -d --build

down-prod: ## Stop the production stack
	$(PROD) down

prod-logs: ## Follow production logs
	$(PROD) logs -f web
