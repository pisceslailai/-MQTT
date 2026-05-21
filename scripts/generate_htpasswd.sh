#!/usr/bin/env bash
set -euo pipefail

USER_NAME="${1:-admin}"
OUTPUT_PATH="${OUTPUT_PATH:-deploy/nginx/.htpasswd}"

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"
read -r -s -p "Password for ${USER_NAME}: " password
echo

hash="$(openssl passwd -apr1 "$password")"
printf '%s:%s\n' "$USER_NAME" "$hash" > "$OUTPUT_PATH"
chmod 644 "$OUTPUT_PATH"
echo "Wrote $OUTPUT_PATH"
