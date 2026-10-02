#!/usr/bin/env bash
# Usage: scripts/query.sh queries/q01_top_scorers_pl_2023.rq [accept-mime]
set -euo pipefail
ENDPOINT="${SPARQL_ENDPOINT:-http://localhost:3030/football/sparql}"
ACCEPT="${2:-text/csv}"
curl -sS --fail-with-body -H "Accept: ${ACCEPT}" --data-urlencode "query@${1}" "${ENDPOINT}"
