# Football Linked Open Data — Design Spec

Date: 2026-10-02

## 1. Goal and success criteria

Build a Linked Open Data application for the football domain as a course project (LOD 5-star scheme).

Deliverables:
1. An ontology (`ontology/football.ttl`), English only.
2. 4-star data: scoped Transfermarkt CSVs transformed to RDF (Turtle) with dereferenceable-style URIs.
3. 5-star data: `owl:sameAs` links to Wikidata, DBpedia and GeoNames.
4. A SPARQL endpoint (Apache Jena Fuseki) plus terminal querying via `curl` / script.
5. Validation: SHACL shapes and a set of competency queries.

Out of scope for this spec (later, separate cycle): the web UI for querying.

Source data: `datasets/*.csv` (Transfermarkt dump, 12 files, ~873 MB).

## 2. Data scope

Configured in `config.json` so scope can be widened later without code changes.

| Item | Scope |
|---|---|
| Competitions | GB1 (Premier League), ES1 (La Liga), IT1 (Serie A), L1 (Bundesliga), FR1 (Ligue 1), CL (Champions League), EL (Europa League), FIWC (World Cup) |
| Seasons | 2012–2025 (all seasons available in the source) for the club competitions; FIWC: all six editions present (season codes 2005, 2009, 2013, 2017, 2021, 2025 = World Cups 2006–2026). Seasons are configured per competition. |
| Games | ~30k club matches (29,740 for the seven club competitions) plus ~390 World Cup matches, selected from `games.csv` by competition and season |
| Clubs | Clubs appearing in selected games |
| Players | Players with an appearance in a selected game, plus players in `players.csv` whose `current_club_id` is a selected club |
| appearances, game_events | Filtered by selected `game_id` |
| transfers, player_valuations | Filtered by selected `player_id` |
| countries, national_teams, competitions | Kept in full (small) |
| Dropped | `club_games` (redundant with games), `game_lineups` (overlaps appearances) |

Measured input for the seven club competitions over 2012–2025: 29,740 games, 832k appearances, 418k game events. Coverage is even across seasons (nearly every game has appearances and events). Expected size: roughly 10–14 million triples (estimate; the build reports actual counts). If load time or size is a problem, narrow the seasons in `config.json`.

Known source limits (documented, not fixed):
- `appearances` for FIWC exist only for the 2026 edition; earlier editions have match results and events only.
- `transfers` contains future-dated rows (contract end dates).
- `transfer_fee = 0` does not distinguish free transfers from undisclosed fees.

## 3. Ontology

Namespaces (base URI is configurable):
- `fb:` = `https://example.org/football/ontology#`
- `fbr:` = `https://example.org/football/resource/`

### 3.1 Classes

```
fb:Team ─┬ fb:Club
         └ fb:NationalTeam
fb:Player        subClassOf foaf:Person, schema:Person
fb:Match         subClassOf schema:SportsEvent
fb:Competition   subClassOf schema:SportsOrganization
fb:Country, fb:Stadium, fb:Referee, fb:Manager
fb:Position      (SKOS concepts; sub_position is skos:narrower of position)
fb:MatchEvent ─┬ fb:Goal ├ fb:Card (yellow/red) └ fb:Substitution
fb:Appearance, fb:Transfer, fb:MarketValuation
```

### 3.2 URI scheme

Transfermarkt IDs are the keys, so URIs are stable and reproducible:
`fbr:player/10`, `fbr:club/398`, `fbr:national-team/3262`, `fbr:competition/GB1`, `fbr:country/189`, `fbr:match/2317258`, `fbr:appearance/{appearance_id}`, `fbr:event/{game_event_id}`.
Transfers have no ID column: `fbr:transfer/{hash(player_id, date, from_club_id, to_club_id)}`.
Valuations: `fbr:valuation/{player_id}-{date}`.

### 3.3 N-ary relations (reified nodes)

