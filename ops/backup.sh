#!/usr/bin/env bash
# Nightly Postgres dump. The review log is the irreplaceable part of this app.
# cron:  15 3 * * *  /path/to/bhasha/ops/backup.sh /srv/backups/bhasha
set -euo pipefail
cd "$(dirname "$0")/.."
dest="${1:-./backups}"
keep="${KEEP_DAYS:-30}"
mkdir -p "$dest"
file="$dest/bhasha-$(date +%F).sql.gz"
docker compose exec -T db pg_dump -U bhasha -d bhasha --no-owner | gzip > "$file.tmp"
mv "$file.tmp" "$file"
find "$dest" -name 'bhasha-*.sql.gz' -mtime +"$keep" -delete
echo "wrote $file"
