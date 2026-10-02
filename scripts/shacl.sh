#!/usr/bin/env bash
# Validate the generated data against shapes/football-shapes.ttl with Jena's `shacl validate`.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose run --rm --no-deps -e JVM_ARGS=-Xmx6g --entrypoint sh fuseki -c '
  cat /import/ontology/football.ttl /import/output/data/*.ttl > /tmp/all.ttl 2>/dev/null || true
  /jena/bin/shacl validate --shapes /import/shapes/football-shapes.ttl --data /tmp/all.ttl
'