- **Appearance**: `fb:appearanceOf` (Player), `fb:inMatch`, `fb:forTeam`, `fb:goals`, `fb:assists`, `fb:minutesPlayed`, `fb:yellowCards`, `fb:redCards`.
- **Transfer**: `fb:transferOf` (Player), `fb:fromClub`, `fb:toClub`, `fb:transferDate`, `fb:transferFee` (xsd:decimal, emitted only when > 0), `fb:isFreeTransfer` only when it can be inferred, otherwise omitted.
- **MarketValuation**: `fb:valuationOf`, `fb:valueEUR`, `fb:valuationDate`, `fb:atClub`.
- **MatchEvent**: `fb:inMatch`, `fb:minute`, `fb:byPlayer`, `fb:forTeam`. Goal adds `fb:assistedBy`. Substitution adds `fb:playerIn` and `fb:playerOut`. Card reason is stored in `rdfs:comment`.

### 3.4 Direct shortcut properties

Object: `fb:playsFor` (Player → Club, current), `fb:citizenOf`, `fb:bornIn`, `fb:homeTeam`, `fb:awayTeam`, `fb:inCompetition`, `fb:inSeason`, `fb:hostedAt`, `fb:refereedBy`, `fb:country`.
Datatype: `fb:dateOfBirth` (xsd:date, functional), `fb:heightCm`, `fb:preferredFoot`, `fb:currentMarketValueEUR`, `fb:highestMarketValueEUR`, `fb:homeScore`, `fb:awayScore`, `fb:attendance`, `fb:stadiumSeats`, `fb:fifaRanking`, `fb:squadSize`, `fb:averageAge`, `fb:confederation`.

Common properties are declared `rdfs:subPropertyOf` the matching schema.org / foaf terms (name, birthDate, height).

### 3.5 Conventions

- Labels use `rdfs:label` with language tag `@en`, or `@und` for personal names.
- Null or empty source values produce no triple.
- Transfermarkt `url` is kept as `rdfs:seeAlso`.
- Every class and property has `rdfs:label`, `rdfs:comment`, and `domain`/`range` where meaningful.
- OWL axioms limited to: disjoint classes, inverse properties, `owl:FunctionalProperty`. This keeps lightweight reasoning possible.

## 4. Pipeline

```
Semantic Football Web/
├── datasets/                  source CSVs (unchanged)
├── config.json                base URI, competitions, seasons
├── ontology/football.ttl
├── src/
│   ├── select_scope.py        game_id / club_id / player_id sets
│   ├── build_rdf.py           CSV -> Turtle (streaming)
│   ├── link_wikidata.py       5-star links
│   └── validate.py            syntax, SHACL, counts
├── shapes/football-shapes.ttl
├── output/data/*.ttl          4-star data
├── output/links/*.ttl         5-star links
├── queries/*.rq               competency queries
├── scripts/query.sh           terminal SPARQL access
└── docker-compose.yml         Fuseki
```

Implementation uses the Python standard library `csv` module (pandas is not installed) and writes Turtle line by line. Whole tables are never loaded into memory. `rdflib` is used only to sample-validate small outputs.

### 4.1 select_scope.py

Filter `games.csv` by competition and season to get the `game_id` set. Derive club IDs from home/away clubs, and player IDs from `appearances` plus current-club membership. Write the sets to intermediate files for later steps.

### 4.2 build_rdf.py — mapping per table

