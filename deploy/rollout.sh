#!/bin/sh
# Zero-downtime rollout of the `app` service on the single-VPS stack (see deploy/README.md, "Zero-downtime rollouts").
#
# Run from anywhere; operates on the repo this script lives in. The new image is selected like for compose:
#   WSWE_IMAGE=wswe:<sha> sh deploy/rollout.sh
# Steps: db up (idempotent) -> caddy up + `caddy reload` (picks up a changed Caddyfile without a restart) ->
# start the NEW app container next to the old one -> wait until it is healthy -> stop (graceful) and remove the old
# one(s) -> assert exactly one app container is left. If the new container does not become healthy it alone is removed,
# the old one keeps serving and the script exits non-zero.
#
# Optional env: DEPLOY_DRY_RUN=1 (print the plan only), ROLLOUT_TIMEOUT (seconds to wait for healthy, default 120),
# ROLLOUT_SETTLE (seconds to let Caddy discover the new container before the old one is stopped, default 3),
# ROLLOUT_COMPOSE_FILE / ROLLOUT_ENV_FILE / ROLLOUT_PROJECT (overrides, used by the local test stack),
# ROLLOUT_CADDY_RELOAD=0 (skip the caddy step).
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
compose_file="${ROLLOUT_COMPOSE_FILE:-deploy/docker-compose.prod.yml}"
env_file="${ROLLOUT_ENV_FILE:-deploy/.env}"
timeout="${ROLLOUT_TIMEOUT:-120}"
settle="${ROLLOUT_SETTLE:-3}"
dry="${DEPLOY_DRY_RUN:-0}"

dc() {
  if [ -n "${ROLLOUT_PROJECT:-}" ]; then
    docker compose -p "$ROLLOUT_PROJECT" -f "$compose_file" --env-file "$env_file" "$@"
  else
    docker compose -f "$compose_file" --env-file "$env_file" "$@"
  fi
}

if [ "$dry" = 1 ]; then
  cat <<PLAN
[dry-run] would: dc up -d --no-build --wait db
[dry-run]        dc up -d --no-build --no-deps caddy && dc exec -T caddy caddy reload --config /etc/caddy/Caddyfile
[dry-run]        no app container yet: dc up -d --no-build --no-deps --wait app
[dry-run]        else: dc up -d --no-build --no-deps --no-recreate --scale app=<n+1> app (new container next to the old)
[dry-run]              wait (max ${timeout}s) until the new container is healthy; on failure remove only it and exit 1
[dry-run]              docker stop + docker rm the old container(s); assert exactly one app container remains
PLAN
  exit 0
fi

ids() { dc ps -a -q app; }
# container ids in $1 that are not in $2 (both newline separated)
minus() { printf '%s\n' "$1" | while read -r a; do [ -z "$a" ] && continue; printf '%s\n' "$2" | grep -qxF "$a" || echo "$a"; done; }

echo "==> rollout: database"
dc up -d --no-build --wait db

if [ "${ROLLOUT_CADDY_RELOAD:-1}" = 1 ]; then
  echo "==> rollout: caddy (start if needed, reload config in place)"
  dc up -d --no-build --no-deps caddy
  dc exec -T caddy caddy reload --config /etc/caddy/Caddyfile
fi

old="$(ids)"
n="$(printf '%s\n' "$old" | grep -c . || true)"
if [ "$n" -eq 0 ]; then
  echo "==> rollout: no app container yet (first deploy): plain start"
  dc up -d --no-build --no-deps --wait app
  new="$(ids)"
else
  echo "==> rollout: $n old app container(s): $(echo $old); starting the new one next to it"
  # --no-recreate: the old container keeps running untouched; the extra replica is created from the NEW config/image.
  dc up -d --no-build --no-deps --no-recreate --scale app=$((n + 1)) app
  new="$(minus "$(ids)" "$old")"
  [ "$(printf '%s\n' "$new" | grep -c .)" -eq 1 ] || { echo "ERROR: expected exactly one new app container, got: $new" >&2; exit 1; }
  echo "==> rollout: new container $new; waiting up to ${timeout}s for it to become healthy"
  i=0
  while :; do
    state="$(docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}nohealth{{end}}' "$new")"
    case "$state" in
      "running healthy") break ;;
      "running starting") ;;
      *) echo "ERROR: new app container is '$state'" >&2; i=$timeout ;;
    esac
    if [ "$i" -ge "$timeout" ]; then
      echo "ERROR: new app container did not become healthy; removing it, the old one keeps serving. Logs:" >&2
      docker logs --tail 40 "$new" >&2 || true
      docker rm -f "$new" >/dev/null || true
      exit 1
    fi
    i=$((i + 1))
    sleep 1
  done
  echo "==> rollout: new container is healthy after ~${i}s; letting Caddy discover it (${settle}s)"
  sleep "$settle"
  echo "==> rollout: stopping old container(s) (graceful, compose stop grace period)"
  # shellcheck disable=SC2086  # ids are plain hex words
  docker stop $old >/dev/null
  # shellcheck disable=SC2086
  docker rm $old >/dev/null
fi

left="$(ids)"
[ "$(printf '%s\n' "$left" | grep -c .)" -eq 1 ] || { echo "ERROR: expected exactly one app container after the rollout, got: $left" >&2; exit 1; }
echo "==> rollout done: app container $(docker inspect --format '{{.Name}} {{.Image}}' "$left")"
