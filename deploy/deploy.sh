#!/bin/sh
# Deploy the checked-out git tree to the production server over SSH (no git clone needed on the server).
#
# Required env: DEPLOY_HOST, DEPLOY_USER, DEPLOY_SSH_KEY_FILE (path to a passwordless OpenSSH private key)
# Optional env:
#   DEPLOY_PATH         remote checkout dir (default /root/workshop-berlin)
#   DEPLOY_KNOWN_HOSTS  contents of a known_hosts line for the server (recommended: pins the host key).
#                       If empty, the host key is fetched with ssh-keyscan (trust-on-first-use per run:
#                       convenient, but does not protect against a man-in-the-middle).
#   DEPLOY_SHA          git SHA being deployed (default: git rev-parse HEAD); recorded in .deployed-sha
#   DEPLOY_DRY_RUN=1    only print what would be done
#
# Uploads `git archive HEAD` (tracked files only, minus e2e/ and .github/) and never touches deploy/.env or the
# database volume, which live only on the server. Idempotent: safe to re-run.
# shellcheck disable=SC2029  # DEPLOY_* are validated below; client-side expansion is intended
set -eu

: "${DEPLOY_HOST:?DEPLOY_HOST is required}"
: "${DEPLOY_USER:?DEPLOY_USER is required}"
: "${DEPLOY_SSH_KEY_FILE:?DEPLOY_SSH_KEY_FILE is required}"
DEPLOY_PATH="${DEPLOY_PATH:-/root/workshop-berlin}"
DEPLOY_SHA="${DEPLOY_SHA:-$(git rev-parse HEAD)}"
DRY="${DEPLOY_DRY_RUN:-0}"

# The values end up inside a remote shell command line, so allow only harmless characters.
case "$DEPLOY_PATH" in /*) ;; *) echo "DEPLOY_PATH must be absolute" >&2; exit 2 ;; esac
case "$DEPLOY_PATH$DEPLOY_SHA$DEPLOY_HOST$DEPLOY_USER" in
  *[!A-Za-z0-9_./:@-]*) echo "unsupported characters in DEPLOY_* values" >&2; exit 2 ;;
esac

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT INT TERM
known_hosts="$workdir/known_hosts"

if [ -n "${DEPLOY_KNOWN_HOSTS:-}" ]; then
  printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > "$known_hosts"
elif [ "$DRY" = 1 ]; then
  : > "$known_hosts"
else
  echo "WARNING: DEPLOY_KNOWN_HOSTS not set; trusting the host key returned by ssh-keyscan (no MITM protection)." >&2
  ssh-keyscan -T 15 -H "$DEPLOY_HOST" > "$known_hosts"
  [ -s "$known_hosts" ] || { echo "ssh-keyscan returned no host key for $DEPLOY_HOST" >&2; exit 1; }
fi

set -- -i "$DEPLOY_SSH_KEY_FILE" -o IdentitiesOnly=yes -o BatchMode=yes \
  -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known_hosts" \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=20
remote="$DEPLOY_USER@$DEPLOY_HOST"

if [ "$DRY" = 1 ]; then
  echo "[dry-run] would upload git archive of $DEPLOY_SHA to $remote:$DEPLOY_PATH and run compose up --build --wait"
  exit 0
fi

echo "==> Uploading $DEPLOY_SHA to $remote:$DEPLOY_PATH"
# Fail early if the server was not set up (deploy/.env holds the secrets and is never uploaded).
ssh "$@" "$remote" "mkdir -p '$DEPLOY_PATH/deploy' && test -f '$DEPLOY_PATH/deploy/.env'" \
  || { echo "ERROR: $DEPLOY_PATH/deploy/.env missing on the server (see deploy/README.md, step 4)" >&2; exit 1; }

git archive --format=tar HEAD -- . ':(exclude)e2e' ':(exclude).github' \
  | ssh "$@" "$remote" "tar -xf - -C '$DEPLOY_PATH' --no-same-owner"

echo "==> Building and starting the stack"
ssh "$@" "$remote" sh -s -- "$DEPLOY_PATH" "$DEPLOY_SHA" <<'REMOTE'
set -eu
cd "$1"
# Keep the previous release marker for manual rollback (git checkout <sha> locally, re-run the deploy).
[ -f .deployed-sha ] && cp .deployed-sha .previous-sha
dc="docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env"
$dc up -d --build --wait
echo "$2" > .deployed-sha
docker image prune -f
$dc ps
REMOTE
echo "==> Deployed $DEPLOY_SHA"
