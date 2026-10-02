#!/usr/bin/env bash
# (Re)load ontology, data and links into a fresh TDB2 store, then start Fuseki.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose down -v
docker compose build
docker compose run --rm --no-deps -e JVM_ARGS=-Xmx4g --entrypoint sh fuseki -c '
  /jena/bin/tdb2.tdbloader --loc /data/tdb \
    /import/ontology/football.ttl \
    /import/output/data/*.ttl \
    /import/output/links/*.ttl
'
docker compose up -d
echo "Waiting for Fuseki..."
for i in $(seq 1 60); do
  curl -sf http://localhost:3030/$/ping >/dev/null && break
  sleep 2
done
echo "Endpoint: http://localhost:3030/football/sparql   UI: http://localhost:3030/"