| CSV | Output | Key handling |
|---|---|---|
| countries, national_teams, competitions | `reference.ttl` | Kept in full. Competition gets `fb:country` and `fb:confederation`. Country id `-1` (international) is skipped. |
| clubs | `clubs.ttl` | `net_transfer_record` (e.g. `+€5.90m`, `€-25.00m`) parsed to a number. `stadium_name` becomes an `fb:Stadium` node. |
| players | `players.ttl` | Trim strings (`"Opole  "`), `1978-06-09 00:00:00` to `xsd:date`, position and sub_position to SKOS concepts. |
| games | `matches.ttl` | home/away, score, referee, stadium, attendance, formation. |
| appearances | `appearances.ttl` | One `fb:Appearance` node per row. |
| game_events | `events.ttl` | Classified as Goal / Card / Substitution by the `type` column. |
| transfers | `transfers.ttl` | Hashed URI, fee rule from 3.3. |
| player_valuations | `valuations.ttl` | Only players in scope. |

Rules:
- One shared literal-escaping function (quotes, newlines, Unicode).
- A club referenced by a game but missing from `clubs.csv` becomes a minimal `fb:Club` with its label taken from `home_club_name` / `away_club_name`.
- `players.name` is the canonical label even when `appearances.player_name` differs.
- At the end the build prints triples per file and the number of dropped rows with reasons.

### 4.3 link_wikidata.py — 5-star

1. Query the Wikidata SPARQL endpoint once per entity type for pairs `(item, Transfermarkt ID)`. Candidate properties: player `P2446`, club `P7223`; national team, competition and manager properties are found the same way. All property IDs must be verified against Wikidata at implementation time.
2. Join on the Transfermarkt ID (exact match, no fuzzy name matching) and emit `owl:sameAs <http://www.wikidata.org/entity/Q...>` into `links/wikidata.ttl`.
3. From Wikidata, get the English sitelink to emit `owl:sameAs` to DBpedia, and the GeoNames ID for countries (`P1566`).
4. Stadiums are matched by name and club; these links are lower precision and carry `fb:linkConfidence`.
5. Downloaded results are cached as JSON, so reruns need no network.
6. A report gives the link rate per entity type. Entities without a Wikidata match stay unlinked.

### 4.4 Endpoint

Docker Compose runs Apache Jena Fuseki with TDB2. The ontology, data and links are loaded with `tdb2.tdbloader`. Dataset endpoint: `/football/sparql`. Fuseki's built-in UI is available for interactive queries. `scripts/query.sh <file.rq>` queries it from the terminal using `curl`.

## 5. Validation

- Syntax: each Turtle file is parsed (`rdflib` for small samples, Jena `riot --validate` for large files).
- SHACL (`shapes/football-shapes.ttl`), core constraints only: every Match has exactly one home team and one away team; every Appearance references an existing Player and Match; dates are valid.
- Competency queries (8–10, in `queries/`), including:
  - Top 10 scorers of the 2023 Premier League season.
  - Most expensive transfers across the scoped leagues.
  - World Cup 2026 players and their clubs.
  - A federated query using `SERVICE <https://query.wikidata.org/sparql>` to fetch data (for example birth place or image) for Wikidata-linked players, demonstrating the value of 5-star links.

## 6. Risks

| Risk | Handling |
|---|---|
| IDs or names differ between tables | `players.name` is the canonical label; unresolved references are logged. |
| Club referenced but absent from `clubs.csv` | Minimal club node (see 4.2). |
| Wikidata rate limits | Batched queries and a local cache. |
| Source property IDs for Wikidata may be wrong | Verified at implementation time, not assumed. |
| Output larger than estimated | `config.json` scope can be narrowed (for example back to 2018–2025). |
| More players in scope means more Wikidata links to verify | Link report per entity type; cache results locally. |

## 6a. Addendum (decisions made while planning)

Details the spec left open (Season nodes, penalty-shootout events, country-name resolution, club scope expansion, stadium links as `skos:closeMatch` instead of a confidence property, competition links via `P12758`) are recorded in the "Decisions made in this plan" section of `docs/superpowers/plans/2026-10-02-football-lod.md`. Where the two differ, the plan's decision wins.

## 7. Out of scope

- Web UI (separate later cycle).
- `game_lineups` and `club_games`.
- Fuzzy name matching for player or club links.
- Heavy OWL reasoning.
