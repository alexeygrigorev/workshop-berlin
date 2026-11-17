# workshop-berlin

Links:

- Lovable export: https://github.com/alexeygrigorev/screenshot-spot-on-58
- Browser automation plugin: https://github.com/alexeygrigorev/agent-browser
- Article: https://aishippingblog.com/p/i-built-an-ai-agent-team-for-software
- Agents: https://github.com/AI-Shipping-Labs/website/tree/main/.claude/agents
- Process: https://github.com/AI-Shipping-Labs/website/blob/main/_docs/PROCESS.md

## Run locally (frontend + backend)

```sh
# 1. Backend (FastAPI, in-memory, seeded demo data) on http://localhost:8000
cd backend && uv sync
WSWE_FIXED_NOW=2026-11-18T09:00:00Z uv run uvicorn app.main:create_app --factory --port 8000

# 2. Frontend (Vite) on http://localhost:8080 (next free port if taken)
cd frontend && npm install && npm run dev
```

Sign in as `anna@example.com` / `password123` (also ben, carla, dmitri, eva @example.com), or join with the invite
token `demo-design-crew-invite` (`/join/demo-design-crew-invite`). `WSWE_FIXED_NOW` freezes the server clock so today's
poll is open; omit it for real time.

- The frontend reads the API base URL from `VITE_API_URL` (default `http://localhost:8000`); the session token is kept
  in `localStorage`, live updates use the team SSE stream (fetch-based, bearer auth).
- Browser origin must be in the backend CORS allowlist (`WSWE_CORS_ORIGINS`, default includes 5173, 8080, 3000). If Vite picks
  another port, e.g. `WSWE_CORS_ORIGINS=http://localhost:8081`.
- API contract: `api/openapi.yaml`; see `api/README.md` and `backend/README.md`.

## PostgreSQL (optional)

SQLite is the default; PostgreSQL works too (driver `psycopg[binary]` is installed with the backend).

```sh
make up           # docker compose: Postgres (volume wswe_pgdata keeps the data) + the app image on :8000
make db           # Postgres only, for the next line
make backend-pg   # backend on :8000 against it (postgresql+psycopg://wswe:wswe@localhost:5432/wswe), migrates first
make psql         # psql shell;  make down  stops compose services (data kept)
```

Migrations: `cd backend && WSWE_DATABASE_URL=... uv run alembic upgrade head` (auto-migrate is off by default for
non-SQLite; set `WSWE_AUTO_MIGRATE=true` to enable). Run the tests on Postgres with
`WSWE_TEST_DATABASE_URL=postgresql+psycopg://wswe:wswe@localhost:5432/wswe make backend-test`. Details: `backend/README.md`.

## Docker

One image, one port: a multi-stage build compiles the frontend as a static SPA (`npm run build:static`) and the
FastAPI backend serves it together with the API (`WSWE_STATIC_DIR`).

```sh
make docker-build   # docker build -t wswe .
make up             # docker compose up: app + Postgres -> http://localhost:8000
```

- SQLite lives at `/data/wswe.db` (volume `wswe-data`). Demo data is seeded into an empty DB; disable with
  `-e WSWE_SEED_DEMO_DATA=false`. Sign in as `anna@example.com` / `password123`.
- If you publish on another host/port, set `-e WSWE_APP_ORIGIN=https://your.host -e WSWE_CORS_ORIGINS=https://your.host`
  (invite links are built from `WSWE_APP_ORIGIN`); behind HTTPS also `-e WSWE_COOKIE_SECURE=true`.
- Against PostgreSQL instead of SQLite (service from `make db`; migrations are not automatic there, so run
  `WSWE_AUTO_MIGRATE=true` or `alembic upgrade head` first):
  `make up` runs the app image on :8000 against the compose `db` service with `WSWE_AUTO_MIGRATE=true`; it needs
  port 8000 free (stop `make backend`/`backend-pg` first).
  (on Linux add `--add-host=host.docker.internal:host-gateway`).
- Static frontend build without Docker: `cd frontend && npm run build:static` -> `frontend/dist/client`
  (`npm run build` still produces the SSR/Nitro build).

## End-to-end tests

A Playwright test (`e2e/`, Chromium) signs in as Anna, adds a restaurant to "Design crew", reloads and checks it
persisted (backend + Postgres).

```sh
make e2e    # npm ci, installs chromium, runs the tests
```

- Needs Docker running. The run starts its own throw-away compose project `wswe-e2e` (app on :18000, Postgres on
  :15432, volume `wswe_e2e_pgdata`) and removes it, volume included, afterwards (also when tests fail). Your dev stack
  (`make up`, :8000, `wswe_pgdata`) is not touched and may keep running.
- Headed / debug: `cd e2e && npx playwright test --headed` or `npx playwright test --debug`. Report:
  `npx playwright show-report`.
- Reuse an already running stack (no docker start/stop), e.g. for quick debugging:
  `cd e2e && E2E_BASE_URL=http://localhost:8000 npx playwright test`. The test adds a uniquely named restaurant to
  that stack's "Design crew" team (it is not removed).
