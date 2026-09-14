#!/usr/bin/env bash
# Nightly logical backup of managed Postgres → Cloudflare R2 via rclone.
# Intended to run on the VPS (cron) or as a scheduled GitHub Action with network access to the DB.
#
# Prerequisites:
#   - pg_dump matching the server major version
#   - rclone configured (see infra/scripts/rclone.conf.example)
#   - env: DATABASE_URL, BACKUP_RCLONE_REMOTE (e.g. r2:renzy-backups), BACKUP_RETENTION_DAYS (default 30)
#
# Example cron (02:15 UTC):
#   15 2 * * * cd /opt/renzy && set -a && . infra/.env && set +a && infra/scripts/backup-pg.sh >> /var/log/renzy-backup.log 2>&1

set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
REMOTE="${BACKUP_RCLONE_REMOTE:-r2:renzy-backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

DUMP="$TMP/renzy-${STAMP}.dump"
echo "backing up to $DUMP"

# Custom format: parallel restore-friendly, compressed.
pg_dump --format=custom --no-owner --no-acl --file="$DUMP" "$DATABASE_URL"

REMOTE_PATH="${REMOTE%/}/postgres/renzy-${STAMP}.dump"
echo "uploading to $REMOTE_PATH"
rclone copyto "$DUMP" "$REMOTE_PATH"

echo "pruning dumps older than ${RETENTION_DAYS} days on ${REMOTE%/}/postgres/"
rclone delete "${REMOTE%/}/postgres/" --min-age "${RETENTION_DAYS}d" || true

echo "backup ok: $REMOTE_PATH"
