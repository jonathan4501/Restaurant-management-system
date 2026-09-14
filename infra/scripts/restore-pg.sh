#!/usr/bin/env bash
# Restore a pg_dump custom-format file into a target DATABASE_URL (scratch or disaster recovery).
#
# Usage:
#   DATABASE_URL=postgres://… ./infra/scripts/restore-pg.sh /path/to/renzy-….dump
#   DATABASE_URL=postgres://… ./infra/scripts/restore-pg.sh r2:renzy-backups/postgres/renzy-….dump
#
# If the argument looks like an rclone remote path, it is downloaded first.

set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${1:?usage: restore-pg.sh <dump-file-or-rclone-remote>}"

SRC="$1"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if [[ "$SRC" == *:*/* ]] && [[ ! -f "$SRC" ]]; then
  echo "downloading $SRC"
  rclone copyto "$SRC" "$TMP/restore.dump"
  SRC="$TMP/restore.dump"
fi

echo "restoring $SRC into DATABASE_URL"
# Drop and recreate public schema objects carefully — for scratch DBs only.
# Production disaster recovery: restore into a new database, then swap connection strings.
pg_restore --clean --if-exists --no-owner --no-acl --dbname="$DATABASE_URL" "$SRC"

echo "restore ok"
