#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
POSTGRES_DB="${POSTGRES_DB:-flow_monitor}"
POSTGRES_USER="${POSTGRES_USER:-flow_user}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-flow-postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

timestamp="$(date +%Y%m%d-%H%M%S)"
output="$BACKUP_DIR/${POSTGRES_DB}-${timestamp}.dump"

docker exec "$POSTGRES_CONTAINER" pg_dump \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -Fc > "$output"

echo "Wrote $output"

if [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] && [ "$RETENTION_DAYS" -gt 0 ]; then
  find "$BACKUP_DIR" -type f -name "${POSTGRES_DB}-*.dump" -mtime +"$RETENTION_DAYS" -print -delete
fi
