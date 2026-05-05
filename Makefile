.PHONY: dev build down logs test migrate shell-backend shell-db clean format key

dev:
	docker compose up --build

build:
	docker compose build

down:
	docker compose down

logs:
	docker compose logs -f backend

test:
	cd backend && pytest tests -v

migrate:
	cd backend && alembic upgrade head

shell-backend:
	docker compose exec backend bash

shell-db:
	docker compose exec postgres psql -U jarvis -d jarvis

clean:
	docker compose down -v --remove-orphans

format:
	cd backend && black . && isort .

key:
	@python -c "import secrets; print(secrets.token_hex(32))"
