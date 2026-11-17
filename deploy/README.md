# Deploy to a single Hetzner VPS

Caddy (automatic HTTPS) -> app (FastAPI + static frontend) -> Postgres, all in Docker Compose on one small server.
Only ports 80/443 are published; the app and database are reachable only inside the compose network.

## 1. Create the server

In the Hetzner Cloud console: new server, **Ubuntu 24.04**, smallest type (CX22 or the cheapest available), add your
**SSH key**, and attach a **firewall** allowing inbound only TCP 22, 80 and 443 (443/UDP too if you want HTTP/3).

## 2. Pick a hostname (no domain needed)

Use the free sslip.io wildcard DNS: the server IP with dashes plus `.sslip.io`. For IP `203.0.113.7` the name is
`203-0-113-7.sslip.io`. Caddy gets a real Let's Encrypt certificate for it. (Your own domain works too: point an A record at the IP.)

## 3. Install Docker and fetch the code

```bash
ssh root@203.0.113.7
curl -fsSL https://get.docker.com | sh
git clone https://github.com/<owner>/workshop-berlin.git && cd workshop-berlin
```

Private repo: use a read-only deploy key or a token (`git clone https://<token>@github.com/<owner>/workshop-berlin.git`),
or copy the working tree with `rsync -a --exclude .git --exclude node_modules --exclude .venv ./ root@203.0.113.7:workshop-berlin/`.

## 4. Configure and start

```bash
cp deploy/.env.example deploy/.env
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 16)/" deploy/.env
nano deploy/.env        # set DOMAIN=203-0-113-7.sslip.io (your IP, dashes)
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
```

The first start builds the image (a few minutes), runs migrations and starts with an empty database (set `WSWE_SEED_DEMO_DATA=true` in `deploy/.env` first if you want the demo users).

## 5. Check

```bash
curl https://$DOMAIN/v1/health        # {"status":"ok",...}
```

Open `https://<DOMAIN>` and create an account (or, with demo data enabled, sign in as `anna@example.com` / `password123`).
If the certificate is not issued, check that ports 80/443 are open in the firewall and `DOMAIN` matches the IP.

## Operate

Shorthand: `alias dc='docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env'`

```bash
dc logs -f app caddy          # logs
dc ps                         # status
git pull && dc up -d --build  # update to the latest code
dc exec -T db pg_dump -U wswe wswe > backup-$(date +%F).sql     # backup
dc exec -T db psql -U wswe wswe < backup.sql                    # restore (into an empty db)
```

## CI/CD (GitHub Actions)

`.github/workflows/ci-cd.yml` runs on every push to `main`, every pull request to `main`, and manually
(Actions tab, "Run workflow"). Jobs:

- `backend-tests`: pytest on SQLite and on a Postgres 16 service container.
- `frontend-tests`: `npm test`, `tsc --noEmit`, `npm run build`, `npm run build:static`.
- `build-image`: builds the root `Dockerfile` once (GHA layer cache) as `wswe:<github sha>`, smoke-tests it (SQLite,
  `/v1/health`), exports it as a gzipped tarball and uploads it as the `wswe-image` artifact (1 day) together with
  `image-manifest.json`. Job outputs: `image_tag`, `image_id`, `tar_sha256`.
- `e2e`: needs `build-image`. Verifies and loads the image, then runs Playwright against its own throw-away docker
  compose stack from that image (no build; report uploaded as an artifact on failure).
- `deploy`: only on `main` (push or manual run), only if all of the above passed and only if the repository variable
  `DEPLOY_ENABLED` is `true` (see "Deploy switch" below). It downloads the same artifact,
  streams it to the server (`docker load`), uploads the tracked files (`git archive`, no git clone needed) and runs
  `deploy/rollout.sh` (zero-downtime, see below), then checks that `$DEPLOY_URL/v1/health`
  returns 200 (retries for about 2 minutes). Nothing is built on the server. `deploy/.env` and the database volume
  are never touched. The deployed commit is written to `.deployed-sha` (the previous one to `.previous-sha`); the
  images of the current and the previous release stay on the server, older `wswe:*` images are removed.

### Same image tested and deployed

