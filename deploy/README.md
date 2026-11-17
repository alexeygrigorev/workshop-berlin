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

The first start builds the image (a few minutes), runs migrations and seeds demo data into the empty database.

## 5. Check

```bash
curl https://$DOMAIN/v1/health        # {"status":"ok",...}
```

Open `https://<DOMAIN>` and sign in as `anna@example.com` / `password123`.
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

## Tear down

After the workshop delete the server in the Hetzner console (stops billing and destroys the data).
To only stop the stack: `dc down` (add `-v` to also delete the database volume and certificates).

## Security notes

- All demo users share the known password `password123`; anyone who finds the URL can sign in. Tear the server down
  after the workshop, or set `WSWE_SEED_DEMO_DATA=false` in `deploy/.env` before the first start to begin empty.
- Sign-in rate limiting is not implemented yet.
- Keep `deploy/.env` private (it is gitignored); it holds the database password.
