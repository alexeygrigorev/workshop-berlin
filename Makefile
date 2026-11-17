.PHONY: frontend backend backend-test frontend-test help db-up db-down db-psql backend-pg

help:
	@echo "make frontend       run the frontend dev server (vite)"
	@echo "make backend        run the FastAPI backend on :8000"
	@echo "make backend-test   run backend tests"
	@echo "make frontend-test  run frontend tests"
	@echo "make db-up         start the Postgres container (wswe-db)"
	@echo "make db-down        stop it (data volume kept)"
	@echo "make db-psql        psql shell in the container"
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
	docker run --rm -p 8000:8000 -v wswe-data:/data wswe

# ---- PostgreSQL (container wswe-db, data in volume wswe_pgdata) ----
PG_URL = postgresql+psycopg://wswe:wswe@localhost:5432/wswe

db-up:
	@docker start wswe-db 2>/dev/null || docker run -id --name wswe-db -e POSTGRES_USER=wswe -e POSTGRES_PASSWORD=wswe -e POSTGRES_DB=wswe -p 5432:5432 -v wswe_pgdata:/var/lib/postgresql/data postgres:16-alpine
	@until docker exec wswe-db pg_isready -U wswe >/dev/null 2>&1; do sleep 1; done; echo "postgres ready: $(PG_URL)"

db-down:
	docker stop wswe-db

db-psql:
	docker exec -it wswe-db psql -U wswe

backend-pg:
	cd backend && uv sync && WSWE_DATABASE_URL=$(PG_URL) uv run alembic upgrade head && WSWE_DATABASE_URL=$(PG_URL) uv run uvicorn app.main:create_app --factory --reload --port 8000