The image is built once and never rebuilt; every stage checks that it is byte-for-byte the one `build-image` produced
(the build job's outputs, not the files inside the artifact, are the reference):

1. `build-image` records the image ID (`docker image inspect --format '{{.Id}}'`) and the sha256 of the tarball.
2. `e2e`: sha256 of the downloaded tarball equals `tar_sha256`; after `docker load` the image ID equals `image_id`;
   `e2e/global-setup.ts` fails if `WSWE_IMAGE` is missing (it never builds or pulls then) and, once the stack is up,
   asserts the running app container's image ID equals the expected one. `e2e` reports the ID it tested.
3. `deploy`: the tested ID must equal the built ID; sha256 of the downloaded tarball equals `tar_sha256`.
4. On the server `deploy.sh` re-checks the sha256 of what it received, the ID after `docker load`, and, after
   `up --no-build --wait`, that the running `app` container's image ID equals the expected one. The log prints
   `EXPECTED ... ACTUAL ...` for each check.

Check by hand: the run's `image-manifest.json` (artifact `wswe-image`, or the `build-image` log) has `image_id`;
on the server compare it with

```bash
docker inspect --format '{{.Image}}' "$(dc ps -q app)"    # dc: see step 4 of the setup; same as the manifest image_id
cat /root/workshop-berlin/.deployed-sha                    # the commit; image tag is wswe:<that sha>
```

Complete steps 1 to 5 above first (Docker installed, `deploy/.env` created in `/root/workshop-berlin`). The server does
not need a git clone; the workflow replaces the code in that directory.

### Secrets and variables (Settings > Secrets and variables > Actions)

| Name | Kind | Meaning |
| --- | --- | --- |
| `DEPLOY_ENABLED` | variable | master switch: must be `true` for the `deploy` job to run; unset or anything else = skipped |
| `DEPLOY_HOST` | secret | server IP or hostname |
| `DEPLOY_USER` | secret | SSH user (e.g. `root`) |
| `DEPLOY_SSH_KEY` | secret | private key (OpenSSH, passwordless), full file contents |
| `DEPLOY_KNOWN_HOSTS` | secret, optional | the server's host key line(s), pins the host; recommended |
| `DEPLOY_PATH` | variable (or secret), optional | checkout dir on the server, default `/root/workshop-berlin` |
| `DEPLOY_URL` | variable | public URL for the health check, e.g. `https://203-0-113-7.sslip.io` |

#### Deploy switch

The `deploy` job runs only when `DEPLOY_ENABLED` is `true` (lowercase). If it is unset or anything else, the job is shown
as "skipped" and the run stays green: all tests still run on every push, nothing contacts the server.

```bash
gh variable set DEPLOY_ENABLED --body false   # disable deploys (tests still run)
gh variable set DEPLOY_ENABLED --body true    # re-enable; the next push or manual run deploys
```

The other `DEPLOY_*` secrets and variables are kept while disabled. Before re-enabling, make sure they are current
(the server exists and `DEPLOY_HOST`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`, `DEPLOY_URL` point at it).

Create a dedicated deploy key (do not reuse a personal key):

```bash
ssh-keygen -t ed25519 -f deploy_key -N "" -C "github-actions-deploy"
ssh-copy-id -i deploy_key.pub root@203.0.113.7     # or append deploy_key.pub to ~/.ssh/authorized_keys on the server
ssh-keyscan -t ed25519 203.0.113.7                  # paste the output into DEPLOY_KNOWN_HOSTS (verify it against the server console if you can)
```

Paste the contents of `deploy_key` into `DEPLOY_SSH_KEY`, then delete the local `deploy_key` files.
Without `DEPLOY_KNOWN_HOSTS` the script runs `ssh-keyscan` at deploy time, which works but trusts whatever answers
(no protection against a man-in-the-middle).

Optional: create a `production` environment (Settings > Environments) with required reviewers, so every deploy needs an
approval. The `deploy` job already uses `environment: production` (GitHub creates it on first use if missing).

### Running and watching

- Manual run: Actions > CI/CD > Run workflow (branch `main`), or `gh workflow run ci-cd.yml --ref main`.
- Logs: the run page in the Actions tab (one log per job); on the server `dc logs -f app caddy`.
- Rollback: the previous release image is still on the server (`docker image ls wswe`, previous sha in
  `/root/workshop-berlin/.previous-sha`). Run it without a build (database untouched):

  ```bash
  cd /root/workshop-berlin
  prev="$(cat .previous-sha)"
  WSWE_IMAGE="wswe:$prev" sh deploy/rollout.sh      # same zero-downtime rollout, now to the previous image
  echo "$prev" > .deployed-sha
  ```

  (The previous release must work with the current database schema: see the migration rule below.)
  Note that the next CI deploy overwrites this; to make a rollback permanent, revert the commit on `main`.
- Manual build on the server (fallback, slow on 1 vCPU / 2 GB):
  `docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build` builds `wswe:prod`.
- Runs are queued, never cancelled, once on `main`. The image tarball (a few hundred MB gzipped) is uploaded over SSH
  on every deploy.

## Zero-downtime rollouts

`deploy.sh` runs `deploy/rollout.sh` instead of recreating the app container, so users see no 502 during a deploy:

1. `db` is brought up (no-op when running); `caddy` is started if needed and re-reads `deploy/Caddyfile` with
   `caddy reload` (no restart).
2. The **new** `app` container is started next to the old one (`up --no-recreate --scale app=2`: the old container is
   not touched, the extra one is created from the new image). Both are behind the one Caddy and use the one Postgres.
3. The script polls `docker inspect` until the new container is `healthy` (default timeout 120 s, `ROLLOUT_TIMEOUT`).
   **If it never becomes healthy (or exits), only the new container is removed, the old one keeps serving and the
   script exits non-zero**, so the deploy job fails and nothing user-visible happened.
4. After a short settle time the old container gets `docker stop` (SIGTERM, then SIGKILL after `stop_grace_period`
   30 s) and is removed. uvicorn drains in-flight requests and closes open SSE streams after at most 10 s
   (`--timeout-graceful-shutdown`). Browsers reconnect automatically (`EventSource` sends `Last-Event-ID`); the replay
   buffer is per process, so the new container answers with a `resync` event and the page refetches.
5. Exactly one app container must remain; `deploy.sh` then checks that it runs the expected image ID.

Caddy finds the containers by resolving the compose name `app` every second (`dynamic a` upstreams), drops
unhealthy ones (active check of `/v1/health` every second plus passive marking), and retries a request that hits a
dying or not yet listening container on another one for up to 10 s (`lb_try_duration`). This is why `app` must have no
`container_name` and no published port. Edits of the Caddyfile apply on the next deploy; the reload itself can reset a
connection that is being set up in that very moment, which is the only expected blip.

**Migration rule.** For a few seconds the old release runs against the schema the new release has just migrated (the
new container migrates at boot, before it is healthy). Every migration must therefore be backwards compatible with the
previous release: expand/contract. Add tables and nullable (or defaulted) columns in one release; remove or rename
columns only in a later release, after no running code uses them. Concurrent starts are safe: migrations and the demo
seed take a Postgres advisory lock, and the scheduler is idempotent, so two containers can run it at once.

Roll back by hand: `WSWE_IMAGE=wswe:$(cat .previous-sha) sh deploy/rollout.sh` (see "Running and watching").
A manual `docker compose up -d --build` (fallback) recreates the container and is **not** zero-downtime.

Test locally (never against the dev stack): build two tags of the image (e.g. `wswe:zd1`, `wswe:zd2`), create an env
file with `DOMAIN=localhost` and `POSTGRES_PASSWORD=x`, start `WSWE_IMAGE=wswe:zd1 docker compose -p wswe-zd -f
deploy/docker-compose.prod.yml --env-file zd.env up -d --no-build --wait`, run a loop such as
`while :; do curl -sk -o /dev/null -w '%{http_code}
' https://localhost/v1/health; sleep 0.1; done` and in another
shell `ROLLOUT_PROJECT=wswe-zd ROLLOUT_ENV_FILE=zd.env WSWE_IMAGE=wswe:zd2 sh deploy/rollout.sh`. Expect only `200`.
Try a broken image (e.g. `CMD ["sh","-c","exit 3"]`): the script exits 1 and the loop stays green. Clean up with
`docker compose -p wswe-zd -f deploy/docker-compose.prod.yml --env-file zd.env down -v`.
In CI, the deploy job also probes `$DEPLOY_URL/v1/health` about 5 times a second during the deploy and fails if any
answer is not HTTP 200.

## Tear down

After the workshop delete the server in the Hetzner console (stops billing and destroys the data).
To only stop the stack: `dc down` (add `-v` to also delete the database volume and certificates).

## Security notes

- The deployment starts empty (`WSWE_SEED_DEMO_DATA=false`). If you set it to `true` for a demo, all demo users share the
  known password `password123` and anyone who finds the URL can sign in, so tear that server down afterwards. Seeding
  only runs against an empty database; to remove demo data later, recreate the database volume (`dc down -v`).
- Sign-in rate limiting is not implemented yet.
- Keep `deploy/.env` private (it is gitignored); it holds the database password.
