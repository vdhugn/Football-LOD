# Football Linked Open Data

Transfermarkt CSVs → football ontology → 4-star RDF → 5-star links (Wikidata, DBpedia, GeoNames) → Fuseki SPARQL endpoint.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
make all            # tests, scope, build, vocabulary check, links, Fuseki load, checks
```

Requires Python 3.12, Docker and network access (the Fuseki image downloads Apache Jena; linking calls Wikidata).
The CSVs go in `datasets/` (git-ignored).

- Endpoint: <http://localhost:3030/football/sparql> (web UI at <http://localhost:3030/>)
- Terminal: `scripts/query.sh queries/q01_top_scorers_pl_2023.rq` (CSV by default; pass a MIME type as 2nd argument for other formats)

## Scope

GB1, ES1, IT1, L1, FR1, CL and EL for seasons 2012–2025; FIWC (all six World Cups in the source). Edit `config.json` to narrow or widen it.
`game_lineups.csv` and `club_games.csv` are not used.

## Results of the last run

- Data: 14,180,422 triples (appearances 7.5M, events 3.1M, valuations 2.0M, transfers 0.6M, matches 0.48M, players 0.44M); Fuseki holds 14,232,449 triples including ontology and links.
- In scope: 30,132 games, 25,482 players, 10,671 clubs (791 of them described in `clubs.csv`, the rest are minimal nodes from transfer history), 135 national teams.
- Links (`output/links/report.json`):
  players 23,287 of 25,482 (91.4%), national teams 135 of 135, competitions 8 of 8,
  clubs listed in `clubs.csv` 753 of 791 (95.2%; 26.2% of all clubs because of the minimal nodes),
  countries 167 of 208 names (80.3%), stadiums 261 of 760 (`skos:closeMatch`).
  Only unambiguous one-to-one Transfermarkt-ID / Wikidata-item pairs become links; 24 clubs with ambiguous IDs are skipped (see `ambiguous` in `report.json`).
- Validation: ontology vocabulary check OK; SHACL on the full data `sh:conforms true`; all five dangling-reference checks return 0; 60 unit tests pass.
- Build is deterministic (two runs are byte-identical); relinking runs offline from `.cache/wikidata/` in under a second.

## Layout

| Path | Purpose |
|---|---|
| `ontology/football.ttl` | ontology (English only) |
| `src/` | scope selection, builders, Wikidata linking, vocabulary check |
| `shapes/football-shapes.ttl` | SHACL shapes |
| `queries/` | nine competency queries; `queries/checks/` has dangling-reference checks |
| `scripts/` | `load.sh` (load + start Fuseki), `query.sh`, `run_checks.sh`, `shacl.sh` |
| `docker/`, `docker-compose.yml` | Apache Jena Fuseki 5.5.0 with TDB2 |
| `docs/superpowers/` | design spec and implementation plan, including the decisions made while planning |

## Known limits of the source data

- World Cup appearances exist only for the 2026 edition; earlier editions have results and events only.
- `transfer_fee` empty and `0` cannot be told apart, so no fee triple is written unless the fee is positive. Future-dated transfers (contract ends) exist in the source.
- Many older players have no transfer history, so some transfer queries return few or no rows.
- Stadium links are lower precision than the other links and use `skos:closeMatch`.
- Managers are modelled as nodes keyed by name and are not linked externally.

## Not yet built

A web UI for querying (planned as a separate cycle).
