# syntax=docker/dockerfile:1
# One image, one port: FastAPI serves the API (/v1/*) and the static SPA build of the frontend.

# ---- Stage 1: build the static frontend (SPA, no SSR/Nitro server) ----
FROM node:22-alpine AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Empty VITE_API_URL = same origin (the backend serves both the app and /v1).
ENV VITE_API_URL=""
RUN npm run build:static

# ---- Stage 2: Python runtime with backend + built frontend ----
FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY --from=frontend /app/dist/client /app/static

RUN useradd --system --uid 10001 --home-dir /app app && mkdir /data && chown app /data
USER app

ENV PATH="/app/.venv/bin:$PATH" \
    WSWE_STATIC_DIR=/app/static \
    WSWE_DATABASE_URL=sqlite:////data/wswe.db \
    WSWE_SEED_DEMO_DATA=true \
    WSWE_APP_ORIGIN=http://localhost:8000 \
    WSWE_CORS_ORIGINS=http://localhost:8000

VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
