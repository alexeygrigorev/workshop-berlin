.PHONY: frontend backend backend-test frontend-test help

help:
	@echo "make frontend       run the frontend dev server (vite)"
	@echo "make backend        run the FastAPI backend on :8000"
	@echo "make backend-test   run backend tests"
	@echo "make frontend-test  run frontend tests"
	@echo "Tip: WSWE_FIXED_NOW=2026-11-18T09:00:00Z make backend  (freeze the clock so today's poll is open)"

frontend:
	cd frontend && npm install && npm run dev

backend:
	cd backend && uv sync && uv run uvicorn app.main:create_app --factory --reload --port 8000

backend-test:
	cd backend && uv run pytest

frontend-test:
	cd frontend && npm test
