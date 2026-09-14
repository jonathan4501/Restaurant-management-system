# RENZY — developer targets. Run from the repo root.
# On Windows without make: run the commands below directly, or `docker compose -f infra/compose.dev.yml exec api make <target>`.

COMPOSE   = docker compose -f infra/compose.dev.yml
UV        = uv
BACKEND   = cd backend &&
FRONTEND  = cd frontend &&

.PHONY: up down migrate seed test check lint fmt typecheck openapi types dev

up:                ## start Postgres + Redis (dev)
	$(COMPOSE) up -d db redis

down:
	$(COMPOSE) down

migrate:
	$(BACKEND) $(UV) run python manage.py migrate

seed:
	$(BACKEND) $(UV) run python manage.py seed_renzy

dev:               ## API with reload on :8000
	$(BACKEND) $(UV) run uvicorn config.asgi:application --reload --port 8000

test:
	$(BACKEND) $(UV) run pytest

lint:
	$(BACKEND) $(UV) run ruff check . && $(UV) run black --check .

fmt:
	$(BACKEND) $(UV) run ruff check --fix . && $(UV) run black .

typecheck:
	$(BACKEND) $(UV) run mypy apps config

openapi:           ## regenerate backend/openapi.json and fail if it changed
	$(BACKEND) $(UV) run python manage.py spectacular --file openapi.json --validate
	git diff --exit-code -- backend/openapi.json

types:             ## regenerate frontend types from openapi.json
	$(FRONTEND) npx openapi-typescript ../backend/openapi.json -o lib/api/schema.d.ts

check: lint typecheck test openapi   ## everything CI runs
