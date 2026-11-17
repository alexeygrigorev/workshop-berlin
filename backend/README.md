# Where Should We Eat? - backend

FastAPI implementation of [`../api/openapi.yaml`](../api/openapi.yaml) (all 40 operations) with an
**in-memory store** seeded with demo data. Restarting the server resets everything.
Dependencies are managed with [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`).

## Install, run, test

```sh
cd backend
uv sync                                                    # creates .venv (gitignored), installs pinned deps incl. dev group
uv run uvicorn app.main:create_app --factory --port 8000   # http://localhost:8000 (docs at /docs)
uv run pytest                                              # 65 tests
```

Note: the spec's local server entry says port 8787; the backend defaults to 8000 as requested. Point the
frontend (or `servers` in the spec) at whichever you use.

## Seed data and demo credentials

Seeded at startup (set `WSWE_SEED=false` to start empty). All demo users share the password **`password123`**.

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
| `WSWE_SEED` | `true` | seed demo data |
| `WSWE_SCHEDULER_INTERVAL_SECONDS` | `30` | background tick that creates/opens/finalizes polls (`0` = off; reads also reconcile lazily) |
| `WSWE_FIXED_NOW` | unset | freeze server time at an ISO instant (demos) |
| `WSWE_SESSION_DAYS` | `30` | sliding session length |
| `WSWE_ARGON2_*` | argon2-cffi defaults | `TIME_COST`, `MEMORY_KIB`, `PARALLELISM` |

## Layout

```
app/
  main.py        app factory: create_app(settings=None, clock=None); CORS, error handlers, scheduler loop, seed
  config.py      Settings (env)
  clock.py       Clock / FrozenClock and the get_clock dependency (inject time in tests)
  errors.py      RFC 9457 problem+json, stable error codes, validation-error mapping
  models.py      pydantic schemas mirroring the spec
  store.py       in-memory store + domain logic (polls lifecycle, snapshots, finalization, idempotency keys)
  scoring.py     pure 3/2/1 scoring and tie-break (first, second, seeded draw)
  scheduling.py  team-local weekday/DST window computation (zoneinfo)
  events.py      in-process pub/sub, 10 min replay buffer, SSE stream generator
  auth.py        argon2id hashing, session + personal-API-token auth dependency (scopes, sliding expiry)
  deps.py        team membership/admin dependency, If-Match / Idempotency-Key helpers
  views.py       store records -> API models
  seed.py        demo data (only used at startup)
  routers/       health, auth, me (+api tokens), teams, members, invites, restaurants, polls, ballots, stats, events
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

- Persistence (in-memory only), rate limiting (`429 rate_limited` is never returned), `503 unavailable`.
- Magic-link / Google OAuth (spec says planned).
- Single-process only: the SSE bus and store are in-process.
