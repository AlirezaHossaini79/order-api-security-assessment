#!/bin/sh
# Preserves the existing project and its volume. Run from the lab directory.
set -eu
project="${1:-lab}"
python3 tools/setup_secrets.py
docker compose -p "$project" config --quiet
docker compose -p "$project" build api
docker compose -p "$project" stop api
docker compose -p "$project" up -d db
attempt=0
until docker compose -p "$project" exec -T db pg_isready -U lab -d lab >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  [ "$attempt" -lt 40 ] || exit 1
  sleep 1
done
docker compose -p "$project" exec -T db sh /docker-entrypoint-initdb.d/10-lab.sh
docker compose -p "$project" up -d --no-deps api
python3 tools/smoke.py
