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
- `e2e`: Playwright against its own throw-away docker compose stack (report uploaded as an artifact on failure).
- `docker-build`: builds the root `Dockerfile` (no push).
- `deploy`: only on `main` (push or manual run) and only if all of the above passed. It uploads the tree
  (`git archive`, so no git clone is needed on the server) with `deploy/deploy.sh`, runs
  `docker compose ... up -d --build --wait`, prunes dangling images, then checks that `$DEPLOY_URL/v1/health`
  returns 200 (retries for about 2 minutes). `deploy/.env` and the database volume on the server are never touched.
  The deployed commit is written to `.deployed-sha` on the server (the previous one to `.previous-sha`).

Complete steps 1 to 5 above first (Docker installed, `deploy/.env` created in `/root/workshop-berlin`). The server does
not need a git clone; the workflow replaces the code in that directory.

### Secrets and variables (Settings > Secrets and variables > Actions)

| Name | Kind | Meaning |
| --- | --- | --- |
| `DEPLOY_HOST` | secret | server IP or hostname |
| `DEPLOY_USER` | secret | SSH user (e.g. `root`) |
| `DEPLOY_SSH_KEY` | secret | private key (OpenSSH, passwordless), full file contents |
| `DEPLOY_KNOWN_HOSTS` | secret, optional | the server's host key line(s), pins the host; recommended |
| `DEPLOY_PATH` | variable (or secret), optional | checkout dir on the server, default `/root/workshop-berlin` |
| `DEPLOY_URL` | variable | public URL for the health check, e.g. `https://203-0-113-7.sslip.io` |

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
- Rollback: the workflow only deploys the latest `main`:
  revert the commit on `main`, or check out `.previous-sha` locally and run `deploy/deploy.sh` by hand.
- Caveat: the image is built on the server (1 vCPU / 2 GB), so a deploy takes a few minutes. Runs are queued, never
  cancelled, once on `main`.

## Tear down

After the workshop delete the server in the Hetzner console (stops billing and destroys the data).
To only stop the stack: `dc down` (add `-v` to also delete the database volume and certificates).

## Security notes

- The deployment starts empty (`WSWE_SEED_DEMO_DATA=false`). If you set it to `true` for a demo, all demo users share the
  known password `password123` and anyone who finds the URL can sign in, so tear that server down afterwards. Seeding
  only runs against an empty database; to remove demo data later, recreate the database volume (`dc down -v`).
- Sign-in rate limiting is not implemented yet.
- Keep `deploy/.env` private (it is gitignored); it holds the database password.
