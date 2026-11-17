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
# Prebuilt image (all four required; produced once by the CI build-image job):
#   WSWE_IMAGE          image tag, e.g. wswe:<sha>
#   WSWE_IMAGE_TAR      path to the gzipped `docker save` tarball
#   WSWE_IMAGE_SHA256   expected sha256 of that tarball (checked locally and again on the server)
#   WSWE_IMAGE_ID       expected image ID (sha256:...) (checked after `docker load` and on the running container)
#
# Uploads `git archive HEAD` (tracked files only, minus e2e/ and .github/) and the image tarball, never touches
# deploy/.env or the database volume, which live only on the server. Idempotent: safe to re-run.
# The image is not built on the server. The last two wswe:<sha> tags (current + previous) are kept for rollback.
# shellcheck disable=SC2029  # DEPLOY_* are validated below; client-side expansion is intended
set -eu

: "${DEPLOY_HOST:?DEPLOY_HOST is required}"
: "${DEPLOY_USER:?DEPLOY_USER is required}"
: "${DEPLOY_SSH_KEY_FILE:?DEPLOY_SSH_KEY_FILE is required}"
DEPLOY_PATH="${DEPLOY_PATH:-/root/workshop-berlin}"
DEPLOY_SHA="${DEPLOY_SHA:-$(git rev-parse HEAD)}"
DRY="${DEPLOY_DRY_RUN:-0}"
: "${WSWE_IMAGE:?WSWE_IMAGE is required}"
: "${WSWE_IMAGE_TAR:?WSWE_IMAGE_TAR is required}"
: "${WSWE_IMAGE_SHA256:?WSWE_IMAGE_SHA256 is required}"
: "${WSWE_IMAGE_ID:?WSWE_IMAGE_ID is required}"

# The values end up inside a remote shell command line, so allow only harmless characters.
case "$DEPLOY_PATH" in /*) ;; *) echo "DEPLOY_PATH must be absolute" >&2; exit 2 ;; esac
case "$DEPLOY_PATH$DEPLOY_SHA$DEPLOY_HOST$DEPLOY_USER$WSWE_IMAGE$WSWE_IMAGE_SHA256$WSWE_IMAGE_ID" in
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
  echo "[dry-run] would upload git archive of $DEPLOY_SHA and $WSWE_IMAGE_TAR to $remote:$DEPLOY_PATH,"
  echo "[dry-run] verify sha256 $WSWE_IMAGE_SHA256, docker load, check image ID $WSWE_IMAGE_ID,"
  echo "[dry-run] run $WSWE_IMAGE compose up -d --no-build --wait and verify the running container's image ID"
  exit 0
fi

[ -f "$WSWE_IMAGE_TAR" ] || { echo "ERROR: image tarball $WSWE_IMAGE_TAR not found" >&2; exit 1; }
actual_sha="$(sha256sum "$WSWE_IMAGE_TAR" | cut -d' ' -f1)"
echo "tarball sha256 EXPECTED $WSWE_IMAGE_SHA256 ACTUAL $actual_sha"
[ "$actual_sha" = "$WSWE_IMAGE_SHA256" ] || { echo "ERROR: image tarball sha256 mismatch" >&2; exit 1; }

echo "==> Uploading $DEPLOY_SHA to $remote:$DEPLOY_PATH"
# Fail early if the server was not set up (deploy/.env holds the secrets and is never uploaded).
ssh "$@" "$remote" "mkdir -p '$DEPLOY_PATH/deploy' && test -f '$DEPLOY_PATH/deploy/.env'" \
  || { echo "ERROR: $DEPLOY_PATH/deploy/.env missing on the server (see deploy/README.md, step 4)" >&2; exit 1; }

git archive --format=tar HEAD -- . ':(exclude)e2e' ':(exclude).github' \
  | ssh "$@" "$remote" "tar -xf - -C '$DEPLOY_PATH' --no-same-owner"

echo "==> Uploading the image tarball"
ssh "$@" "$remote" "cat > '$DEPLOY_PATH/.image-upload.tar.gz'" < "$WSWE_IMAGE_TAR"

echo "==> Loading and starting the stack"
ssh "$@" "$remote" sh -s -- "$DEPLOY_PATH" "$DEPLOY_SHA" "$WSWE_IMAGE" "$WSWE_IMAGE_ID" "$WSWE_IMAGE_SHA256" <<'REMOTE'
set -eu
cd "$1"
sha="$2"; image="$3"; want_id="$4"; want_sha="$5"
tarball=.image-upload.tar.gz
trap 'rm -f "$tarball"' EXIT

got_sha="$(sha256sum "$tarball" | cut -d' ' -f1)"
echo "server tarball sha256 EXPECTED $want_sha ACTUAL $got_sha"
[ "$got_sha" = "$want_sha" ] || { echo "ERROR: tarball sha256 mismatch on the server" >&2; exit 1; }

gunzip -c "$tarball" | docker load
got_id="$(docker image inspect --format '{{.Id}}' "$image")"
echo "loaded image ID EXPECTED $want_id ACTUAL $got_id"
[ "$got_id" = "$want_id" ] || { echo "ERROR: loaded image ID mismatch" >&2; exit 1; }

# Keep the previous release marker for manual rollback; a re-deploy of the same sha keeps the older marker.
if [ -f .deployed-sha ] && [ "$(cat .deployed-sha)" != "$sha" ]; then cp .deployed-sha .previous-sha; fi
dc="docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env"
WSWE_IMAGE="$image" $dc up -d --no-build --wait

cid="$(WSWE_IMAGE="$image" $dc ps -q app)"
run_id="$(docker inspect --format '{{.Image}}' "$cid")"
echo "running container image ID EXPECTED $want_id ACTUAL $run_id"
[ "$run_id" = "$want_id" ] || { echo "ERROR: app container is not running the expected image" >&2; exit 1; }
echo "$sha" > .deployed-sha

# Prune old wswe:<sha> images but keep the current and the previous release (rollback). Volumes are untouched.
prev=""; [ -f .previous-sha ] && prev="wswe:$(cat .previous-sha)"
for t in $(docker image ls wswe --format '{{.Repository}}:{{.Tag}}'); do
  case "$t" in "$image"|"$prev"|wswe:prod|wswe:\<none\>) continue ;; esac
  docker rmi "$t" || true
done
docker image prune -f
WSWE_IMAGE="$image" $dc ps
REMOTE
echo "==> Deployed $DEPLOY_SHA ($WSWE_IMAGE)"
