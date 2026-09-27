.PHONY: up down logs dev test lint migrate migration shell-backend shell-db clean format key

COMPOSE_DEV = docker compose -f docker-compose.yml -f docker-compose.dev.yml

# Production stack (only the web UI port is published)
up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f backend

# Development stack: hot reload, all service ports published
dev:
	$(COMPOSE_DEV) up --build

test:
	cd backend && python -m pytest

lint:
	cd backend && black --check . && isort --check-only .

format:
	cd backend && black . && isort .

# Apply migrations to the database in DATABASE_URL
migrate:
	cd backend && alembic upgrade head

# Create a migration from model changes: make migration m="add foo column"
migration:
	cd backend && alembic revision --autogenerate -m "$(m)"

shell-backend:
	docker compose exec backend bash

shell-db:
	docker compose exec postgres psql -U genai_engine -d genai_engine

clean:
	docker compose down -v --remove-orphans

key:
	@python -c "import secrets; print(secrets.token_hex(32))"
