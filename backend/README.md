# Where Should We Eat? - backend

FastAPI implementation of [`../api/openapi.yaml`](../api/openapi.yaml) (all 40 operations) persisted in a
**SQL database via SQLAlchemy 2.0** (SQLite by default, PostgreSQL supported, schema managed by Alembic) and seeded with demo data on
first start. Data survives restarts.
Dependencies are managed with [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`).

## Install, run, test

```sh
cd backend
uv sync                                                    # creates .venv (gitignored), installs pinned deps incl. dev group
uv run uvicorn app.main:create_app --factory --port 8000   # http://localhost:8000 (docs at /docs)
uv run pytest                                              # all tests (each on a fresh temp SQLite file; see Testing on PostgreSQL)
uv run alembic upgrade head                                # apply migrations by hand (see Database below)
```

Note: the spec's local server entry says port 8787; the backend defaults to 8000 as requested. Point the
frontend (or `servers` in the spec) at whichever you use.

## Seed data and demo credentials

Seeded at startup into an **empty database only** (set `WSWE_SEED_DEMO_DATA=false` to start empty; delete `wswe.db` to reseed). All demo users share the password **`password123`**.

| email | name | teams |
|---|---|---|
| `anna@example.com` | Anna | admin of **Design crew**, member of **Platform team** |
| `ben@example.com` | Ben | admin of Design crew |
| `carla@example.com` | Carla | member of Design crew |
| `dmitri@example.com` | Dmitri | member of Design crew (has not voted today) |
| `eva@example.com` | Eva | admin of Platform team (08:30-11:00 schedule) |

- Restaurants: the Berlin Friedrichstrasse list from `frontend/src/lib/seed-restaurants.ts`, copied into
  `app/seed.py` and used **only** by the seed code. Teams created through the API always start empty.
  Design crew also has one archived restaurant.
- Today's poll (Design crew) has live ballots from Anna, Ben and Carla if the poll is open at startup
  (08:00-11:30 Europe/Berlin, Mon-Fri). Outside that window the ballots are still there once it has closed; before
  opening or on weekends the poll is `scheduled`. To always demo an open poll, freeze the clock:
  `WSWE_FIXED_NOW=2026-11-18T09:00:00Z uv run uvicorn app.main:create_app --factory --port 8000`.
- History: 8 closed weekday polls for Design crew (including a seeded random-draw tie, a first-place-votes tie and a
  no-ballots day) and 4 for Platform team, with final scores and winners.
- Invite tokens: `demo-design-crew-invite`, `demo-platform-team-invite` (`POST /v1/invites/<token>/accept`).

Quick check:

```sh
curl localhost:8000/v1/health
curl -X POST localhost:8000/v1/auth/sign-in -H 'content-type: application/json' \
     -d '{"email":"anna@example.com","password":"password123"}'
```

## Configuration (environment variables, prefix `WSWE_`, optional `.env`)

| variable | default | meaning |
|---|---|---|
| `WSWE_CORS_ORIGINS` | `http://localhost:8080,http://localhost:5173,http://localhost:3000` | comma separated CORS allowlist; also the origins trusted for cookie-authenticated unsafe requests |
| `WSWE_APP_ORIGIN` | first CORS origin | base for invite URLs (`<origin>/join/<token>`) |
| `WSWE_COOKIE_SECURE` | `false` | set `true` behind HTTPS (the `wswe_session` cookie is always HttpOnly, SameSite=Lax) |
| `WSWE_DATABASE_URL` | `sqlite:///./wswe.db` | SQLAlchemy URL of the database (the SQLite file is gitignored); `postgresql://`, `postgres://` and `postgresql+psycopg://` all work (see PostgreSQL) |
| `WSWE_AUTO_MIGRATE` | unset = `true` for SQLite, `false` otherwise | run `alembic upgrade head` at startup |
| `WSWE_SEED_DEMO_DATA` | `true` | seed demo data at startup, only if the database has no users (never from an endpoint) |
| `WSWE_SCHEDULER_INTERVAL_SECONDS` | `30` | background tick that creates/opens/finalizes polls (`0` = off; reads also reconcile lazily) |
| `WSWE_FIXED_NOW` | unset | freeze server time at an ISO instant (demos) |
| `WSWE_SESSION_DAYS` | `30` | sliding session length |
| `WSWE_ARGON2_*` | argon2-cffi defaults | `TIME_COST`, `MEMORY_KIB`, `PARALLELISM` |

## Database

- Engine/session: `app/db/session.py`. SQLite-only settings (`check_same_thread=False`, `PRAGMA foreign_keys=ON`,
  explicit `BEGIN` so SAVEPOINTs work) are applied only for `sqlite:` URLs; other backends use plain defaults.
- One transaction per request (`app/store.py`, `unit_of_work`): committed when the handler returns, rolled back on
  any error. SSE events are queued during the request and published only after a successful commit.
- Schema: `alembic/` (initial migration `0001`). With `WSWE_AUTO_MIGRATE` on (default for SQLite) the app upgrades
  the schema on startup; otherwise run `uv run alembic upgrade head` (uses `WSWE_DATABASE_URL`, `.env` works too).
  After changing `app/db/models.py`: `uv run alembic revision --autogenerate -m "what changed"`, review, commit.
  A test fails if the models and migrations drift apart.
- Concurrency patterns (portable): unique `(team_id, poll_date)` poll creation via savepoint + re-read; ballot
  replace is an update of the single `(poll_id, user_id)` row under a `SELECT ... FOR UPDATE` poll lock (no-op on
  SQLite); finalization re-checks `finalized_at` after taking that lock, so it is idempotent; teams/restaurants use
  a version column (`UPDATE ... WHERE version = old`, stale writes give `412`).
- Tokens: only SHA-256 hashes of session and personal API tokens are stored.

### PostgreSQL

The driver (`psycopg[binary]`, psycopg 3) is a regular dependency. From the repo root, `make db-up` starts a
`postgres:16-alpine` container (`wswe-db`, user/password/db `wswe`, port 5432, volume `wswe_pgdata`; idempotent),
`make db-psql` opens psql, `make db-down` stops it (data stays in the volume).

```sh
export WSWE_DATABASE_URL=postgresql+psycopg://wswe:wswe@localhost:5432/wswe   # postgresql:// or postgres:// also work
uv run alembic upgrade head          # AUTO_MIGRATE is off by default for non-SQLite: run this as a deploy step ...
# ... or set WSWE_AUTO_MIGRATE=true to upgrade at startup (fine for a single instance)
uv run uvicorn app.main:create_app --factory --port 8000      # or: make backend-pg
```

`postgres://` / `postgresql://` URLs are rewritten to `postgresql+psycopg://` (`app/db/session.py`). The pool uses
`pool_pre_ping` and a 30 minute `pool_recycle`.

### Testing on PostgreSQL

```sh
make db-up
WSWE_TEST_DATABASE_URL=postgresql+psycopg://wswe:wswe@localhost:5432/wswe uv run pytest
```

Each test creates its own throw-away database (`wswe_test_<random>`) on that server and drops it afterwards; the
database in the URL (your `wswe` data) is only used to connect and is never touched. The role needs `CREATEDB`
(the container's `wswe` superuser has it). Without the variable the suite runs on temp SQLite files as before.

## Layout

```
app/
  main.py        app factory: create_app(settings=None, clock=None); CORS, error handlers, scheduler loop, seed
  config.py      Settings (env)
  clock.py       Clock / FrozenClock and the get_clock dependency (inject time in tests)
  errors.py      RFC 9457 problem+json, stable error codes, validation-error mapping
  models.py      pydantic API schemas mirroring the spec (ORM models are in db/models.py)
  db/            models.py (SQLAlchemy ORM), session.py (engine, sqlite-only tweaks), types.py (UTC datetime, JSON
                 UUID types), migrate.py (embedded Alembic)
  store.py       Store (one SQLAlchemy session): data access + domain logic (poll lifecycle, snapshots,
                 finalization, idempotency keys); unit_of_work() transaction helper
  scoring.py     pure 3/2/1 scoring and tie-break (first, second, seeded draw)
  scheduling.py  team-local weekday/DST window computation (zoneinfo)
  events.py      in-process pub/sub, 10 min replay buffer, SSE stream generator
  auth.py        argon2id hashing, session + personal-API-token auth dependency (scopes, sliding expiry)
  deps.py        team membership/admin dependency, If-Match / Idempotency-Key helpers
  views.py       store records -> API models
  seed.py        demo data (only used at startup, into an empty DB)
  routers/       health, auth, me (+api tokens), teams, members, invites, restaurants, polls, ballots, stats, events
alembic/         migration environment and versions
tests/           pytest + httpx TestClient; every response is validated against api/openapi.yaml (openapi-core)
```

## Behaviour notes

- Auth: argon2id password hashes; opaque `wswe_ses_...` session tokens (30-day sliding expiry) and `wswe_pat_...`
  personal tokens with `read`/`write` scopes (`403 insufficient_scope`); only SHA-256 hashes of tokens are stored.
  The `wswe_session` cookie works too (unsafe methods then need an allowed `Origin`).
- Time: all logic uses the injected clock; poll windows are computed from the team's IANA timezone (DST safe).
  Polls are created lazily (and by the tick), finalized idempotently at/after `closes_at` by any read, the
  scheduler or `finalizePoll`. The tie-break seed is stored privately on the poll and never returned.
- A team created after today's closing time gets the *next* poll as its current one (no empty closed poll).

## Not implemented / known gaps

- Rate limiting (`429 rate_limited` is never returned), `503 unavailable`.
- Magic-link / Google OAuth (spec says planned).
- The SSE bus (and its 10 min replay buffer) is in-process: with several server processes a client only sees
  events caused by requests handled by the process it is connected to (everything else is still correct; clients
  refetch on `resync`). Use a shared broker (e.g. Postgres LISTEN/NOTIFY or Redis) to scale out.
- The scheduler tick runs in every process (it is idempotent and row-locked, so that is safe, just redundant).
- A lost race on a reused `Idempotency-Key` surfaces as a 500 instead of a replay.

## Serving the frontend (optional)

Set `WSWE_STATIC_DIR` to a built SPA directory (containing `index.html` and `assets/`, e.g.
`frontend/dist/client` from `npm run build:static`) and the app serves it at `/`. Unset (default) = disabled, so
local dev and tests are unaffected. The catch-all is registered after the API routers, so `/v1/*` always wins
(unknown `/v1/*` paths return 404, not the shell). Non-file paths such as `/teams` or `/join/<token>` fall back to
`index.html` (`Cache-Control: no-cache`); files under `assets/` get `immutable` one-year caching; missing files with
an extension return 404; paths escaping the directory are rejected. See `app/static.py` and the Docker section of
the root README.
