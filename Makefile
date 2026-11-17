.PHONY: frontend backend backend-test frontend-test help up down psql backend-pg

help:
	@echo "make frontend       run the frontend dev server (vite)"
	@echo "make backend        run the FastAPI backend on :8000"
	@echo "make backend-test   run backend tests"
	@echo "make frontend-test  run frontend tests"
	@echo "make up             start Postgres via docker compose (waits until healthy)"
	@echo "make down           stop compose services (data volume kept)"
	@echo "make psql           psql shell in the db service"
	@echo "make backend-pg     run the backend on :8000 against the Postgres container"
	@echo "Tip: WSWE_FIXED_NOW=2026-11-18T09:00:00Z make backend  (freeze the clock so today's poll is open)"

frontend:
	cd frontend && npm install && npm run dev

backend:
	cd backend && uv sync && uv run uvicorn app.main:create_app --factory --reload --port 8000

backend-test:
	cd backend && uv run pytest

frontend-test:
	cd frontend && npm test

.PHONY: docker-build docker-run
docker-build:
	docker build -t wswe .

docker-run:
	docker compose --profile app up --build

# ---- PostgreSQL via docker compose (service db, data in volume wswe_pgdata) ----
PG_URL = postgresql+psycopg://wswe:wswe@localhost:5432/wswe

up:
	docker compose up -d --wait db
	@echo "postgres ready: $(PG_URL)"

down:
	docker compose --profile app down

psql:
	docker compose exec db psql -U wswe

backend-pg:
	cd backend && uv sync && WSWE_DATABASE_URL=$(PG_URL) uv run alembic upgrade head && WSWE_DATABASE_URL=$(PG_URL) uv run uvicorn app.main:create_app --factory --reload --port 8000
