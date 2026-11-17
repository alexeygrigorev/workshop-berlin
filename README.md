# workshop-berlin

https://github.com/alexeygrigorev/screenshot-spot-on-58

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
