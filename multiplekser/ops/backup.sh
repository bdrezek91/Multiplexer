#!/bin/sh
set -eu

# Multiplekser: spójna kopia PostgreSQL + logiczna kopia obiektów MinIO.
# Nie zatrzymuje aplikacji. Sekrety nie są zapisywane do backupu.
#
# Zmienne opcjonalne:
#   BACKUP_ROOT=/var/backups/multiplekser
#   RETENTION_DAYS=14

umask 077

PROJECT_DIR="/root/Multiplexer/multiplekser"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/multiplekser}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

DB_DIR="$BACKUP_ROOT/database"
MINIO_DIR="$BACKUP_ROOT/minio"
MANIFEST_DIR="$BACKUP_ROOT/manifests"
WORK_DIR="$BACKUP_ROOT/.work-$TIMESTAMP"
LAST_SUCCESS="$BACKUP_ROOT/LAST_SUCCESS"

mkdir -p "$DB_DIR" "$MINIO_DIR" "$MANIFEST_DIR" "$WORK_DIR"
chmod 700 "$BACKUP_ROOT" "$DB_DIR" "$MINIO_DIR" "$MANIFEST_DIR" "$WORK_DIR"

# Nie uruchamiaj dwóch backupów równocześnie.
LOCK_FILE="/run/lock/multiplekser-backup.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "Backup Multipleksera już działa - pomijam." >&2
    exit 0
fi

cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT INT TERM

cd "$PROJECT_DIR"

DB_TMP="$WORK_DIR/postgres-$TIMESTAMP.dump"
DB_FINAL="$DB_DIR/postgres-$TIMESTAMP.dump"
MINIO_STAGE="$WORK_DIR/minio"
MINIO_TMP="$WORK_DIR/minio-$TIMESTAMP.tar.gz"
MINIO_FINAL="$MINIO_DIR/minio-$TIMESTAMP.tar.gz"
MANIFEST_TMP="$WORK_DIR/backup-$TIMESTAMP.sha256"
MANIFEST_FINAL="$MANIFEST_DIR/backup-$TIMESTAMP.sha256"

echo "[$TIMESTAMP] Backup PostgreSQL..."
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -lc \
    'pg_dump --format=custom --no-owner --no-acl -U "$POSTGRES_USER" "$POSTGRES_DB"' \
    > "$DB_TMP"

# Weryfikacja formatu dumpa przed publikacją backupu.
docker compose -f "$COMPOSE_FILE" exec -T postgres pg_restore --list < "$DB_TMP" >/dev/null

echo "[$TIMESTAMP] Backup MinIO przez API S3..."
BUCKET="$(docker compose -f "$COMPOSE_FILE" exec -T backend python -c 'from app.core.config import settings; print(settings.minio_bucket)' | tr -d '\r\n')"
if [ -z "$BUCKET" ]; then
    echo "Nie udało się ustalić nazwy bucketa MinIO." >&2
    exit 1
fi

MINIO_CID="$(docker compose -f "$COMPOSE_FILE" ps -q minio)"
if [ -z "$MINIO_CID" ]; then
    echo "Kontener MinIO nie działa." >&2
    exit 1
fi

REMOTE_TMP="/tmp/multiplekser-backup-$TIMESTAMP"
docker compose -f "$COMPOSE_FILE" exec -T minio sh -lc \
    'rm -rf "$1" && mkdir -p "$1" && mc alias set backupsrc http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc mirror --quiet "backupsrc/$2" "$1" >/dev/null' \
    sh "$REMOTE_TMP" "$BUCKET"

mkdir -p "$MINIO_STAGE"
docker cp "$MINIO_CID:$REMOTE_TMP/." "$MINIO_STAGE/" >/dev/null
docker compose -f "$COMPOSE_FILE" exec -T minio sh -lc 'rm -rf "$1"' sh "$REMOTE_TMP"

tar -C "$MINIO_STAGE" -czf "$MINIO_TMP" .
tar -tzf "$MINIO_TMP" >/dev/null

# Manifest integralności obu artefaktów.
sha256sum "$DB_TMP" "$MINIO_TMP" > "$MANIFEST_TMP"

# Dopiero po pełnej weryfikacji publikujemy pliki pod finalnymi nazwami.
mv "$DB_TMP" "$DB_FINAL"
mv "$MINIO_TMP" "$MINIO_FINAL"
sed \
    -e "s#$WORK_DIR/postgres-$TIMESTAMP.dump#$DB_FINAL#" \
    -e "s#$WORK_DIR/minio-$TIMESTAMP.tar.gz#$MINIO_FINAL#" \
    "$MANIFEST_TMP" > "$MANIFEST_FINAL"

printf '%s\n' "$TIMESTAMP" > "$LAST_SUCCESS"
chmod 600 "$DB_FINAL" "$MINIO_FINAL" "$MANIFEST_FINAL" "$LAST_SUCCESS"

# Retencja wyłącznie plików tworzonych przez ten skrypt.
find "$DB_DIR" -maxdepth 1 -type f -name 'postgres-*.dump' -mtime "+$RETENTION_DAYS" -delete
find "$MINIO_DIR" -maxdepth 1 -type f -name 'minio-*.tar.gz' -mtime "+$RETENTION_DAYS" -delete
find "$MANIFEST_DIR" -maxdepth 1 -type f -name 'backup-*.sha256' -mtime "+$RETENTION_DAYS" -delete

DB_SIZE="$(du -h "$DB_FINAL" | awk '{print $1}')"
MINIO_SIZE="$(du -h "$MINIO_FINAL" | awk '{print $1}')"
OBJECTS="$(find "$MINIO_STAGE" -type f | wc -l | tr -d ' ')"

echo "Backup Multipleksera OK: PostgreSQL=$DB_SIZE, MinIO=$MINIO_SIZE, obiekty=$OBJECTS, timestamp=$TIMESTAMP"
