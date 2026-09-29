#!/bin/sh
set -eu

BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/multiplekser}"
MAX_AGE_SECONDS="${BACKUP_MAX_AGE_SECONDS:-129600}"  # 36 h
LAST_SUCCESS="$BACKUP_ROOT/LAST_SUCCESS"

if [ ! -f "$LAST_SUCCESS" ]; then
    echo "BRAK LAST_SUCCESS" >&2
    exit 1
fi

LAST_TIMESTAMP="$(cat "$LAST_SUCCESS")"
NOW="$(date +%s)"
LAST_MTIME="$(stat -c %Y "$LAST_SUCCESS")"
AGE="$((NOW - LAST_MTIME))"

if [ "$AGE" -gt "$MAX_AGE_SECONDS" ]; then
    echo "Backup jest za stary: age=${AGE}s, max=${MAX_AGE_SECONDS}s" >&2
    exit 1
fi

DB="$BACKUP_ROOT/database/postgres-$LAST_TIMESTAMP.dump"
MINIO="$BACKUP_ROOT/minio/minio-$LAST_TIMESTAMP.tar.gz"
MANIFEST="$BACKUP_ROOT/manifests/backup-$LAST_TIMESTAMP.sha256"

for file in "$DB" "$MINIO" "$MANIFEST"; do
    if [ ! -s "$file" ]; then
        echo "Brak lub pusty plik backupu: $file" >&2
        exit 1
    fi
done

sha256sum -c "$MANIFEST" >/dev/null
tar -tzf "$MINIO" >/dev/null

echo "Backup Multipleksera zdrowy: $LAST_TIMESTAMP, wiek=${AGE}s"
