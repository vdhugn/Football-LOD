#!/usr/bin/env bash
# Runs every queries/checks/*.rq; exits 1 if any count is above zero.
set -uo pipefail
cd "$(dirname "$0")/.."
bad=0
for q in queries/checks/*.rq; do
  n=$(scripts/query.sh "$q" | tail -n 1 | tr -d '\r')
  echo "$(basename "$q"): $n"
  if [ "$n" != "0" ]; then bad=1; fi
done
exit $bad
