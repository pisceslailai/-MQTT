#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
OUTPUT_PATH="${OUTPUT_PATH:-deploy/emqx/auth-built-in-db-bootstrap.csv}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE. Run: cp .env.example .env" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

MQTT_USERNAME="${MQTT_USERNAME:-flow_backend}"
MQTT_GATEWAY_USERNAME="${MQTT_GATEWAY_USERNAME:-gateway}"

required_vars=(
  MQTT_USERNAME
  MQTT_PASSWORD
  MQTT_GATEWAY_USERNAME
  MQTT_GATEWAY_PASSWORD
)

for name in "${required_vars[@]}"; do
  value="${!name:-}"
  if [ -z "$value" ]; then
    echo "Missing $name in $ENV_FILE" >&2
    exit 1
  fi
  if [[ "$value" == change-this-* ]]; then
    echo "$name still uses the example password in $ENV_FILE" >&2
    exit 1
  fi
done

mkdir -p "$(dirname "$OUTPUT_PATH")"
{
  printf 'user_id,password,is_superuser\n'
  printf '%s,%s,false\n' "$MQTT_USERNAME" "$MQTT_PASSWORD"
  printf '%s,%s,false\n' "$MQTT_GATEWAY_USERNAME" "$MQTT_GATEWAY_PASSWORD"
} > "$OUTPUT_PATH"
chmod 600 "$OUTPUT_PATH"
echo "Wrote $OUTPUT_PATH"
