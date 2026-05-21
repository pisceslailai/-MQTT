#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

pass() {
  echo "OK: $*"
}

contains() {
  local pattern="$1"
  local file="$2"
  if command -v rg >/dev/null 2>&1; then
    rg -q "$pattern" "$file"
  else
    grep -Eq "$pattern" "$file"
  fi
}

if [ ! -f "$ENV_FILE" ]; then
  fail "Missing $ENV_FILE. Run: cp .env.example .env"
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

required_vars=(
  POSTGRES_PASSWORD
  EMQX_DASHBOARD_PASSWORD
  MQTT_USERNAME
  MQTT_PASSWORD
  MQTT_GATEWAY_USERNAME
  MQTT_GATEWAY_PASSWORD
  CORS_ORIGINS
)

for name in "${required_vars[@]}"; do
  value="${!name:-}"
  [ -n "$value" ] || fail "$name is empty"
  [[ "$value" != change-this-* ]] || fail "$name still uses the example value"
done

[ "${CORS_ORIGINS:-}" != "*" ] || fail "CORS_ORIGINS must be the production origin, not *"
[ -f deploy/nginx/.htpasswd ] || fail "Missing deploy/nginx/.htpasswd. Run: bash scripts/generate_htpasswd.sh admin"
[ -f deploy/emqx/auth-built-in-db-bootstrap.csv ] || fail "Missing deploy/emqx/auth-built-in-db-bootstrap.csv. Run: bash scripts/generate_emqx_auth_bootstrap.sh"
pass "required secrets and generated files exist"

docker compose -f docker-compose.prod.yml config >/tmp/flow-monitor-prod-compose.yml
pass "docker-compose.prod.yml renders"

if contains 'published: "5432"|published: "8000"' /tmp/flow-monitor-prod-compose.yml; then
  fail "production compose exposes PostgreSQL or backend port"
fi
contains 'published: "80"' /tmp/flow-monitor-prod-compose.yml || fail "production compose does not expose 80"
contains 'published: "1883"' /tmp/flow-monitor-prod-compose.yml || fail "production compose does not expose 1883"
contains 'host_ip: 127.0.0.1' /tmp/flow-monitor-prod-compose.yml || fail "EMQX dashboard is not bound to 127.0.0.1"
pass "production port exposure is constrained"

docker run --rm \
  --add-host backend:127.0.0.1 \
  -v "$PWD/deploy/nginx/prod.conf:/etc/nginx/conf.d/default.conf:ro" \
  -v "$PWD/deploy/nginx/.htpasswd:/etc/nginx/.htpasswd:ro" \
  nginx:1.27-alpine nginx -t >/tmp/flow-monitor-nginx-check.log 2>&1 \
  || { cat /tmp/flow-monitor-nginx-check.log >&2; fail "nginx production config failed"; }
pass "nginx production config is valid"

docker run --rm \
  -e EMQX_ALLOW_ANONYMOUS=false \
  -e 'EMQX_AUTHENTICATION__1={mechanism="password_based",backend="built_in_database",user_id_type="username",password_hash_algorithm={name="sha256",salt_position="suffix"},bootstrap_file="/opt/emqx/etc/auth-built-in-db-bootstrap.csv",bootstrap_type="plain"}' \
  -v "$PWD/deploy/emqx/auth-built-in-db-bootstrap.csv:/opt/emqx/etc/auth-built-in-db-bootstrap.csv:ro" \
  emqx/emqx:5.8.4 /opt/emqx/bin/emqx check_config >/tmp/flow-monitor-emqx-check.log 2>&1 \
  || { cat /tmp/flow-monitor-emqx-check.log >&2; fail "emqx production authentication config failed"; }
pass "emqx production authentication config is valid"

echo "Production readiness checks passed."
