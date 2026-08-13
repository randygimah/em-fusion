#!/usr/bin/env bash
# Smoke-test a running EM Fusion stack (`make up` or `make demo` first).
# Checks the backend health endpoint directly, the frontend through nginx, and
# the /api/ proxy path the frontend uses to reach the backend.
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:8080}"
RETRIES="${RETRIES:-20}"
SLEEP_SECONDS="${SLEEP_SECONDS:-3}"

fail() {
	echo "FAIL: $1" >&2
	exit 1
}

wait_for() {
	local name="$1" url="$2" attempt=1
	while [ "$attempt" -le "$RETRIES" ]; do
		if curl -fsS -o /dev/null "$url"; then
			echo "ok: $name ($url)"
			return 0
		fi
		printf 'waiting for %s (%d/%d)\n' "$name" "$attempt" "$RETRIES"
		sleep "$SLEEP_SECONDS"
		attempt=$((attempt + 1))
	done
	fail "$name did not become healthy at $url"
}

wait_for "backend health" "$BACKEND_URL/api/v1/health"
wait_for "frontend" "$FRONTEND_URL/"
# The proxy must forward /api/v1 intact. A trailing slash on nginx's proxy_pass
# would strip the prefix and 404 here while both services report healthy.
wait_for "frontend -> backend proxy" "$FRONTEND_URL/api/v1/health"

body="$(curl -fsS "$BACKEND_URL/api/v1/health")"
case "$body" in
*'"status"'*'"healthy"'*) echo "ok: backend reports healthy" ;;
*) fail "unexpected /health payload: $body" ;;
esac

echo "Smoke test passed."
