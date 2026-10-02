# Football LOD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the scoped Transfermarkt CSVs into a football ontology plus 4-star RDF data and 5-star Wikidata/DBpedia/GeoNames links, served through a Fuseki SPARQL endpoint with SHACL and competency-query validation.

**Architecture:** Plain Python 3.12 scripts stream CSVs (stdlib `csv`) and write Turtle line by line. `select_scope.py` computes the in-scope game/club/player ID sets once and caches them; one builder module per table family turns CSV rows into Turtle. `link_wikidata.py` joins on Transfermarkt IDs (exact match) via batched, cached Wikidata SPARQL queries. Apache Jena Fuseki (TDB2, in Docker) loads ontology, data and links.

**Tech Stack:** Python 3.12 (stdlib + `rdflib`, `pyshacl`, `pytest`), Apache Jena/Fuseki 5.5.0 in Docker, SPARQL 1.1.

**Spec:** `docs/superpowers/specs/2026-10-02-football-lod-design.md` (read it first; this plan also records a few decisions the spec left open in the "Decisions made in this plan" section below).

## Global Constraints

- Ontology is English only; namespaces `fb:` = `https://example.org/football/ontology#`, resource base `https://example.org/football/resource/` (both read from `config.json`, never hard-coded in `src/`).
- Source data: `datasets/*.csv`; never modify them. Do not use pandas (not installed); use stdlib `csv` and stream; never load the large tables (`appearances`, `game_events`, `player_valuations`, `transfers`) into memory.
- Scope: GB1, ES1, IT1, L1, FR1, CL, EL for seasons 2012–2025; FIWC for season codes 2005, 2009, 2013, 2017, 2021, 2025. `game_lineups.csv` and `club_games.csv` are not used.
- Resource URIs use Transfermarkt IDs: `player/10`, `club/398`, `national-team/3262`, `competition/GB1`, `country/189`, `match/2317258`, `appearance/{appearance_id}`, `event/{game_event_id}`, `transfer/{hash}`, `valuation/{player_id}-{date}`.
- Null/empty source cells produce no triple. Dates are `xsd:date`; strings are trimmed.
- Names use `@und` language tags; country and position labels use `@en`.
- `transfer_fee` is emitted only when > 0 (empty and `0.000` carry no usable information); no `isFreeTransfer` triple is ever emitted.
- Wikidata property IDs (verified live on 2026-10-02): player `P2446`, team `P7223` (clubs and national teams), competition `P12758`, GeoNames ID `P1566`, home venue `P115`.
- Wikidata requests need a descriptive `User-Agent`, batching, a 1-second pause between requests, and an on-disk cache so reruns work offline.
- Output Turtle uses full IRIs (`<https://...>`) for resources, because `/` is not legal in unescaped prefixed local names.

## Decisions made in this plan (spec addendum)

1. **Season nodes:** `fb:Season` with URI `season/{year}` (start year of the source `season` code), `fb:startYear`, `rdfs:label "Season 2023"`; `fb:inSeason` points to it.
2. **Penalty shootouts:** `game_events.type = Shootout` becomes `fb:PenaltyShootoutKick` (subclass of `fb:MatchEvent`) with `fb:scored` boolean.
3. **Countries from names:** `players.csv` gives country *names*, not IDs. Names matching `countries.csv` (after the alias `Turkey` → `Türkiye`) reuse `country/{id}`; the rest get a minimal `fb:Country` at `country/n-{name}`.
4. **Club scope:** `club_ids` = clubs in selected games ∪ clubs referenced by in-scope players' transfers, valuations and current club. Clubs missing from `clubs.csv` become minimal `fb:Club` nodes labelled from the names seen in other tables. National teams missing from `national_teams.csv` likewise.
5. **Players:** in-scope players missing from `players.csv` become minimal `fb:Player` nodes so references never dangle.
6. **Stadium links:** matched through the linked club's Wikidata home venue (`P115`) by case-folded name; emitted as `skos:closeMatch` (weaker than `owl:sameAs`) instead of a `fb:linkConfidence` property.
7. **Competition links:** exact join on `P12758` (competition ID string such as `GB1`).
8. **Managers:** `fb:Manager` nodes keyed by name slug (no ID in the data) are *not* linked externally.
9. **SHACL at scale:** pyshacl validates a fixture-sized graph in unit tests; full data is validated with Jena's `shacl validate` CLI plus SPARQL "dangling reference" count queries against Fuseki.

## Review Focus

1. Names containing quotes, backslashes, newlines or non-ASCII characters (`O"Brien`, `Türkiye`) must still yield valid Turtle with the exact value round-tripping (Task 2).
2. Empty-string and missing CSV cells must produce no triple and no crash (Tasks 6, 7, 8).
3. Transfer fee `""` vs `0.000` vs a positive value must never yield a `fb:transferFee` of 0 (Task 9).
4. Games referencing clubs or national teams absent from `clubs.csv`/`national_teams.csv` (38 clubs and 20 FIWC games in real data) must still produce resolvable team nodes (Tasks 3, 5, 6).
5. Re-running the build must give byte-identical output (deterministic ordering, hash-based transfer URIs), and re-running linking must work with no network (Tasks 10, 11).

---

## File Structure

```
config.json                  scope and base URIs
requirements.txt             rdflib, pyshacl, pytest
Makefile                     convenience targets
.gitignore
ontology/football.ttl        ontology
shapes/football-shapes.ttl   SHACL shapes
src/common.py                config, CSV, Turtle writer, parsers, Uris, BuildCtx, named_node
src/scope.py                 Scope dataclass + select_scope()
src/select_scope.py          CLI: writes .cache/scope.json
src/countries.py             CountryResolver
src/builders/__init__.py
src/builders/reference.py    countries, national teams, competitions
src/builders/clubs.py        clubs, stadiums, managers
src/builders/players.py      players, positions, extra countries
src/builders/matches.py      matches, seasons, referees
src/builders/facts.py        appearances, game events
src/builders/transfers.py    transfers, valuations
src/build_rdf.py             CLI orchestrator
src/link_wikidata.py         5-star linking
src/validate.py              vocabulary check CLI
tests/helpers.py, tests/conftest.py, tests/test_*.py
queries/*.rq                 competency queries
queries/checks/*.rq          dangling-reference checks
scripts/query.sh, load.sh, run_checks.sh, shacl.sh
docker/Dockerfile, docker-compose.yml
README.md
```

---

### Task 1: Project bootstrap

**Files:**
- Create: `.gitignore`, `requirements.txt`, `config.json`, `Makefile` (placeholder targets added in later tasks)

**Interfaces:**
- Produces: `config.json` schema (`ontology_base`, `resource_base`, `data_dir`, `out_dir`, `cache_dir`, `competitions[]` with `id`, `kind` in `club|national`, `seasons` as a list or `{"from":Y,"to":Y}`); a working `.venv` with pytest, rdflib, pyshacl.

- [ ] **Step 1: Initialise git and ignore large/generated paths**

```bash
cd "/home/jkl/Projects/Semantic Football Web"
git init
cat > .gitignore <<'EOF'
datasets/
output/
.cache/
.venv/
__pycache__/
*.pyc
.pytest_cache/
EOF
```

- [ ] **Step 2: Create requirements and the virtualenv**

```bash
cat > requirements.txt <<'EOF'
rdflib>=7.0
pyshacl>=0.26
pytest>=7.4
EOF
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -c "import rdflib, pyshacl, pytest; print(rdflib.__version__)"
```
Expected: a version number such as `7.x`.

- [ ] **Step 3: Write `config.json`**

```json
{
  "ontology_base": "https://example.org/football/ontology#",
  "resource_base": "https://example.org/football/resource/",
  "data_dir": "datasets",
  "out_dir": "output",
  "cache_dir": ".cache",
  "competitions": [
    {"id": "GB1", "kind": "club", "seasons": {"from": 2012, "to": 2025}},
    {"id": "ES1", "kind": "club", "seasons": {"from": 2012, "to": 2025}},
    {"id": "IT1", "kind": "club", "seasons": {"from": 2012, "to": 2025}},
    {"id": "L1",  "kind": "club", "seasons": {"from": 2012, "to": 2025}},
    {"id": "FR1", "kind": "club", "seasons": {"from": 2012, "to": 2025}},
    {"id": "CL",  "kind": "club", "seasons": {"from": 2012, "to": 2025}},
    {"id": "EL",  "kind": "club", "seasons": {"from": 2012, "to": 2025}},
    {"id": "FIWC", "kind": "national", "seasons": [2005, 2009, 2013, 2017, 2021, 2025]}
  ]
}
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore requirements.txt config.json
git commit -m "chore: project bootstrap (config, requirements)"
```

---

### Task 2: Common helpers (Turtle writer, parsers, URIs)

**Files:**
- Create: `src/common.py`, `tests/helpers.py`, `tests/conftest.py`, `tests/test_common.py`

**Interfaces:**
- Produces (all in `src/common.py`):
  - `load_config(path="config.json") -> dict`; `expand_seasons(spec) -> list[int]`
  - `read_csv(path) -> Iterator[dict]`
  - `clean(s) -> str|None` (strip, drop control chars, `""`→None); `parse_date(s)->str|None` (`"1978-06-09 00:00:00"`→`"1978-06-09"`); `parse_int(s)->str|None`; `parse_decimal(s)->str|None`; `parse_net_transfer(s)->str|None`; `slug(s)->str|None`
  - `lit(s, lang=None)->str|None`; `typed(v, dt)->str|None`; `t_int(s)`, `t_dec(s)`, `t_date(s)` (parse + type, None-safe); `iri(s)->str|None`
  - `hash_id(*parts)->str` (sha1 hex, first 16 chars)
  - `class Uris(cfg)` with `res(kind, key)->str|None` (returns `"<base{kind}/{key}>"`, None for empty key) and `team(game_kind, team_id)->str|None` (`club` or `national-team`)
  - `class TurtleWriter(path, ontology_base)`: context manager; `node(subject, *pairs)`; attribute `count` (triples written); object value may be a `str`, `None` (skipped) or a `list` of those
  - `class BuildCtx(cfg, uris, scope, data_dir, out_dir)` with `notes: Counter`, `seen: set`, `csv(name)`, `writer(name)`, `once(*key)->bool`
  - `named_node(ctx, w, kind, cls, name)->str|None` writes `a cls; rdfs:label name@und` once per name and returns its URI
- `tests/helpers.py` produces: `FB`, `R` (base strings), `HEADERS` (real CSV headers per file), `put(data_dir, name, rows)`, `load_ttl(path)->rdflib.Graph`, `write_mini(data_dir)`.
- `tests/conftest.py` produces fixtures `cfg`, `data_dir`, `ctx` (the latter calls `scope.select_scope`, written in Task 3, so tests using `ctx` start in Task 3).

- [ ] **Step 1: Write `tests/helpers.py`** (real headers copied from the CSVs, plus the mini fixture dataset reused by all later tests)

```python
import csv
from pathlib import Path

from rdflib import Graph

FB = "https://example.org/football/ontology#"
R = "https://example.org/football/resource/"

HEADERS = {
    "countries.csv": ["country_id", "country_name", "country_code", "confederation", "total_clubs", "total_players", "average_age", "url"],
    "national_teams.csv": ["national_team_id", "name", "team_code", "country_id", "country_name", "country_code", "confederation", "team_image_url", "squad_size", "average_age", "foreigners_number", "foreigners_percentage", "total_market_value", "coach_name", "fifa_ranking", "last_season", "url"],
    "competitions.csv": ["competition_id", "competition_code", "name", "sub_type", "type", "country_id", "country_name", "domestic_league_code", "confederation", "total_clubs", "url"],
    "clubs.csv": ["club_id", "club_code", "name", "domestic_competition_id", "total_market_value", "squad_size", "average_age", "foreigners_number", "foreigners_percentage", "national_team_players", "stadium_name", "stadium_seats", "net_transfer_record", "coach_name", "last_season", "filename", "url"],
    "games.csv": ["game_id", "competition_id", "season", "round", "date", "home_club_id", "away_club_id", "home_club_goals", "away_club_goals", "home_club_position", "away_club_position", "home_club_manager_name", "away_club_manager_name", "stadium", "attendance", "referee", "url", "home_club_formation", "away_club_formation", "home_club_name", "away_club_name", "aggregate", "competition_type"],
    "players.csv": ["player_id", "first_name", "last_name", "name", "last_season", "current_club_id", "player_code", "country_of_birth", "city_of_birth", "country_of_citizenship", "date_of_birth", "sub_position", "position", "foot", "height_in_cm", "contract_expiration_date", "agent_name", "image_url", "international_caps", "international_goals", "current_national_team_id", "url", "current_club_domestic_competition_id", "current_club_name", "market_value_in_eur", "highest_market_value_in_eur"],
    "appearances.csv": ["appearance_id", "game_id", "player_id", "player_club_id", "player_current_club_id", "date", "player_name", "competition_id", "yellow_cards", "red_cards", "goals", "assists", "minutes_played"],
    "game_events.csv": ["game_event_id", "date", "game_id", "minute", "type", "club_id", "club_name", "player_id", "description", "player_in_id", "player_assist_id"],
    "transfers.csv": ["player_id", "transfer_date", "transfer_season", "from_club_id", "to_club_id", "from_club_name", "to_club_name", "transfer_fee", "market_value_in_eur", "player_name"],
    "player_valuations.csv": ["player_id", "date", "market_value_in_eur", "current_club_name", "current_club_id", "player_club_domestic_competition_id"],
}


def put(data_dir, name, rows):
    header = HEADERS[name]
    with open(Path(data_dir) / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(header)
        for r in rows:
            w.writerow([r.get(h, "") for h in header])


def load_ttl(path):
    g = Graph()
    g.parse(str(path), format="turtle")
    return g


def write_mini(d):
    put(d, "countries.csv", [
        {"country_id": "189", "country_name": "England", "country_code": "GB1", "confederation": "europa", "url": "https://www.transfermarkt.co.uk/wettbewerbe/national/wettbewerbe/189"},
        {"country_id": "50", "country_name": "Türkiye", "country_code": "TR1", "confederation": "europa"},
    ])
    put(d, "national_teams.csv", [
        {"national_team_id": "3299", "name": "England", "team_code": "england", "country_id": "189", "country_name": "England", "country_code": "GB1", "confederation": "UEFA", "team_image_url": "https://tmssl.akamaized.net/e.png", "squad_size": "26", "average_age": "27.1", "foreigners_number": "0", "total_market_value": "1000000000", "coach_name": "Gareth Southgate", "fifa_ranking": "4", "last_season": "2025", "url": "https://www.transfermarkt.co.uk/england/startseite/verein/3299"},
    ])
    put(d, "competitions.csv", [
        {"competition_id": "GB1", "competition_code": "premier-league", "name": "premier-league", "type": "domestic_league", "country_id": "189", "country_name": "England", "confederation": "europa", "url": "https://www.transfermarkt.co.uk/premier-league/startseite/wettbewerb/GB1"},
        {"competition_id": "FIWC", "competition_code": "fifa-world-cup", "name": "fifa-world-cup", "type": "national_team_competition", "country_id": "-1", "confederation": "fifa"},
    ])
    put(d, "clubs.csv", [
        {"club_id": "11", "club_code": "arsenal", "name": "Arsenal FC", "domestic_competition_id": "GB1", "total_market_value": "1200000000", "squad_size": "25", "average_age": "25.1", "foreigners_number": "15", "foreigners_percentage": "60.0", "national_team_players": "10", "stadium_name": "Emirates Stadium", "stadium_seats": "60704", "net_transfer_record": "+€5.90m", "coach_name": "Mikel Arteta", "last_season": "2023", "url": "https://www.transfermarkt.co.uk/arsenal/startseite/verein/11"},
    ])
    put(d, "games.csv", [
        {"game_id": "100", "competition_id": "GB1", "season": "2023", "round": "1. Matchday", "date": "2023-08-12", "home_club_id": "11", "away_club_id": "148", "home_club_goals": "2", "away_club_goals": "1", "stadium": "Emirates Stadium", "attendance": "60000", "referee": "Michael Oliver", "home_club_formation": "4-3-3", "home_club_name": "Arsenal FC", "away_club_name": "Tottenham Hotspur"},
        {"game_id": "101", "competition_id": "GB1", "season": "2022", "date": "2022-08-12", "home_club_id": "11", "away_club_id": "148", "home_club_goals": "0", "away_club_goals": "0", "home_club_name": "Arsenal FC", "away_club_name": "Tottenham Hotspur"},
        {"game_id": "200", "competition_id": "FIWC", "season": "2025", "round": "Group A", "date": "2026-06-12", "home_club_id": "3299", "away_club_id": "9999", "home_club_goals": "1", "away_club_goals": "1", "home_club_name": "England", "away_club_name": "Serbia and Montenegro"},
    ])
    put(d, "players.csv", [
        {"player_id": "10", "first_name": "Bukayo", "last_name": "Saka", "name": "Bukayo Saka", "date_of_birth": "2001-09-05 00:00:00", "country_of_birth": "England", "city_of_birth": "London  ", "country_of_citizenship": "England", "sub_position": "Right Winger", "position": "Attack", "foot": "left", "height_in_cm": "178", "current_club_id": "11", "current_club_name": "Arsenal FC", "market_value_in_eur": "120000000", "highest_market_value_in_eur": "130000000", "image_url": "https://img.example/10.jpg", "url": "https://www.transfermarkt.co.uk/saka/profil/spieler/10", "current_national_team_id": "3299"},
        {"player_id": "20", "first_name": "Heung-min", "last_name": "Son", "name": "Heung-min Son", "country_of_citizenship": "Korea, South", "position": "Missing", "current_club_id": "148", "current_club_name": "Tottenham Hotspur"},
        {"player_id": "30", "name": "Far Away", "current_club_id": "999", "current_club_name": "Elsewhere FC"},
    ])
    put(d, "appearances.csv", [
        {"appearance_id": "100_10", "game_id": "100", "player_id": "10", "player_club_id": "11", "date": "2023-08-12", "player_name": "Bukayo Saka", "competition_id": "GB1", "yellow_cards": "0", "red_cards": "0", "goals": "1", "assists": "0", "minutes_played": "90"},
        {"appearance_id": "200_10", "game_id": "200", "player_id": "10", "player_club_id": "3299", "date": "2026-06-12", "player_name": "Bukayo Saka", "competition_id": "FIWC", "yellow_cards": "0", "red_cards": "0", "goals": "0", "assists": "0", "minutes_played": "45"},
        {"appearance_id": "101_30", "game_id": "101", "player_id": "30", "player_club_id": "11", "competition_id": "GB1"},
    ])
    put(d, "game_events.csv", [
        {"game_event_id": "e1", "date": "2023-08-12", "game_id": "100", "minute": "10", "type": "Goals", "club_id": "11", "club_name": "Arsenal FC", "player_id": "10", "description": ", Right-footed shot, 1. Tournament Goal Assist: , Cross", "player_assist_id": "20"},
        {"game_event_id": "e2", "date": "2023-08-12", "game_id": "100", "minute": "30", "type": "Cards", "club_id": "148", "club_name": "Tottenham Hotspur", "player_id": "20", "description": "1. Yellow card  , Foul"},
        {"game_event_id": "e3", "date": "2023-08-12", "game_id": "100", "minute": "60", "type": "Substitutions", "club_id": "11", "club_name": "Arsenal FC", "player_id": "10", "description": ", Tactical", "player_in_id": "20"},
        {"game_event_id": "e4", "date": "2026-06-12", "game_id": "200", "minute": "120", "type": "Shootout", "club_id": "3299", "club_name": "England", "player_id": "10", "description": ", Scored"},
    ])
    put(d, "transfers.csv", [
        {"player_id": "10", "transfer_date": "2019-07-01", "transfer_season": "19/20", "from_club_id": "999", "to_club_id": "11", "from_club_name": "Hale End", "to_club_name": "Arsenal FC", "transfer_fee": "0.000", "market_value_in_eur": "500000.000", "player_name": "Bukayo Saka"},
        {"player_id": "10", "transfer_date": "2019-07-01", "transfer_season": "19/20", "from_club_id": "999", "to_club_id": "11", "from_club_name": "Hale End", "to_club_name": "Arsenal FC", "transfer_fee": "0.000", "market_value_in_eur": "500000.000", "player_name": "Bukayo Saka"},
        {"player_id": "10", "transfer_date": "2023-01-01", "transfer_season": "22/23", "from_club_id": "11", "to_club_id": "148", "from_club_name": "Arsenal FC", "to_club_name": "Tottenham Hotspur", "transfer_fee": "5000000.000", "market_value_in_eur": "90000000.000", "player_name": "Bukayo Saka"},
        {"player_id": "10", "transfer_date": "2024-01-01", "transfer_season": "23/24", "from_club_id": "148", "to_club_id": "11", "from_club_name": "Tottenham Hotspur", "to_club_name": "Arsenal FC", "transfer_fee": "", "player_name": "Bukayo Saka"},
        {"player_id": "30", "transfer_date": "2020-01-01", "transfer_season": "19/20", "from_club_id": "555", "to_club_id": "999", "from_club_name": "Nowhere", "to_club_name": "Elsewhere FC", "transfer_fee": "100.000", "player_name": "Far Away"},
    ])
    put(d, "player_valuations.csv", [
        {"player_id": "10", "date": "2023-06-01", "market_value_in_eur": "100000000", "current_club_name": "Arsenal FC", "current_club_id": "11"},
        {"player_id": "10", "date": "2019-01-01", "market_value_in_eur": "5000000", "current_club_name": "Unknown", "current_club_id": "999"},
        {"player_id": "30", "date": "2020-01-01", "market_value_in_eur": "1000", "current_club_name": "Elsewhere FC", "current_club_id": "777"},
    ])
```

- [ ] **Step 2: Write `tests/conftest.py`**

```python
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from helpers import write_mini  # noqa: E402


@pytest.fixture
def cfg():
    return {
        "ontology_base": "https://example.org/football/ontology#",
        "resource_base": "https://example.org/football/resource/",
        "competitions": [
            {"id": "GB1", "kind": "club", "seasons": [2023]},
            {"id": "FIWC", "kind": "national", "seasons": [2025]},
        ],
    }


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "datasets"
    d.mkdir()
    write_mini(d)
    return d


@pytest.fixture
def ctx(cfg, data_dir, tmp_path):
    from common import BuildCtx, Uris
    from scope import select_scope

    out = tmp_path / "out"
    out.mkdir()
    return BuildCtx(cfg, Uris(cfg), select_scope(cfg, data_dir), data_dir, out)
```

- [ ] **Step 3: Write the failing tests `tests/test_common.py`**

```python
from rdflib import Literal, URIRef
from rdflib.namespace import XSD

from common import (BuildCtx, TurtleWriter, Uris, clean, expand_seasons, hash_id, iri,
                    lit, parse_date, parse_decimal, parse_int, parse_net_transfer,
                    slug, t_int)
from helpers import FB, R, load_ttl


def test_clean():
    assert clean("  Opole  ") == "Opole"
    assert clean("") is None and clean("   ") is None and clean(None) is None
    assert clean("a\x00b") == "ab"


def test_parse_date():
    assert parse_date("1978-06-09 00:00:00") == "1978-06-09"
    assert parse_date("2019-07-01") == "2019-07-01"
    assert parse_date("") is None and parse_date("garbage") is None


def test_parse_numbers():
    assert parse_int("90") == "90" and parse_int("2.0") == "2"
    assert parse_int("") is None and parse_int("x") is None and parse_int("NaN") is None
    assert parse_decimal("700000.000") == "700000"
    assert parse_decimal("0.000") == "0"
    assert parse_decimal("27.1") == "27.1"
    assert parse_decimal("abc") is None


def test_parse_net_transfer():
    assert parse_net_transfer("+€5.90m") == "5900000"
    assert parse_net_transfer("€-25.00m") == "-25000000"
    assert parse_net_transfer("€0") == "0"
    assert parse_net_transfer("+€350k") == "350000"
    assert parse_net_transfer("-") is None and parse_net_transfer("") is None


def test_slug_and_hash_and_iri():
    assert slug(" Emirates Stadium ") == "Emirates_Stadium"
    assert slug("") is None
    assert hash_id("1", "2") == hash_id("1", "2") != hash_id("2", "1")
    assert len(hash_id("x")) == 16
    assert iri("https://a.b/c") == "<https://a.b/c>"
    assert iri("has space") is None and iri("") is None


def test_expand_seasons():
    assert expand_seasons({"from": 2012, "to": 2014}) == [2012, 2013, 2014]
    assert expand_seasons([2005, "2009"]) == [2005, 2009]


def test_uris(cfg):
    u = Uris(cfg)
    assert u.res("player", "10") == f"<{R}player/10>"
    assert u.res("player", "") is None and u.res("player", None) is None
    assert u.res("stadium", "Allianz Arena") == f"<{R}stadium/Allianz%20Arena>"
    assert u.team("club", "5") == f"<{R}club/5>"
    assert u.team("national", "5") == f"<{R}national-team/5>"
    assert u.team("club", "") is None


def test_writer_round_trips_awkward_literals(tmp_path):
    tricky = 'O"Brien \\ back\nnewline\ttab Türkiye'
    path = tmp_path / "t.ttl"
    with TurtleWriter(path, FB) as w:
        w.node(f"<{R}player/1>", ("a", "fb:Player"), ("rdfs:label", lit(tricky, "und")),
               ("fb:heightCm", t_int("178")), ("fb:agent", None), ("fb:x", None))
        w.node(f"<{R}player/2>", ("fb:agent", None))  # nothing to write
    g = load_ttl(path)
    assert w.count == 3
    assert (URIRef(f"{R}player/1"), URIRef("http://www.w3.org/2000/01/rdf-schema#label"),
            Literal(tricky, lang="und")) in g
    assert (URIRef(f"{R}player/1"), URIRef(FB + "heightCm"), Literal("178", datatype=XSD.integer)) in g
    assert len(g) == 3


def test_writer_accepts_list_objects(tmp_path):
    path = tmp_path / "t.ttl"
    with TurtleWriter(path, FB) as w:
        w.node(f"<{R}position/Attack>", ("a", ["fb:Position", "skos:Concept"]))
    assert len(load_ttl(path)) == 2


def test_once_and_named_node(cfg, tmp_path):
    from common import named_node
    ctx = BuildCtx(cfg, Uris(cfg), scope=None, data_dir=tmp_path, out_dir=tmp_path)
    path = tmp_path / "n.ttl"
    with TurtleWriter(path, FB) as w:
        a = named_node(ctx, w, "stadium", "fb:Stadium", " Emirates Stadium ")
        b = named_node(ctx, w, "stadium", "fb:Stadium", "Emirates Stadium")
        assert named_node(ctx, w, "stadium", "fb:Stadium", "") is None
    assert a == b == f"<{R}stadium/Emirates_Stadium>"
    assert len(load_ttl(path)) == 2
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_common.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'common'`).

- [ ] **Step 5: Write `src/common.py`**

```python
"""Shared helpers: config, CSV reading, Turtle writing, value parsing, URIs."""
import csv
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

csv.field_size_limit(10**7)

PREFIXES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "schema": "https://schema.org/",
}

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ESC = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}
_NET = re.compile(r"^([+-]?)€([+-]?)([\d.]+)(bn|m|k)?$")
_MULT = {"bn": 10**9, "m": 10**6, "k": 10**3, None: 1}


# ---------- config / csv ----------

def load_config(path="config.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def expand_seasons(spec):
    if isinstance(spec, dict):
        return list(range(int(spec["from"]), int(spec["to"]) + 1))
    return [int(s) for s in spec]


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


# ---------- value parsing ----------

def clean(s):
    if s is None:
        return None
    s = _CTRL.sub("", s).strip()
    return s or None


def parse_date(s):
    s = clean(s)
    if s and re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    return None


def parse_int(s):
    s = clean(s)
    if s is None:
        return None
    try:
        return str(int(Decimal(s)))
    except (InvalidOperation, ValueError, OverflowError):
        return None


def parse_decimal(s):
    s = clean(s)
    if s is None:
        return None
    try:
        d = Decimal(s)
        if not d.is_finite():
            return None
        return format(d.normalize(), "f")
    except InvalidOperation:
        return None


def parse_net_transfer(s):
    s = clean(s)
    m = _NET.match(s) if s else None
    if not m:
        return None
    sign = -1 if "-" in (m.group(1), m.group(2)) else 1
    try:
        val = Decimal(m.group(3))
    except InvalidOperation:
        return None
    return str(int(sign * val * _MULT[m.group(4)]))


def slug(s):
    s = clean(s)
    return s.replace(" ", "_") if s else None


def hash_id(*parts):
    return hashlib.sha1("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:16]


# ---------- Turtle terms ----------

def esc(s):
    return "".join(_ESC.get(c, c) for c in s)


def lit(s, lang=None):
    s = clean(s) if s is not None else None
    if s is None:
        return None
    return f'"{esc(s)}"@{lang}' if lang else f'"{esc(s)}"'


def typed(v, dt):
    return None if v is None else f'"{v}"^^{dt}'


def t_int(s):
    return typed(parse_int(s), "xsd:integer")


def t_dec(s):
    return typed(parse_decimal(s), "xsd:decimal")


def t_date(s):
    return typed(parse_date(s), "xsd:date")


def iri(s):
    s = clean(s)
    if s is None or re.search(r'[\s<>"{}|\\^`]', s):
        return None
    return f"<{s}>"


class Uris:
    def __init__(self, cfg):
        self.base = cfg["resource_base"]
        self.onto = cfg["ontology_base"]

    def res(self, kind, key):
        key = clean(str(key)) if key is not None else None
        if key is None:
            return None
        return f"<{self.base}{kind}/{quote(key, safe='-_.~')}>"

    def team(self, game_kind, team_id):
        return self.res("club" if game_kind == "club" else "national-team", team_id)


class TurtleWriter:
    def __init__(self, path, ontology_base):
        self.path = Path(path)
        self.onto = ontology_base
        self.count = 0
        self.f = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.path, "w", encoding="utf-8")
        for p, ns in PREFIXES.items():
            self.f.write(f"@prefix {p}: <{ns}> .\n")
        self.f.write(f"@prefix fb: <{self.onto}> .\n\n")
        return self

    def __exit__(self, *exc):
        self.f.close()

    def node(self, subject, *pairs):
        if subject is None:
            return
        parts = []
        for p, o in pairs:
            for x in (o if isinstance(o, list) else [o]):
                if x is not None:
                    parts.append((p, x))
        if not parts:
            return
        body = " ;\n    ".join(f"{p} {o}" for p, o in parts)
        self.f.write(f"{subject}\n    {body} .\n")
        self.count += len(parts)


@dataclass
class BuildCtx:
    cfg: dict
    uris: Uris
    scope: object
    data_dir: Path
    out_dir: Path
    notes: Counter = field(default_factory=Counter)
    seen: set = field(default_factory=set)
    countries: object = None

    def csv(self, name):
        return read_csv(Path(self.data_dir) / name)

    def writer(self, name):
        return TurtleWriter(Path(self.out_dir) / name, self.cfg["ontology_base"])

    def once(self, *key):
        if key in self.seen:
            return False
        self.seen.add(key)
        return True


def named_node(ctx, w, kind, cls, name):
    """Write a labelled reference node once per name; return its URI (or None)."""
    name = clean(name)
    if name is None:
        return None
    uri = ctx.uris.res(kind, slug(name))
    if ctx.once(kind, name):
        w.node(uri, ("a", cls), ("rdfs:label", lit(name, "und")))
    return uri
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_common.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/common.py tests/helpers.py tests/conftest.py tests/test_common.py
git commit -m "feat: common helpers (Turtle writer, parsers, URIs) with tests"
```

---

### Task 3: Scope selection

**Files:**
- Create: `src/scope.py`, `src/select_scope.py`, `tests/test_scope.py`

**Interfaces:**
- Consumes: `common.load_config`, `expand_seasons`, `read_csv`, `clean`.
- Produces: `scope.Scope` dataclass with `game_ids:set[str]`, `game_kind:dict[str,str]` (`"club"|"national"`), `club_ids:set[str]`, `club_names:dict[str,str]`, `national_ids:set[str]`, `national_names:dict[str,str]`, `player_ids:set[str]`; `Scope.save(path)`, `Scope.load(path)`; `select_scope(cfg, data_dir) -> Scope`. CLI `python src/select_scope.py` writes `<cache_dir>/scope.json`.

- [ ] **Step 1: Write the failing test `tests/test_scope.py`**

```python
from scope import Scope, select_scope


def test_games_filtered_by_competition_and_season(ctx):
    s = ctx.scope
    assert s.game_ids == {"100", "200"}          # 101 is season 2022, excluded
    assert s.game_kind == {"100": "club", "200": "national"}


def test_clubs_and_national_teams(ctx):
    s = ctx.scope
    assert {"11", "148"} <= s.club_ids
    assert "999" in s.club_ids                    # from an in-scope player's transfer
    assert "777" not in s.club_ids                # valuation of an out-of-scope player
    assert s.national_ids == {"3299", "9999"}
    assert s.club_names["148"] == "Tottenham Hotspur"
    assert s.club_names["999"] == "Hale End"      # "Unknown" valuation name never wins
    assert s.national_names["9999"] == "Serbia and Montenegro"


def test_players(ctx):
    assert ctx.scope.player_ids == {"10", "20"}   # 30: only in excluded game / other club


def test_save_and_load_round_trip(ctx, tmp_path):
    p = tmp_path / "scope.json"
    ctx.scope.save(p)
    assert Scope.load(p) == ctx.scope


def test_unknown_club_name_is_ignored(cfg, data_dir):
    s = select_scope(cfg, data_dir)
    assert "Unknown" not in s.club_names.values()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_scope.py -v`
Expected: FAIL (`No module named 'scope'`).

- [ ] **Step 3: Write `src/scope.py`**

```python
"""Compute the in-scope game / club / national team / player ID sets."""
import json
from dataclasses import dataclass, field
from pathlib import Path

from common import clean, expand_seasons, read_csv


@dataclass
class Scope:
    game_ids: set = field(default_factory=set)
    game_kind: dict = field(default_factory=dict)
    club_ids: set = field(default_factory=set)
    club_names: dict = field(default_factory=dict)
    national_ids: set = field(default_factory=set)
    national_names: dict = field(default_factory=dict)
    player_ids: set = field(default_factory=set)

    def save(self, path):
        data = {
            "game_ids": sorted(self.game_ids), "game_kind": self.game_kind,
            "club_ids": sorted(self.club_ids), "club_names": self.club_names,
            "national_ids": sorted(self.national_ids), "national_names": self.national_names,
            "player_ids": sorted(self.player_ids),
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path):
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(set(d["game_ids"]), d["game_kind"], set(d["club_ids"]), d["club_names"],
                   set(d["national_ids"]), d["national_names"], set(d["player_ids"]))


def select_scope(cfg, data_dir):
    data_dir = Path(data_dir)
    comps = {c["id"]: (c["kind"], set(expand_seasons(c["seasons"]))) for c in cfg["competitions"]}
    s = Scope()

    def add_team(kind, tid, name):
        tid = clean(tid)
        if tid is None:
            return
        ids, names = (s.club_ids, s.club_names) if kind == "club" else (s.national_ids, s.national_names)
        ids.add(tid)
        name = clean(name)
        if name and name != "Unknown" and tid not in names:
            names[tid] = name

    for r in read_csv(data_dir / "games.csv"):
        spec = comps.get(r["competition_id"])
        if not spec or int(r["season"]) not in spec[1]:
            continue
        kind = spec[0]
        s.game_ids.add(r["game_id"])
        s.game_kind[r["game_id"]] = kind
        add_team(kind, r["home_club_id"], r["home_club_name"])
        add_team(kind, r["away_club_id"], r["away_club_name"])

    for r in read_csv(data_dir / "appearances.csv"):
        gid = r["game_id"]
        if gid in s.game_ids:
            s.player_ids.add(r["player_id"])
            add_team(s.game_kind[gid], r["player_club_id"], None)

    for r in read_csv(data_dir / "game_events.csv"):
        gid = r["game_id"]
        if gid in s.game_ids:
            for col in ("player_id", "player_in_id", "player_assist_id"):
                v = clean(r[col])
                if v:
                    s.player_ids.add(v)
            add_team(s.game_kind[gid], r["club_id"], r["club_name"])

    players = list(read_csv(data_dir / "players.csv"))
    for r in players:
        if clean(r["current_club_id"]) in s.club_ids:
            s.player_ids.add(r["player_id"])
    for r in players:
        if r["player_id"] in s.player_ids:
            add_team("club", r["current_club_id"], r["current_club_name"])

    for r in read_csv(data_dir / "transfers.csv"):
        if r["player_id"] in s.player_ids:
            add_team("club", r["from_club_id"], r["from_club_name"])
            add_team("club", r["to_club_id"], r["to_club_name"])

    for r in read_csv(data_dir / "player_valuations.csv"):
        if r["player_id"] in s.player_ids:
            add_team("club", r["current_club_id"], r["current_club_name"])

    return s
```

- [ ] **Step 4: Write `src/select_scope.py`**

```python
"""CLI: python src/select_scope.py [--config config.json]  ->  <cache_dir>/scope.json"""
import argparse
from pathlib import Path

from common import load_config
from scope import select_scope


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    scope = select_scope(cfg, cfg["data_dir"])
    out = Path(cfg["cache_dir"]) / "scope.json"
    scope.save(out)
    print(f"games={len(scope.game_ids)} clubs={len(scope.club_ids)} "
          f"national_teams={len(scope.national_ids)} players={len(scope.player_ids)} -> {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest tests/test_scope.py tests/test_common.py -v`
Expected: all PASS.

- [ ] **Step 6: Run on real data and record the numbers**

Run: `.venv/bin/python src/select_scope.py`
Expected: one summary line; `games` should be about 30.1k (29,740 club games plus ~390 World Cup games), players tens of thousands. Note the printed numbers in the README later. If `games` is far outside 29k–31k, stop and investigate before continuing.

- [ ] **Step 7: Commit**

```bash
git add src/scope.py src/select_scope.py tests/test_scope.py
git commit -m "feat: scope selection (games, clubs, national teams, players)"
```

---

### Task 4: Ontology

**Files:**
- Create: `ontology/football.ttl`, `tests/test_ontology.py`

**Interfaces:**
- Produces: all `fb:` classes and properties used by Tasks 5–9. Builders may only emit terms defined here (enforced by `validate.py` in Task 12 and the orchestrator test in Task 10).

- [ ] **Step 1: Write the failing test `tests/test_ontology.py`**

```python
from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS, OWL

FB = Namespace("https://example.org/football/ontology#")
ONT = Path(__file__).resolve().parents[1] / "ontology" / "football.ttl"

CLASSES = ["Team", "Club", "NationalTeam", "Player", "Match", "Competition", "Country", "Stadium",
           "Referee", "Manager", "Position", "Season", "MatchEvent", "Goal", "Card", "Substitution",
           "PenaltyShootoutKick", "Appearance", "Transfer", "MarketValuation"]


def graph():
    g = Graph()
    g.parse(str(ONT), format="turtle")
    return g


def test_classes_defined_with_label_and_comment():
    g = graph()
    for c in CLASSES:
        assert (FB[c], RDF.type, OWL.Class) in g, c
        assert (FB[c], RDFS.label, None) in g, c
        assert (FB[c], RDFS.comment, None) in g, c


def test_hierarchy():
    g = graph()
    assert (FB.Club, RDFS.subClassOf, FB.Team) in g
    assert (FB.NationalTeam, RDFS.subClassOf, FB.Team) in g
    assert (FB.Goal, RDFS.subClassOf, FB.MatchEvent) in g
    assert (FB.PenaltyShootoutKick, RDFS.subClassOf, FB.MatchEvent) in g


def test_every_property_has_label_comment_and_type():
    g = graph()
    props = set(g.subjects(RDF.type, OWL.ObjectProperty)) | set(g.subjects(RDF.type, OWL.DatatypeProperty))
    assert len(props) >= 60
    for p in props:
        assert (p, RDFS.label, None) in g, p
        assert (p, RDFS.comment, None) in g, p


def test_functional_and_inverse():
    g = graph()
    assert (FB.dateOfBirth, RDF.type, OWL.FunctionalProperty) in g
    assert (FB.hasPlayer, OWL.inverseOf, FB.playsFor) in g
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_ontology.py -v`
Expected: FAIL (file not found).

- [ ] **Step 3: Write `ontology/football.ttl`**

```turtle
@prefix fb:     <https://example.org/football/ontology#> .
@prefix rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:    <http://www.w3.org/2002/07/owl#> .
@prefix xsd:    <http://www.w3.org/2001/XMLSchema#> .
@prefix skos:   <http://www.w3.org/2004/02/skos/core#> .
@prefix foaf:   <http://xmlns.com/foaf/0.1/> .
@prefix schema: <https://schema.org/> .

<https://example.org/football/ontology> a owl:Ontology ;
    rdfs:label "Football ontology"@en ;
    rdfs:comment "Vocabulary for clubs, national teams, players, matches, appearances, events, transfers and market valuations, derived from Transfermarkt data."@en .

# ---------------- Classes ----------------
fb:Team a owl:Class ; rdfs:subClassOf schema:SportsTeam ; rdfs:label "Team"@en ; rdfs:comment "A club or a national team."@en .
fb:Club a owl:Class ; rdfs:subClassOf fb:Team ; rdfs:label "Club"@en ; rdfs:comment "A football club."@en .
fb:NationalTeam a owl:Class ; rdfs:subClassOf fb:Team ; rdfs:label "National team"@en ; rdfs:comment "A national football team."@en .
fb:Player a owl:Class ; rdfs:subClassOf foaf:Person , schema:Person ; rdfs:label "Player"@en ; rdfs:comment "A football player."@en .
fb:Match a owl:Class ; rdfs:subClassOf schema:SportsEvent ; rdfs:label "Match"@en ; rdfs:comment "A football match between two teams."@en .
fb:Competition a owl:Class ; rdfs:subClassOf schema:SportsOrganization ; rdfs:label "Competition"@en ; rdfs:comment "A league, cup or tournament."@en .
fb:Country a owl:Class ; rdfs:subClassOf schema:Country ; rdfs:label "Country"@en ; rdfs:comment "A country or football nation."@en .
fb:Stadium a owl:Class ; rdfs:subClassOf schema:StadiumOrArena ; rdfs:label "Stadium"@en ; rdfs:comment "A football stadium."@en .
fb:Referee a owl:Class ; rdfs:label "Referee"@en ; rdfs:comment "A match referee."@en .
fb:Manager a owl:Class ; rdfs:label "Manager"@en ; rdfs:comment "A coach or manager of a team."@en .
fb:Position a owl:Class ; rdfs:label "Position"@en ; rdfs:comment "A playing position, modelled as a SKOS concept; sub-positions are skos:broader than their position."@en .
fb:Season a owl:Class ; rdfs:label "Season"@en ; rdfs:comment "A season, identified by its start year in the source data."@en .
fb:MatchEvent a owl:Class ; rdfs:label "Match event"@en ; rdfs:comment "Something that happened during a match."@en .
fb:Goal a owl:Class ; rdfs:subClassOf fb:MatchEvent ; rdfs:label "Goal"@en ; rdfs:comment "A goal event."@en .
fb:Card a owl:Class ; rdfs:subClassOf fb:MatchEvent ; rdfs:label "Card"@en ; rdfs:comment "A yellow, second yellow or red card event."@en .
fb:Substitution a owl:Class ; rdfs:subClassOf fb:MatchEvent ; rdfs:label "Substitution"@en ; rdfs:comment "A substitution event."@en .
fb:PenaltyShootoutKick a owl:Class ; rdfs:subClassOf fb:MatchEvent ; rdfs:label "Penalty shootout kick"@en ; rdfs:comment "A kick taken in a penalty shootout."@en .
fb:Appearance a owl:Class ; rdfs:label "Appearance"@en ; rdfs:comment "A player's participation in one match (n-ary relation between player, match and team)."@en .
fb:Transfer a owl:Class ; rdfs:label "Transfer"@en ; rdfs:comment "A transfer of a player between two clubs on a date."@en .
fb:MarketValuation a owl:Class ; rdfs:label "Market valuation"@en ; rdfs:comment "A dated estimate of a player's market value."@en .

[] a owl:AllDisjointClasses ; owl:members ( fb:Club fb:NationalTeam ) .
[] a owl:AllDisjointClasses ; owl:members ( fb:Player fb:Team fb:Match fb:Competition fb:Country fb:Stadium fb:Season fb:Appearance fb:Transfer fb:MarketValuation fb:MatchEvent ) .

# ---------------- Object properties ----------------
fb:playsFor a owl:ObjectProperty ; rdfs:label "plays for"@en ; rdfs:comment "The club a player currently belongs to."@en ; rdfs:domain fb:Player ; rdfs:range fb:Club .
fb:hasPlayer a owl:ObjectProperty ; owl:inverseOf fb:playsFor ; rdfs:label "has player"@en ; rdfs:comment "Inverse of plays for. Not materialised in the data."@en .
fb:citizenOf a owl:ObjectProperty ; rdfs:label "citizen of"@en ; rdfs:comment "Country of citizenship."@en ; rdfs:domain fb:Player ; rdfs:range fb:Country .
fb:bornIn a owl:ObjectProperty ; rdfs:label "born in"@en ; rdfs:comment "Country of birth."@en ; rdfs:domain fb:Player ; rdfs:range fb:Country .
fb:representsNationalTeam a owl:ObjectProperty ; rdfs:label "represents national team"@en ; rdfs:comment "The national team the player currently plays for."@en ; rdfs:domain fb:Player ; rdfs:range fb:NationalTeam .
fb:position a owl:ObjectProperty ; rdfs:label "position"@en ; rdfs:comment "General playing position."@en ; rdfs:domain fb:Player ; rdfs:range fb:Position .
fb:subPosition a owl:ObjectProperty ; rdfs:label "sub-position"@en ; rdfs:comment "Specific playing position."@en ; rdfs:domain fb:Player ; rdfs:range fb:Position .
fb:homeTeam a owl:ObjectProperty ; rdfs:subPropertyOf schema:homeTeam ; rdfs:label "home team"@en ; rdfs:comment "Home team of a match."@en ; rdfs:domain fb:Match ; rdfs:range fb:Team .
fb:awayTeam a owl:ObjectProperty ; rdfs:subPropertyOf schema:awayTeam ; rdfs:label "away team"@en ; rdfs:comment "Away team of a match."@en ; rdfs:domain fb:Match ; rdfs:range fb:Team .
fb:inCompetition a owl:ObjectProperty ; rdfs:label "in competition"@en ; rdfs:comment "Competition a match belongs to."@en ; rdfs:domain fb:Match ; rdfs:range fb:Competition .
fb:inSeason a owl:ObjectProperty ; rdfs:label "in season"@en ; rdfs:comment "Season a match belongs to."@en ; rdfs:domain fb:Match ; rdfs:range fb:Season .
fb:hostedAt a owl:ObjectProperty ; rdfs:label "hosted at"@en ; rdfs:comment "Stadium where a match was played."@en ; rdfs:domain fb:Match ; rdfs:range fb:Stadium .
fb:refereedBy a owl:ObjectProperty ; rdfs:label "refereed by"@en ; rdfs:comment "Referee of a match."@en ; rdfs:domain fb:Match ; rdfs:range fb:Referee .
fb:country a owl:ObjectProperty ; rdfs:label "country"@en ; rdfs:comment "Country a team or competition belongs to."@en ; rdfs:range fb:Country .
fb:homeStadium a owl:ObjectProperty ; rdfs:label "home stadium"@en ; rdfs:comment "Home stadium of a club."@en ; rdfs:domain fb:Club ; rdfs:range fb:Stadium .
fb:managedBy a owl:ObjectProperty ; rdfs:label "managed by"@en ; rdfs:comment "Current manager of a team."@en ; rdfs:domain fb:Team ; rdfs:range fb:Manager .
fb:domesticCompetition a owl:ObjectProperty ; rdfs:label "domestic competition"@en ; rdfs:comment "Domestic league a club plays in."@en ; rdfs:domain fb:Club ; rdfs:range fb:Competition .
fb:appearanceOf a owl:ObjectProperty ; rdfs:label "appearance of"@en ; rdfs:comment "The player who made the appearance."@en ; rdfs:domain fb:Appearance ; rdfs:range fb:Player .
fb:inMatch a owl:ObjectProperty ; rdfs:label "in match"@en ; rdfs:comment "The match an appearance or event belongs to."@en ; rdfs:range fb:Match .
fb:forTeam a owl:ObjectProperty ; rdfs:label "for team"@en ; rdfs:comment "The team an appearance or event is attributed to."@en ; rdfs:range fb:Team .
fb:byPlayer a owl:ObjectProperty ; rdfs:label "by player"@en ; rdfs:comment "The player an event is about."@en ; rdfs:domain fb:MatchEvent ; rdfs:range fb:Player .
fb:assistedBy a owl:ObjectProperty ; rdfs:label "assisted by"@en ; rdfs:comment "The player who assisted a goal."@en ; rdfs:domain fb:Goal ; rdfs:range fb:Player .
fb:playerIn a owl:ObjectProperty ; rdfs:label "player in"@en ; rdfs:comment "The player who came on."@en ; rdfs:domain fb:Substitution ; rdfs:range fb:Player .
fb:playerOut a owl:ObjectProperty ; rdfs:label "player out"@en ; rdfs:comment "The player who went off."@en ; rdfs:domain fb:Substitution ; rdfs:range fb:Player .
fb:transferOf a owl:ObjectProperty ; rdfs:label "transfer of"@en ; rdfs:comment "The player being transferred."@en ; rdfs:domain fb:Transfer ; rdfs:range fb:Player .
fb:fromClub a owl:ObjectProperty ; rdfs:label "from club"@en ; rdfs:comment "Club the player left."@en ; rdfs:domain fb:Transfer ; rdfs:range fb:Club .
fb:toClub a owl:ObjectProperty ; rdfs:label "to club"@en ; rdfs:comment "Club the player joined."@en ; rdfs:domain fb:Transfer ; rdfs:range fb:Club .
fb:valuationOf a owl:ObjectProperty ; rdfs:label "valuation of"@en ; rdfs:comment "The player being valued."@en ; rdfs:domain fb:MarketValuation ; rdfs:range fb:Player .
fb:atClub a owl:ObjectProperty ; rdfs:label "at club"@en ; rdfs:comment "Club the player belonged to at valuation time."@en ; rdfs:domain fb:MarketValuation ; rdfs:range fb:Club .

# ---------------- Datatype properties ----------------
fb:firstName a owl:DatatypeProperty ; rdfs:subPropertyOf schema:givenName ; rdfs:label "first name"@en ; rdfs:comment "Given name."@en ; rdfs:domain fb:Player ; rdfs:range xsd:string .
fb:lastName a owl:DatatypeProperty ; rdfs:subPropertyOf schema:familyName ; rdfs:label "last name"@en ; rdfs:comment "Family name."@en ; rdfs:domain fb:Player ; rdfs:range xsd:string .
fb:dateOfBirth a owl:DatatypeProperty , owl:FunctionalProperty ; rdfs:subPropertyOf schema:birthDate ; rdfs:label "date of birth"@en ; rdfs:comment "Date of birth."@en ; rdfs:domain fb:Player ; rdfs:range xsd:date .
fb:birthCity a owl:DatatypeProperty ; rdfs:label "birth city"@en ; rdfs:comment "City of birth as free text."@en ; rdfs:domain fb:Player ; rdfs:range xsd:string .
fb:heightCm a owl:DatatypeProperty ; rdfs:label "height (cm)"@en ; rdfs:comment "Height in centimetres."@en ; rdfs:domain fb:Player ; rdfs:range xsd:integer .
fb:preferredFoot a owl:DatatypeProperty ; rdfs:label "preferred foot"@en ; rdfs:comment "left, right or both."@en ; rdfs:domain fb:Player ; rdfs:range xsd:string .
fb:internationalCaps a owl:DatatypeProperty ; rdfs:label "international caps"@en ; rdfs:comment "Number of international appearances."@en ; rdfs:domain fb:Player ; rdfs:range xsd:integer .
fb:internationalGoals a owl:DatatypeProperty ; rdfs:label "international goals"@en ; rdfs:comment "Number of international goals."@en ; rdfs:domain fb:Player ; rdfs:range xsd:integer .
fb:contractExpires a owl:DatatypeProperty ; rdfs:label "contract expires"@en ; rdfs:comment "Contract expiration date."@en ; rdfs:domain fb:Player ; rdfs:range xsd:date .
fb:agent a owl:DatatypeProperty ; rdfs:label "agent"@en ; rdfs:comment "Name of the player's agent."@en ; rdfs:domain fb:Player ; rdfs:range xsd:string .
fb:currentMarketValueEUR a owl:DatatypeProperty ; rdfs:label "current market value (EUR)"@en ; rdfs:comment "Latest market value in euros."@en ; rdfs:domain fb:Player ; rdfs:range xsd:decimal .
fb:highestMarketValueEUR a owl:DatatypeProperty ; rdfs:label "highest market value (EUR)"@en ; rdfs:comment "Highest market value ever recorded, in euros."@en ; rdfs:domain fb:Player ; rdfs:range xsd:decimal .
fb:matchDate a owl:DatatypeProperty ; rdfs:label "match date"@en ; rdfs:comment "Date a match was played."@en ; rdfs:domain fb:Match ; rdfs:range xsd:date .
fb:round a owl:DatatypeProperty ; rdfs:label "round"@en ; rdfs:comment "Round or matchday label."@en ; rdfs:domain fb:Match ; rdfs:range xsd:string .
fb:homeScore a owl:DatatypeProperty ; rdfs:label "home score"@en ; rdfs:comment "Goals scored by the home team."@en ; rdfs:domain fb:Match ; rdfs:range xsd:integer .
fb:awayScore a owl:DatatypeProperty ; rdfs:label "away score"@en ; rdfs:comment "Goals scored by the away team."@en ; rdfs:domain fb:Match ; rdfs:range xsd:integer .
fb:attendance a owl:DatatypeProperty ; rdfs:label "attendance"@en ; rdfs:comment "Number of spectators."@en ; rdfs:domain fb:Match ; rdfs:range xsd:integer .
fb:homeFormation a owl:DatatypeProperty ; rdfs:label "home formation"@en ; rdfs:comment "Formation of the home team."@en ; rdfs:domain fb:Match ; rdfs:range xsd:string .
fb:awayFormation a owl:DatatypeProperty ; rdfs:label "away formation"@en ; rdfs:comment "Formation of the away team."@en ; rdfs:domain fb:Match ; rdfs:range xsd:string .
fb:startYear a owl:DatatypeProperty ; rdfs:label "start year"@en ; rdfs:comment "Start year of a season as coded in the source."@en ; rdfs:domain fb:Season ; rdfs:range xsd:integer .
fb:stadiumSeats a owl:DatatypeProperty ; rdfs:label "stadium seats"@en ; rdfs:comment "Seating capacity."@en ; rdfs:domain fb:Stadium ; rdfs:range xsd:integer .
fb:countryCode a owl:DatatypeProperty ; rdfs:label "country code"@en ; rdfs:comment "Transfermarkt country code."@en ; rdfs:domain fb:Country ; rdfs:range xsd:string .
fb:confederation a owl:DatatypeProperty ; rdfs:label "confederation"@en ; rdfs:comment "Football confederation."@en ; rdfs:range xsd:string .
fb:competitionType a owl:DatatypeProperty ; rdfs:label "competition type"@en ; rdfs:comment "domestic_league, domestic_cup, international_cup, national_team_competition or other."@en ; rdfs:domain fb:Competition ; rdfs:range xsd:string .
fb:competitionCode a owl:DatatypeProperty ; rdfs:label "competition code"@en ; rdfs:comment "Transfermarkt competition code."@en ; rdfs:domain fb:Competition ; rdfs:range xsd:string .
fb:fifaRanking a owl:DatatypeProperty ; rdfs:label "FIFA ranking"@en ; rdfs:comment "FIFA world ranking of a national team."@en ; rdfs:domain fb:NationalTeam ; rdfs:range xsd:integer .
fb:squadSize a owl:DatatypeProperty ; rdfs:label "squad size"@en ; rdfs:comment "Number of players in the squad."@en ; rdfs:domain fb:Team ; rdfs:range xsd:integer .
fb:averageAge a owl:DatatypeProperty ; rdfs:label "average age"@en ; rdfs:comment "Average age of the squad."@en ; rdfs:domain fb:Team ; rdfs:range xsd:decimal .
fb:foreignersNumber a owl:DatatypeProperty ; rdfs:label "foreigners number"@en ; rdfs:comment "Number of foreign players in the squad."@en ; rdfs:domain fb:Team ; rdfs:range xsd:integer .
fb:foreignersPercentage a owl:DatatypeProperty ; rdfs:label "foreigners percentage"@en ; rdfs:comment "Share of foreign players in the squad."@en ; rdfs:domain fb:Team ; rdfs:range xsd:decimal .
fb:nationalTeamPlayers a owl:DatatypeProperty ; rdfs:label "national team players"@en ; rdfs:comment "Number of squad members with national team caps."@en ; rdfs:domain fb:Club ; rdfs:range xsd:integer .
fb:totalMarketValueEUR a owl:DatatypeProperty ; rdfs:label "total market value (EUR)"@en ; rdfs:comment "Squad market value in euros."@en ; rdfs:domain fb:Team ; rdfs:range xsd:decimal .
fb:netTransferRecordEUR a owl:DatatypeProperty ; rdfs:label "net transfer record (EUR)"@en ; rdfs:comment "Net transfer spending balance in euros (negative = net spend)."@en ; rdfs:domain fb:Club ; rdfs:range xsd:decimal .
fb:lastSeason a owl:DatatypeProperty ; rdfs:label "last season"@en ; rdfs:comment "Latest season for which the team data was scraped."@en ; rdfs:domain fb:Team ; rdfs:range xsd:integer .
fb:goals a owl:DatatypeProperty ; rdfs:label "goals"@en ; rdfs:comment "Goals scored in an appearance."@en ; rdfs:domain fb:Appearance ; rdfs:range xsd:integer .
fb:assists a owl:DatatypeProperty ; rdfs:label "assists"@en ; rdfs:comment "Assists in an appearance."@en ; rdfs:domain fb:Appearance ; rdfs:range xsd:integer .
fb:minutesPlayed a owl:DatatypeProperty ; rdfs:label "minutes played"@en ; rdfs:comment "Minutes played in an appearance."@en ; rdfs:domain fb:Appearance ; rdfs:range xsd:integer .
fb:yellowCards a owl:DatatypeProperty ; rdfs:label "yellow cards"@en ; rdfs:comment "Yellow cards received in an appearance."@en ; rdfs:domain fb:Appearance ; rdfs:range xsd:integer .
fb:redCards a owl:DatatypeProperty ; rdfs:label "red cards"@en ; rdfs:comment "Red cards received in an appearance."@en ; rdfs:domain fb:Appearance ; rdfs:range xsd:integer .
fb:minute a owl:DatatypeProperty ; rdfs:label "minute"@en ; rdfs:comment "Match minute of an event."@en ; rdfs:domain fb:MatchEvent ; rdfs:range xsd:integer .
fb:cardType a owl:DatatypeProperty ; rdfs:label "card type"@en ; rdfs:comment "Yellow card, Second yellow or Red card."@en ; rdfs:domain fb:Card ; rdfs:range xsd:string .
fb:scored a owl:DatatypeProperty ; rdfs:label "scored"@en ; rdfs:comment "Whether a shootout kick was scored."@en ; rdfs:domain fb:PenaltyShootoutKick ; rdfs:range xsd:boolean .
fb:transferDate a owl:DatatypeProperty ; rdfs:label "transfer date"@en ; rdfs:comment "Date of the transfer."@en ; rdfs:domain fb:Transfer ; rdfs:range xsd:date .
fb:transferSeason a owl:DatatypeProperty ; rdfs:label "transfer season"@en ; rdfs:comment "Season label such as 23/24."@en ; rdfs:domain fb:Transfer ; rdfs:range xsd:string .
fb:transferFee a owl:DatatypeProperty ; rdfs:label "transfer fee (EUR)"@en ; rdfs:comment "Transfer fee in euros; only present when positive."@en ; rdfs:domain fb:Transfer ; rdfs:range xsd:decimal .
fb:marketValueAtTransferEUR a owl:DatatypeProperty ; rdfs:label "market value at transfer (EUR)"@en ; rdfs:comment "Market value when the transfer happened."@en ; rdfs:domain fb:Transfer ; rdfs:range xsd:decimal .
fb:valuationDate a owl:DatatypeProperty ; rdfs:label "valuation date"@en ; rdfs:comment "Date of a market valuation."@en ; rdfs:domain fb:MarketValuation ; rdfs:range xsd:date .
fb:valueEUR a owl:DatatypeProperty ; rdfs:label "value (EUR)"@en ; rdfs:comment "Valuation in euros."@en ; rdfs:domain fb:MarketValuation ; rdfs:range xsd:decimal .
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_ontology.py -v`
Expected: all PASS (≥60 properties is satisfied by the list above; if the count assertion fails, count the definitions, do not lower the threshold without checking for a lost property).

- [ ] **Step 5: Commit**

```bash
git add ontology/football.ttl tests/test_ontology.py
git commit -m "feat: football ontology"
```

---

### Task 5: Reference builder (countries, national teams, competitions)

**Files:**
- Create: `src/builders/__init__.py` (empty), `src/builders/reference.py`, `tests/test_reference.py`

**Interfaces:**
- Consumes: `common` (`BuildCtx`, `lit`, `iri`, `t_int`, `t_dec`, `named_node`, `clean`), `ctx.scope.national_ids`, `ctx.scope.national_names`.
- Produces: `reference.build(ctx) -> int` writing `reference.ttl`; every builder in `src/builders` follows the same `build(ctx) -> int` (triples written) contract.

- [ ] **Step 1: Write the failing test `tests/test_reference.py`**

```python
from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from builders import reference
from helpers import FB, R, load_ttl


def build(ctx):
    n = reference.build(ctx)
    return n, load_ttl(ctx.out_dir / "reference.ttl")


def test_countries_and_national_teams(ctx):
    n, g = build(ctx)
    england = URIRef(f"{R}country/189")
    assert (england, RDF.type, URIRef(FB + "Country")) in g
    assert (england, RDFS.label, Literal("England", lang="en")) in g
    nt = URIRef(f"{R}national-team/3299")
    assert (nt, RDF.type, URIRef(FB + "NationalTeam")) in g
    assert (nt, URIRef(FB + "country"), england) in g
    assert (nt, URIRef(FB + "fifaRanking"), Literal("4", datatype=XSD.integer)) in g
    assert (nt, URIRef(FB + "averageAge"), Literal("27.1", datatype=XSD.decimal)) in g
    assert (nt, URIRef(FB + "managedBy"), URIRef(f"{R}manager/Gareth_Southgate")) in g
    assert n == len(g)


def test_missing_national_team_gets_minimal_node(ctx):
    _, g = build(ctx)
    minimal = URIRef(f"{R}national-team/9999")
    assert (minimal, RDF.type, URIRef(FB + "NationalTeam")) in g
    assert (minimal, RDFS.label, Literal("Serbia and Montenegro", lang="und")) in g


def test_competitions_international_has_no_country(ctx):
    _, g = build(ctx)
    gb1, wc = URIRef(f"{R}competition/GB1"), URIRef(f"{R}competition/FIWC")
    assert (gb1, URIRef(FB + "country"), URIRef(f"{R}country/189")) in g
    assert (gb1, URIRef(FB + "competitionType"), Literal("domestic_league")) in g
    assert (wc, RDF.type, URIRef(FB + "Competition")) in g
    assert not list(g.objects(wc, URIRef(FB + "country")))   # country_id = -1


def test_optional_cells_do_not_create_triples(ctx):
    _, g = build(ctx)
    turkiye = URIRef(f"{R}country/50")
    assert not list(g.objects(turkiye, URIRef("http://www.w3.org/2000/01/rdf-schema#seeAlso")))
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_reference.py -v`
Expected: FAIL (`No module named 'builders'`).

- [ ] **Step 3: Write `src/builders/__init__.py` (empty) and `src/builders/reference.py`**

```python
"""countries.csv, national_teams.csv, competitions.csv -> reference.ttl"""
from common import clean, iri, lit, named_node, t_dec, t_int


def build(ctx):
    u = ctx.uris
    with ctx.writer("reference.ttl") as w:
        for r in ctx.csv("countries.csv"):
            if not clean(r["country_id"]):
                continue
            w.node(u.res("country", r["country_id"]),
                   ("a", "fb:Country"),
                   ("rdfs:label", lit(r["country_name"], "en")),
                   ("fb:countryCode", lit(r["country_code"])),
                   ("fb:confederation", lit(r["confederation"])),
                   ("rdfs:seeAlso", iri(r["url"])))

        known = set()
        for r in ctx.csv("national_teams.csv"):
            nid = clean(r["national_team_id"])
            if not nid:
                continue
            known.add(nid)
            manager = named_node(ctx, w, "manager", "fb:Manager", r["coach_name"])
            w.node(u.res("national-team", nid),
                   ("a", "fb:NationalTeam"),
                   ("rdfs:label", lit(r["name"], "und")),
                   ("fb:country", u.res("country", clean(r["country_id"]))),
                   ("fb:confederation", lit(r["confederation"])),
                   ("fb:squadSize", t_int(r["squad_size"])),
                   ("fb:averageAge", t_dec(r["average_age"])),
                   ("fb:foreignersNumber", t_int(r["foreigners_number"])),
                   ("fb:foreignersPercentage", t_dec(r["foreigners_percentage"])),
                   ("fb:totalMarketValueEUR", t_dec(r["total_market_value"])),
                   ("fb:managedBy", manager),
                   ("fb:fifaRanking", t_int(r["fifa_ranking"])),
                   ("fb:lastSeason", t_int(r["last_season"])),
                   ("foaf:depiction", iri(r["team_image_url"])),
                   ("rdfs:seeAlso", iri(r["url"])))

        for nid in sorted(ctx.scope.national_ids - known):
            ctx.notes["national_team_minimal"] += 1
            w.node(u.res("national-team", nid),
                   ("a", "fb:NationalTeam"),
                   ("rdfs:label", lit(ctx.scope.national_names.get(nid), "und")))

        for r in ctx.csv("competitions.csv"):
            cid = clean(r["competition_id"])
            if not cid:
                continue
            country_id = clean(r["country_id"])
            country = u.res("country", country_id) if country_id and country_id != "-1" else None
            w.node(u.res("competition", cid),
                   ("a", "fb:Competition"),
                   ("rdfs:label", lit(r["name"], "und")),
                   ("fb:competitionCode", lit(r["competition_code"])),
                   ("fb:competitionType", lit(r["type"])),
                   ("fb:confederation", lit(r["confederation"])),
                   ("fb:country", country),
                   ("rdfs:seeAlso", iri(r["url"])))
    return w.count
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_reference.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/builders tests/test_reference.py
git commit -m "feat: reference builder (countries, national teams, competitions)"
```

---

### Task 6: Clubs and players builders

**Files:**
- Create: `src/countries.py`, `src/builders/clubs.py`, `src/builders/players.py`, `tests/test_clubs_players.py`

**Interfaces:**
- Consumes: `common` helpers; `ctx.scope.club_ids`, `club_names`, `player_ids`, `national_ids`.
- Produces: `countries.CountryResolver(ctx)` with `uri(name)->str|None`, `all_names()->dict[str,str]` (name → `<country URI>` for every `countries.csv` name plus every extra name resolved so far), `write_extra(w)`; `clubs.build(ctx)->int` (writes `clubs.ttl`), `players.build(ctx)->int` (writes `players.ttl`, sets `ctx.countries`).

- [ ] **Step 1: Write the failing test `tests/test_clubs_players.py`**

```python
from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, SKOS, XSD

from builders import clubs, players
from countries import CountryResolver
from helpers import FB, R, load_ttl


def test_full_and_minimal_clubs(ctx):
    n = clubs.build(ctx)
    g = load_ttl(ctx.out_dir / "clubs.ttl")
    arsenal = URIRef(f"{R}club/11")
    assert (arsenal, RDFS.label, Literal("Arsenal FC", lang="und")) in g
    assert (arsenal, URIRef(FB + "netTransferRecordEUR"), Literal("5900000", datatype=XSD.decimal)) in g
    assert (arsenal, URIRef(FB + "domesticCompetition"), URIRef(f"{R}competition/GB1")) in g
    assert (arsenal, URIRef(FB + "homeStadium"), URIRef(f"{R}stadium/Emirates_Stadium")) in g
    assert (URIRef(f"{R}stadium/Emirates_Stadium"), URIRef(FB + "stadiumSeats"),
            Literal("60704", datatype=XSD.integer)) in g
    # clubs 148 and 999 are not in clubs.csv -> minimal nodes with names from other tables
    assert (URIRef(f"{R}club/148"), RDFS.label, Literal("Tottenham Hotspur", lang="und")) in g
    assert (URIRef(f"{R}club/999"), RDFS.label, Literal("Hale End", lang="und")) in g
    assert (URIRef(f"{R}club/999"), RDF.type, URIRef(FB + "Club")) in g
    assert ctx.notes["club_minimal"] == 2
    assert n == len(g)


def test_player_values_and_nulls(ctx):
    players.build(ctx)
    g = load_ttl(ctx.out_dir / "players.ttl")
    p = URIRef(f"{R}player/10")
    assert (p, URIRef(FB + "dateOfBirth"), Literal("2001-09-05", datatype=XSD.date)) in g
    assert (p, URIRef(FB + "birthCity"), Literal("London")) in g           # trimmed
    assert (p, URIRef(FB + "heightCm"), Literal("178", datatype=XSD.integer)) in g
    assert (p, URIRef(FB + "playsFor"), URIRef(f"{R}club/11")) in g
    assert (p, URIRef(FB + "representsNationalTeam"), URIRef(f"{R}national-team/3299")) in g
    assert (p, URIRef(FB + "citizenOf"), URIRef(f"{R}country/189")) in g
    assert (p, URIRef(FB + "position"), URIRef(f"{R}position/Attack")) in g
    assert (p, URIRef(FB + "subPosition"), URIRef(f"{R}position/Right_Winger")) in g
    assert (URIRef(f"{R}position/Right_Winger"), SKOS.broader, URIRef(f"{R}position/Attack")) in g
    son = URIRef(f"{R}player/20")                                          # almost all cells empty
    assert not list(g.objects(son, URIRef(FB + "dateOfBirth")))
    assert not list(g.objects(son, URIRef(FB + "position")))               # position "Missing"
    assert not list(g.objects(son, URIRef(FB + "heightCm")))


def test_out_of_scope_player_excluded_and_unknown_country_minimal(ctx):
    players.build(ctx)
    g = load_ttl(ctx.out_dir / "players.ttl")
    assert not list(g.triples((URIRef(f"{R}player/30"), None, None)))
    extra = URIRef(f"{R}country/n-Korea%2C_South")      # Uris.res percent-encodes the comma
    assert (URIRef(f"{R}player/20"), URIRef(FB + "citizenOf"), extra) in g
    assert (extra, RDF.type, URIRef(FB + "Country")) in g


def test_player_missing_from_players_csv_gets_minimal_node(ctx):
    ctx.scope.player_ids.add("777")
    players.build(ctx)
    g = load_ttl(ctx.out_dir / "players.ttl")
    assert (URIRef(f"{R}player/777"), RDF.type, URIRef(FB + "Player")) in g
    assert ctx.notes["player_minimal"] == 1


def test_country_resolver_alias_and_names(ctx):
    r = CountryResolver(ctx)
    assert r.uri("Turkey") == f"<{R}country/50>"      # alias to Türkiye
    assert r.uri("England") == f"<{R}country/189>"
    assert r.uri("") is None and r.uri(None) is None
    assert "England" in r.all_names()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_clubs_players.py -v`
Expected: FAIL (`No module named 'countries'`).

- [ ] **Step 3: Write `src/countries.py`**

```python
"""Resolve country names (as used in players.csv) to country URIs."""
from common import clean, lit, slug

ALIASES = {"Turkey": "Türkiye"}


class CountryResolver:
    def __init__(self, ctx):
        self.uris = ctx.uris
        self.by_name = {}
        for r in ctx.csv("countries.csv"):
            name, cid = clean(r["country_name"]), clean(r["country_id"])
            if name and cid:
                self.by_name[name] = self.uris.res("country", cid)
        self.extra = {}

    def uri(self, name):
        name = clean(name)
        if name is None:
            return None
        name = ALIASES.get(name, name)
        if name in self.by_name:
            return self.by_name[name]
        if name not in self.extra:
            self.extra[name] = self.uris.res("country", "n-" + slug(name))
        return self.extra[name]

    def all_names(self):
        return {**self.by_name, **self.extra}

    def write_extra(self, w):
        for name, uri in sorted(self.extra.items()):
            w.node(uri, ("a", "fb:Country"), ("rdfs:label", lit(name, "en")))
```

- [ ] **Step 4: Write `src/builders/clubs.py`**

```python
"""clubs.csv (+ scope) -> clubs.ttl"""
from common import clean, iri, lit, named_node, parse_net_transfer, t_dec, t_int, typed


def build(ctx):
    u = ctx.uris
    rows = {clean(r["club_id"]): r for r in ctx.csv("clubs.csv")}
    with ctx.writer("clubs.ttl") as w:
        for cid in sorted(ctx.scope.club_ids):
            uri = u.res("club", cid)
            r = rows.get(cid)
            if r is None:
                ctx.notes["club_minimal"] += 1
                w.node(uri, ("a", "fb:Club"), ("rdfs:label", lit(ctx.scope.club_names.get(cid), "und")))
                continue
            stadium = named_node(ctx, w, "stadium", "fb:Stadium", r["stadium_name"])
            if stadium:
                w.node(stadium, ("fb:stadiumSeats", t_int(r["stadium_seats"])))
            manager = named_node(ctx, w, "manager", "fb:Manager", r["coach_name"])
            comp = clean(r["domestic_competition_id"])
            w.node(uri,
                   ("a", "fb:Club"),
                   ("rdfs:label", lit(r["name"], "und")),
                   ("fb:domesticCompetition", u.res("competition", comp) if comp else None),
                   ("fb:squadSize", t_int(r["squad_size"])),
                   ("fb:averageAge", t_dec(r["average_age"])),
                   ("fb:foreignersNumber", t_int(r["foreigners_number"])),
                   ("fb:foreignersPercentage", t_dec(r["foreigners_percentage"])),
                   ("fb:nationalTeamPlayers", t_int(r["national_team_players"])),
                   ("fb:totalMarketValueEUR", t_dec(r["total_market_value"])),
                   ("fb:netTransferRecordEUR", typed(parse_net_transfer(r["net_transfer_record"]), "xsd:decimal")),
                   ("fb:homeStadium", stadium),
                   ("fb:managedBy", manager),
                   ("fb:lastSeason", t_int(r["last_season"])),
                   ("rdfs:seeAlso", iri(r["url"])))
    return w.count
```

- [ ] **Step 5: Write `src/builders/players.py`**

```python
"""players.csv (+ scope) -> players.ttl (also positions and non-listed countries)"""
from common import clean, iri, lit, slug, t_date, t_dec, t_int
from countries import CountryResolver


def _position(ctx, w, name, broader=None):
    name = clean(name)
    if name is None or name == "Missing":
        return None
    uri = ctx.uris.res("position", slug(name))
    if ctx.once("position", name):
        w.node(uri, ("a", ["fb:Position", "skos:Concept"]),
               ("rdfs:label", lit(name, "en")),
               ("skos:broader", broader))
    return uri


def build(ctx):
    u = ctx.uris
    ctx.countries = countries = CountryResolver(ctx)
    national_ids = {clean(r["national_team_id"]) for r in ctx.csv("national_teams.csv")}
    national_ids |= ctx.scope.national_ids
    seen_players = set()
    with ctx.writer("players.ttl") as w:
        for r in ctx.csv("players.csv"):
            pid = clean(r["player_id"])
            if pid not in ctx.scope.player_ids:
                continue
            seen_players.add(pid)
            position = _position(ctx, w, r["position"])
            sub = _position(ctx, w, r["sub_position"], broader=position)
            nat = clean(r["current_national_team_id"])
            w.node(u.res("player", pid),
                   ("a", "fb:Player"),
                   ("rdfs:label", lit(r["name"], "und")),
                   ("fb:firstName", lit(r["first_name"], "und")),
                   ("fb:lastName", lit(r["last_name"], "und")),
                   ("fb:dateOfBirth", t_date(r["date_of_birth"])),
                   ("fb:bornIn", countries.uri(r["country_of_birth"])),
                   ("fb:birthCity", lit(r["city_of_birth"])),
                   ("fb:citizenOf", countries.uri(r["country_of_citizenship"])),
                   ("fb:position", position),
                   ("fb:subPosition", sub),
                   ("fb:preferredFoot", lit(r["foot"])),
                   ("fb:heightCm", t_int(r["height_in_cm"])),
                   ("fb:currentMarketValueEUR", t_dec(r["market_value_in_eur"])),
                   ("fb:highestMarketValueEUR", t_dec(r["highest_market_value_in_eur"])),
                   ("fb:playsFor", u.res("club", clean(r["current_club_id"]))),
                   ("fb:representsNationalTeam", u.res("national-team", nat) if nat in national_ids else None),
                   ("fb:internationalCaps", t_int(r["international_caps"])),
                   ("fb:internationalGoals", t_int(r["international_goals"])),
                   ("fb:contractExpires", t_date(r["contract_expiration_date"])),
                   ("fb:agent", lit(r["agent_name"])),
                   ("foaf:depiction", iri(r["image_url"])),
                   ("rdfs:seeAlso", iri(r["url"])))
        for pid in sorted(ctx.scope.player_ids - seen_players):
            ctx.notes["player_minimal"] += 1
            w.node(u.res("player", pid), ("a", "fb:Player"))
        countries.write_extra(w)
    return w.count
```

- [ ] **Step 6: Run tests**

Run: `.venv/bin/pytest tests/test_clubs_players.py -v`
Expected: all PASS. If `test_clubs_and_...` counts differ, print `ctx.scope.club_ids` and compare with Task 3's expectations before changing assertions.

- [ ] **Step 7: Verify the alias against the real data**

Run:
```bash
.venv/bin/python - <<'EOF'
import csv
names = {r["country_name"] for r in csv.DictReader(open("datasets/countries.csv", encoding="utf-8"))}
print("Türkiye" in names, "Turkey" in names)
EOF
```
Expected: `True False`. If `Türkiye` is `False`, print the closest names (`[n for n in names if n.startswith("T")]`) and fix `ALIASES` in `src/countries.py` accordingly.

- [ ] **Step 8: Commit**

```bash
git add src/countries.py src/builders/clubs.py src/builders/players.py tests/test_clubs_players.py
git commit -m "feat: clubs and players builders, country name resolver"
```

---

### Task 7: Matches builder

**Files:**
- Create: `src/builders/matches.py`, `tests/test_matches.py`

**Interfaces:**
- Consumes: `ctx.scope.game_ids`, `ctx.scope.game_kind`, `ctx.uris.team`, `named_node`.
- Produces: `matches.build(ctx)->int` writing `matches.ttl` (Match, Season, Referee, Stadium nodes).

- [ ] **Step 1: Write the failing test `tests/test_matches.py`**

```python
from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from builders import matches
from helpers import FB, R, load_ttl


def test_club_match(ctx):
    n = matches.build(ctx)
    g = load_ttl(ctx.out_dir / "matches.ttl")
    m = URIRef(f"{R}match/100")
    assert (m, RDF.type, URIRef(FB + "Match")) in g
    assert (m, RDFS.label, Literal("Arsenal FC vs Tottenham Hotspur", lang="und")) in g
    assert (m, URIRef(FB + "homeTeam"), URIRef(f"{R}club/11")) in g
    assert (m, URIRef(FB + "awayTeam"), URIRef(f"{R}club/148")) in g
    assert (m, URIRef(FB + "homeScore"), Literal("2", datatype=XSD.integer)) in g
    assert (m, URIRef(FB + "matchDate"), Literal("2023-08-12", datatype=XSD.date)) in g
    assert (m, URIRef(FB + "inCompetition"), URIRef(f"{R}competition/GB1")) in g
    assert (m, URIRef(FB + "inSeason"), URIRef(f"{R}season/2023")) in g
    assert (m, URIRef(FB + "hostedAt"), URIRef(f"{R}stadium/Emirates_Stadium")) in g
    assert (m, URIRef(FB + "refereedBy"), URIRef(f"{R}referee/Michael_Oliver")) in g
    assert (m, URIRef(FB + "homeFormation"), Literal("4-3-3")) in g
    assert not list(g.objects(m, URIRef(FB + "awayFormation")))        # empty cell
    assert (URIRef(f"{R}season/2023"), URIRef(FB + "startYear"), Literal("2023", datatype=XSD.integer)) in g
    assert n == len(g)


def test_national_match_uses_national_team_uris_and_skips_empty_cells(ctx):
    matches.build(ctx)
    g = load_ttl(ctx.out_dir / "matches.ttl")
    m = URIRef(f"{R}match/200")
    assert (m, URIRef(FB + "homeTeam"), URIRef(f"{R}national-team/3299")) in g
    assert (m, URIRef(FB + "awayTeam"), URIRef(f"{R}national-team/9999")) in g
    assert not list(g.objects(m, URIRef(FB + "hostedAt")))             # stadium ""
    assert not list(g.objects(m, URIRef(FB + "refereedBy")))           # referee ""


def test_out_of_scope_match_skipped(ctx):
    matches.build(ctx)
    g = load_ttl(ctx.out_dir / "matches.ttl")
    assert not list(g.triples((URIRef(f"{R}match/101"), None, None)))
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_matches.py -v`
Expected: FAIL (`cannot import name 'matches'`).

- [ ] **Step 3: Write `src/builders/matches.py`**

```python
"""games.csv -> matches.ttl"""
from common import clean, iri, lit, named_node, t_date, t_int


def build(ctx):
    u = ctx.uris
    with ctx.writer("matches.ttl") as w:
        for r in ctx.csv("games.csv"):
            gid = r["game_id"]
            if gid not in ctx.scope.game_ids:
                continue
            kind = ctx.scope.game_kind[gid]
            home, away = u.team(kind, r["home_club_id"]), u.team(kind, r["away_club_id"])
            if home is None or away is None:
                ctx.notes["match_missing_team"] += 1
            season = clean(r["season"])
            season_uri = u.res("season", season)
            if season_uri and ctx.once("season", season):
                w.node(season_uri, ("a", "fb:Season"),
                       ("rdfs:label", lit(f"Season {season}")),
                       ("fb:startYear", t_int(season)))
            stadium = named_node(ctx, w, "stadium", "fb:Stadium", r["stadium"])
            referee = named_node(ctx, w, "referee", "fb:Referee", r["referee"])
            hn, an = clean(r["home_club_name"]), clean(r["away_club_name"])
            label = f"{hn} vs {an}" if hn and an else None
            w.node(u.res("match", gid),
                   ("a", "fb:Match"),
                   ("rdfs:label", lit(label, "und")),
                   ("fb:inCompetition", u.res("competition", clean(r["competition_id"]))),
                   ("fb:inSeason", season_uri),
                   ("fb:matchDate", t_date(r["date"])),
                   ("fb:round", lit(r["round"])),
                   ("fb:homeTeam", home),
                   ("fb:awayTeam", away),
                   ("fb:homeScore", t_int(r["home_club_goals"])),
                   ("fb:awayScore", t_int(r["away_club_goals"])),
                   ("fb:hostedAt", stadium),
                   ("fb:attendance", t_int(r["attendance"])),
                   ("fb:refereedBy", referee),
                   ("fb:homeFormation", lit(r["home_club_formation"])),
                   ("fb:awayFormation", lit(r["away_club_formation"])),
                   ("rdfs:seeAlso", iri(r["url"])))
    return w.count
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_matches.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/builders/matches.py tests/test_matches.py
git commit -m "feat: matches builder (matches, seasons, referees)"
```

---

### Task 8: Appearances and events builders

**Files:**
- Create: `src/builders/facts.py`, `tests/test_facts.py`

**Interfaces:**
- Consumes: `ctx.scope.game_ids`, `game_kind`, `ctx.uris.team`.
- Produces: `facts.build_appearances(ctx)->int` (writes `appearances.ttl`), `facts.build_events(ctx)->int` (writes `events.ttl`), `facts.split_description(desc)->(head|None, tail|None)`.

- [ ] **Step 1: Write the failing test `tests/test_facts.py`**

```python
from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from builders import facts
from helpers import FB, R, load_ttl


def test_split_description():
    assert facts.split_description("1. Yellow card  , Foul") == ("1. Yellow card", "Foul")
    assert facts.split_description(", Tactical") == (None, "Tactical")
    assert facts.split_description("") == (None, None)
    assert facts.split_description(None) == (None, None)


def test_appearances(ctx):
    n = facts.build_appearances(ctx)
    g = load_ttl(ctx.out_dir / "appearances.ttl")
    a = URIRef(f"{R}appearance/100_10")
    assert (a, RDF.type, URIRef(FB + "Appearance")) in g
    assert (a, URIRef(FB + "appearanceOf"), URIRef(f"{R}player/10")) in g
    assert (a, URIRef(FB + "inMatch"), URIRef(f"{R}match/100")) in g
    assert (a, URIRef(FB + "forTeam"), URIRef(f"{R}club/11")) in g
    assert (a, URIRef(FB + "goals"), Literal("1", datatype=XSD.integer)) in g
    assert (a, URIRef(FB + "minutesPlayed"), Literal("90", datatype=XSD.integer)) in g
    # World Cup appearance is attributed to the national team
    wc = URIRef(f"{R}appearance/200_10")
    assert (wc, URIRef(FB + "forTeam"), URIRef(f"{R}national-team/3299")) in g
    # appearance in an out-of-scope game is skipped
    assert not list(g.triples((URIRef(f"{R}appearance/101_30"), None, None)))
    assert n == len(g)


def test_events(ctx):
    n = facts.build_events(ctx)
    g = load_ttl(ctx.out_dir / "events.ttl")
    goal = URIRef(f"{R}event/e1")
    assert (goal, RDF.type, URIRef(FB + "Goal")) in g
    assert (goal, URIRef(FB + "byPlayer"), URIRef(f"{R}player/10")) in g
    assert (goal, URIRef(FB + "assistedBy"), URIRef(f"{R}player/20")) in g
    assert (goal, URIRef(FB + "minute"), Literal("10", datatype=XSD.integer)) in g
    assert (goal, URIRef(FB + "forTeam"), URIRef(f"{R}club/11")) in g
    card = URIRef(f"{R}event/e2")
    assert (card, RDF.type, URIRef(FB + "Card")) in g
    assert (card, URIRef(FB + "cardType"), Literal("Yellow card")) in g
    assert (card, RDFS.comment, Literal("Foul")) in g
    sub = URIRef(f"{R}event/e3")
    assert (sub, RDF.type, URIRef(FB + "Substitution")) in g
    assert (sub, URIRef(FB + "playerOut"), URIRef(f"{R}player/10")) in g
    assert (sub, URIRef(FB + "playerIn"), URIRef(f"{R}player/20")) in g
    kick = URIRef(f"{R}event/e4")
    assert (kick, RDF.type, URIRef(FB + "PenaltyShootoutKick")) in g
    assert (kick, URIRef(FB + "scored"), Literal(True)) in g
    assert (kick, URIRef(FB + "forTeam"), URIRef(f"{R}national-team/3299")) in g
    assert n == len(g)


def test_unknown_event_type_is_counted_not_fatal(ctx, data_dir):
    from helpers import put
    put(data_dir, "game_events.csv", [
        {"game_event_id": "x1", "game_id": "100", "minute": "1", "type": "VAR", "club_id": "11", "player_id": "10"},
    ])
    facts.build_events(ctx)
    assert ctx.notes["event_unknown_type"] == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_facts.py -v`
Expected: FAIL (`cannot import name 'facts'`).

- [ ] **Step 3: Write `src/builders/facts.py`**

```python
"""appearances.csv -> appearances.ttl ; game_events.csv -> events.ttl"""
import re

from common import clean, lit, t_int, typed

EVENT_CLASS = {
    "Goals": "fb:Goal",
    "Cards": "fb:Card",
    "Substitutions": "fb:Substitution",
    "Shootout": "fb:PenaltyShootoutKick",
}


def split_description(desc):
    desc = clean(desc)
    if desc is None:
        return None, None
    head, _, tail = desc.partition(",")
    return clean(head), clean(tail)


def build_appearances(ctx):
    u = ctx.uris
    with ctx.writer("appearances.ttl") as w:
        for r in ctx.csv("appearances.csv"):
            gid = r["game_id"]
            if gid not in ctx.scope.game_ids:
                continue
            kind = ctx.scope.game_kind[gid]
            w.node(u.res("appearance", r["appearance_id"]),
                   ("a", "fb:Appearance"),
                   ("fb:appearanceOf", u.res("player", r["player_id"])),
                   ("fb:inMatch", u.res("match", gid)),
                   ("fb:forTeam", u.team(kind, r["player_club_id"])),
                   ("fb:goals", t_int(r["goals"])),
                   ("fb:assists", t_int(r["assists"])),
                   ("fb:minutesPlayed", t_int(r["minutes_played"])),
                   ("fb:yellowCards", t_int(r["yellow_cards"])),
                   ("fb:redCards", t_int(r["red_cards"])))
    return w.count


def build_events(ctx):
    u = ctx.uris
    with ctx.writer("events.ttl") as w:
        for r in ctx.csv("game_events.csv"):
            gid = r["game_id"]
            if gid not in ctx.scope.game_ids:
                continue
            typ = r["type"]
            cls = EVENT_CLASS.get(typ)
            if cls is None:
                ctx.notes["event_unknown_type"] += 1
                continue
            kind = ctx.scope.game_kind[gid]
            head, tail = split_description(r["description"])
            player = u.res("player", clean(r["player_id"]))
            card_type = re.sub(r"^\d+\.\s*", "", head) if typ == "Cards" and head else None
            scored = None
            if typ == "Shootout" and tail:
                scored = typed("true" if tail.lower().startswith("scored") else "false", "xsd:boolean")
            w.node(u.res("event", r["game_event_id"]),
                   ("a", cls),
                   ("fb:inMatch", u.res("match", gid)),
                   ("fb:minute", t_int(r["minute"])),
                   ("fb:forTeam", u.team(kind, r["club_id"])),
                   ("fb:byPlayer", player),
                   ("fb:assistedBy", u.res("player", clean(r["player_assist_id"])) if typ == "Goals" else None),
                   ("fb:playerOut", player if typ == "Substitutions" else None),
                   ("fb:playerIn", u.res("player", clean(r["player_in_id"])) if typ == "Substitutions" else None),
                   ("fb:cardType", lit(card_type)),
                   ("fb:scored", scored),
                   ("rdfs:comment", lit(tail)))
    return w.count
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_facts.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/builders/facts.py tests/test_facts.py
git commit -m "feat: appearances and game events builders"
```

---

### Task 9: Transfers and valuations builders

**Files:**
- Create: `src/builders/transfers.py`, `tests/test_transfers.py`

**Interfaces:**
- Consumes: `ctx.scope.player_ids`, `common.hash_id`, `parse_decimal`.
- Produces: `transfers.build_transfers(ctx)->int` (`transfers.ttl`), `transfers.build_valuations(ctx)->int` (`valuations.ttl`).

- [ ] **Step 1: Write the failing test `tests/test_transfers.py`**

```python
from rdflib import Literal, URIRef
from rdflib.namespace import RDF, XSD

from builders import transfers
from common import hash_id
from helpers import FB, R, load_ttl


def uri(*parts):
    return URIRef(f"{R}transfer/{hash_id(*parts)}")


def test_fee_only_emitted_when_positive(ctx):
    transfers.build_transfers(ctx)
    g = load_ttl(ctx.out_dir / "transfers.ttl")
    fee = URIRef(FB + "transferFee")
    free = uri("10", "2019-07-01", "999", "11")             # fee "0.000"
    paid = uri("10", "2023-01-01", "11", "148")             # fee "5000000.000"
    blank = uri("10", "2024-01-01", "148", "11")            # fee ""
    assert not list(g.objects(free, fee))
    assert (paid, fee, Literal("5000000", datatype=XSD.decimal)) in g
    assert not list(g.objects(blank, fee))
    assert not any(o == Literal("0", datatype=XSD.decimal) for o in g.objects(None, fee))


def test_transfer_structure_and_duplicates(ctx):
    n = transfers.build_transfers(ctx)
    g = load_ttl(ctx.out_dir / "transfers.ttl")
    t = uri("10", "2023-01-01", "11", "148")
    assert (t, RDF.type, URIRef(FB + "Transfer")) in g
    assert (t, URIRef(FB + "transferOf"), URIRef(f"{R}player/10")) in g
    assert (t, URIRef(FB + "fromClub"), URIRef(f"{R}club/11")) in g
    assert (t, URIRef(FB + "toClub"), URIRef(f"{R}club/148")) in g
    assert (t, URIRef(FB + "transferDate"), Literal("2023-01-01", datatype=XSD.date)) in g
    assert (t, URIRef(FB + "marketValueAtTransferEUR"), Literal("90000000", datatype=XSD.decimal)) in g
    subjects = set(g.subjects(RDF.type, URIRef(FB + "Transfer")))
    assert len(subjects) == 3                                # duplicate row collapses; p30 excluded
    assert n >= len(g)                                       # duplicate row wrote the same triples twice


def test_valuations(ctx):
    transfers.build_valuations(ctx)
    g = load_ttl(ctx.out_dir / "valuations.ttl")
    v = URIRef(f"{R}valuation/10-2023-06-01")
    assert (v, RDF.type, URIRef(FB + "MarketValuation")) in g
    assert (v, URIRef(FB + "valuationOf"), URIRef(f"{R}player/10")) in g
    assert (v, URIRef(FB + "valueEUR"), Literal("100000000", datatype=XSD.decimal)) in g
    assert (v, URIRef(FB + "valuationDate"), Literal("2023-06-01", datatype=XSD.date)) in g
    assert (v, URIRef(FB + "atClub"), URIRef(f"{R}club/11")) in g
    old = URIRef(f"{R}valuation/10-2019-01-01")
    assert (old, URIRef(FB + "atClub"), URIRef(f"{R}club/999")) in g
    assert not list(g.triples((URIRef(f"{R}valuation/30-2020-01-01"), None, None)))   # out of scope
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_transfers.py -v`
Expected: FAIL (`cannot import name 'transfers'`).

- [ ] **Step 3: Write `src/builders/transfers.py`**

```python
"""transfers.csv -> transfers.ttl ; player_valuations.csv -> valuations.ttl"""
from common import clean, hash_id, lit, parse_date, parse_decimal, t_dec, t_date, typed


def build_transfers(ctx):
    u = ctx.uris
    with ctx.writer("transfers.ttl") as w:
        for r in ctx.csv("transfers.csv"):
            pid = clean(r["player_id"])
            if pid not in ctx.scope.player_ids:
                continue
            date, frm, to = parse_date(r["transfer_date"]), clean(r["from_club_id"]), clean(r["to_club_id"])
            fee = parse_decimal(r["transfer_fee"])
            fee = fee if fee is not None and float(fee) > 0 else None
            w.node(u.res("transfer", hash_id(pid, date, frm, to)),
                   ("a", "fb:Transfer"),
                   ("fb:transferOf", u.res("player", pid)),
                   ("fb:fromClub", u.res("club", frm)),
                   ("fb:toClub", u.res("club", to)),
                   ("fb:transferDate", t_date(r["transfer_date"])),
                   ("fb:transferSeason", lit(r["transfer_season"])),
                   ("fb:transferFee", typed(fee, "xsd:decimal")),
                   ("fb:marketValueAtTransferEUR", t_dec(r["market_value_in_eur"])))
    return w.count


def build_valuations(ctx):
    u = ctx.uris
    with ctx.writer("valuations.ttl") as w:
        for r in ctx.csv("player_valuations.csv"):
            pid = clean(r["player_id"])
            date = parse_date(r["date"])
            if pid not in ctx.scope.player_ids or date is None:
                continue
            w.node(u.res("valuation", f"{pid}-{date}"),
                   ("a", "fb:MarketValuation"),
                   ("fb:valuationOf", u.res("player", pid)),
                   ("fb:valuationDate", t_date(r["date"])),
                   ("fb:valueEUR", t_dec(r["market_value_in_eur"])),
                   ("fb:atClub", u.res("club", clean(r["current_club_id"]))))
    return w.count
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_transfers.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/builders/transfers.py tests/test_transfers.py
git commit -m "feat: transfers and valuations builders"
```

---

### Task 10: Orchestrator and full run

**Files:**
- Create: `src/build_rdf.py`, `src/validate.py`, `tests/test_build_rdf.py`

**Interfaces:**
- Consumes: all builders; `scope.Scope.load`; `validate.check_vocabulary`.
- Produces: `build_rdf.run(cfg, scope, data_dir, out_dir) -> dict[str,int]` (triples per file name) and CLI `python src/build_rdf.py`; `validate.ontology_terms(path, onto_base)->set[str]`, `validate.used_terms(files)->set[str]`, `validate.check_vocabulary(ontology_path, files, onto_base)->set[str]` (terms used but not defined) and CLI `python src/validate.py vocab`.

- [ ] **Step 1: Write the failing test `tests/test_build_rdf.py`**

```python
from pathlib import Path

from build_rdf import run
from helpers import load_ttl
from validate import check_vocabulary

ONT = Path(__file__).resolve().parents[1] / "ontology" / "football.ttl"
EXPECTED = {"reference.ttl", "clubs.ttl", "players.ttl", "matches.ttl",
            "appearances.ttl", "events.ttl", "transfers.ttl", "valuations.ttl"}


def test_run_writes_all_files_that_parse(cfg, data_dir, tmp_path):
    from scope import select_scope
    out = tmp_path / "out"
    totals = run(cfg, select_scope(cfg, data_dir), data_dir, out)
    assert set(totals) == EXPECTED
    for name in EXPECTED:
        assert (out / "data" / name).exists()
        assert len(load_ttl(out / "data" / name)) > 0


def test_every_fb_term_used_is_defined_in_the_ontology(cfg, data_dir, tmp_path):
    from scope import select_scope
    out = tmp_path / "out"
    run(cfg, select_scope(cfg, data_dir), data_dir, out)
    files = sorted((out / "data").glob("*.ttl"))
    assert check_vocabulary(ONT, files, cfg["ontology_base"]) == set()


def test_vocabulary_check_detects_unknown_term(tmp_path):
    f = tmp_path / "x.ttl"
    f.write_text("<http://x/a> fb:notDefinedAnywhere 1 .\n", encoding="utf-8")
    assert check_vocabulary(ONT, [f], "https://example.org/football/ontology#") == {"notDefinedAnywhere"}


def test_output_is_deterministic(cfg, data_dir, tmp_path):
    from scope import select_scope
    scope = select_scope(cfg, data_dir)
    run(cfg, scope, data_dir, tmp_path / "a")
    run(cfg, select_scope(cfg, data_dir), data_dir, tmp_path / "b")
    for name in EXPECTED:
        assert (tmp_path / "a" / "data" / name).read_bytes() == (tmp_path / "b" / "data" / name).read_bytes()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_build_rdf.py -v`
Expected: FAIL (`No module named 'build_rdf'`).

- [ ] **Step 3: Write `src/validate.py`**

```python
"""Vocabulary check: every fb: term used in generated Turtle must exist in the ontology.

CLI: python src/validate.py vocab
"""
import re
import sys
from pathlib import Path

from rdflib import Graph

_USED = re.compile(r"\bfb:([A-Za-z][A-Za-z0-9]*)")


def ontology_terms(path, onto_base):
    g = Graph()
    g.parse(str(path), format="turtle")
    return {str(s)[len(onto_base):] for s in set(g.subjects())
            if str(s).startswith(onto_base)}


def used_terms(files):
    terms = set()
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                terms.update(_USED.findall(line))
    return terms


def check_vocabulary(ontology_path, files, onto_base):
    return used_terms(files) - ontology_terms(ontology_path, onto_base)


def main(argv=None):
    from common import load_config
    argv = sys.argv[1:] if argv is None else argv
    if argv != ["vocab"]:
        print("usage: validate.py vocab")
        return 2
    cfg = load_config()
    files = sorted((Path(cfg["out_dir"]) / "data").glob("*.ttl"))
    missing = check_vocabulary("ontology/football.ttl", files, cfg["ontology_base"])
    if missing:
        print("Undefined fb: terms:", ", ".join(sorted(missing)))
        return 1
    print(f"vocabulary OK ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Write `src/build_rdf.py`**

```python
"""CLI: python src/build_rdf.py [--config config.json]  (needs .cache/scope.json)"""
import argparse
from pathlib import Path

from builders import clubs, facts, matches, players, reference, transfers
from common import BuildCtx, Uris, load_config
from scope import Scope

STEPS = [
    ("reference.ttl", reference.build),
    ("clubs.ttl", clubs.build),
    ("players.ttl", players.build),
    ("matches.ttl", matches.build),
    ("appearances.ttl", facts.build_appearances),
    ("events.ttl", facts.build_events),
    ("transfers.ttl", transfers.build_transfers),
    ("valuations.ttl", transfers.build_valuations),
]


def run(cfg, scope, data_dir, out_dir):
    out_dir = Path(out_dir)
    ctx = BuildCtx(cfg, Uris(cfg), scope, Path(data_dir), out_dir / "data")
    totals = {}
    for name, build in STEPS:
        totals[name] = build(ctx)
        print(f"{name:18s} {totals[name]:>12,d} triples")
    print(f"{'TOTAL':18s} {sum(totals.values()):>12,d} triples")
    for key, n in sorted(ctx.notes.items()):
        print(f"note: {key} = {n:,d}")
    return totals


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    scope = Scope.load(Path(cfg["cache_dir"]) / "scope.json")
    run(cfg, scope, cfg["data_dir"], cfg["out_dir"])


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run unit tests**

Run: `.venv/bin/pytest tests/test_build_rdf.py -v`
Expected: all PASS. If `test_every_fb_term...` fails, the failing set names the missing term: add it to `ontology/football.ttl` with label, comment, domain and range (do not remove it from the builder).

- [ ] **Step 6: Run the whole suite**

Run: `.venv/bin/pytest -q`
Expected: all tests pass.

- [ ] **Step 7: Full run on the real data**

```bash
.venv/bin/python src/select_scope.py
time .venv/bin/python src/build_rdf.py
.venv/bin/python src/validate.py vocab
du -sh output/data
```
Expected: per-file triple counts, a TOTAL of roughly 10–14 million, `vocabulary OK (8 files)`. Record the actual TOTAL and the `note:` lines (minimal clubs/players, unknown event types). Spec check: `club_minimal` should be around 38 plus clubs referenced only by transfers; a `match_missing_team` note must be absent or tiny. If TOTAL is outside 5M–25M, stop and investigate the scope before continuing.

- [ ] **Step 8: Check determinism on the real data**

```bash
.venv/bin/python src/build_rdf.py > /dev/null && sha256sum output/data/*.ttl > /tmp/run1.sha
.venv/bin/python src/build_rdf.py > /dev/null && sha256sum output/data/*.ttl > /tmp/run2.sha
diff /tmp/run1.sha /tmp/run2.sha && echo IDENTICAL
```
Expected: `IDENTICAL`.

- [ ] **Step 9: Commit**

```bash
git add src/build_rdf.py src/validate.py tests/test_build_rdf.py
git commit -m "feat: build_rdf orchestrator and vocabulary validation"
```

---

### Task 11: Wikidata / DBpedia / GeoNames linking (5-star)

**Files:**
- Create: `src/link_wikidata.py`, `tests/test_link_wikidata.py`

**Interfaces:**
- Consumes: `scope.Scope`, `common` (`hash_id`, `read_csv`, `clean`, `Uris`, `TurtleWriter`, `BuildCtx`, `slug`), `countries.CountryResolver`.
- Produces (all in `src/link_wikidata.py`):
  - `sparql(query, retries=4)->dict` (live Wikidata call, sends `User-Agent`, backs off on 429/5xx)
  - `cached_query(cache_dir, key, query, fetch)->dict` (JSON cache; sleeps 1 s only after a live fetch)
  - `tm_query(prop, ids, with_venue=False)->str`
  - `fetch_rows(prop, ids, cache_dir, key, fetch, with_venue=False, batch=300)->list[dict]`; each row has `item` (Wikidata entity URL), `tm` (the Transfermarkt ID string), optional `article` (en.wikipedia URL) and `venue`/`venueLabel`
  - `dbpedia_uri(article_url)->str|None`
  - `write_links(out_dir, uris, kinds)` where `kinds` maps `{"player"|"club"|"national-team"|"competition": rows}` to our URIs via `uris.res(kind, row["tm"])`; writes `wikidata.ttl`, `dbpedia.ttl`; returns link counts
  - `country_rows(names, cache_dir, fetch)->list[dict]` with `name`, `item`, optional `geonames`
  - `main()` CLI writing `output/links/{wikidata,dbpedia,geonames,stadiums}.ttl` and `output/links/report.json`

- [ ] **Step 1: Write the failing test `tests/test_link_wikidata.py`** (all network access is replaced by canned `fetch` functions)

```python
import json

from rdflib import URIRef
from rdflib.namespace import OWL, SKOS

import link_wikidata as lw
from common import Uris
from helpers import R, load_ttl

WD = "http://www.wikidata.org/entity/"


def canned(rows):
    def fetch(query):
        bindings = [{k: {"type": "literal", "value": v} for k, v in r.items()} for r in rows]
        return {"results": {"bindings": bindings}}
    return fetch


def test_tm_query_contains_property_and_values():
    q = lw.tm_query("P2446", ["10", "26"])
    assert "wdt:P2446" in q and '"10"' in q and '"26"' in q
    assert "wdt:P115" not in q
    assert "wdt:P115" in lw.tm_query("P7223", ["1"], with_venue=True)


def test_cached_query_is_offline_on_second_call(tmp_path):
    calls = []

    def fetch(q):
        calls.append(q)
        return {"results": {"bindings": []}}

    lw.cached_query(tmp_path, "k", "SELECT 1", fetch, pause=0)
    lw.cached_query(tmp_path, "k", "SELECT 1", lambda q: (_ for _ in ()).throw(AssertionError("network!")), pause=0)
    assert len(calls) == 1


def test_fetch_rows_batches_and_dedupes(tmp_path):
    seen = []

    def fetch(q):
        seen.append(q)
        return {"results": {"bindings": [
            {"item": {"value": WD + "Q1"}, "tm": {"value": "10"}},
            {"item": {"value": WD + "Q1"}, "tm": {"value": "10"}},      # duplicate row
        ]}}

    rows = lw.fetch_rows("P2446", ["10", "11", "12"], tmp_path, "player", fetch, batch=2, pause=0)
    assert len(seen) == 2                      # 3 ids, batch size 2
    assert len(rows) == 1 and rows[0]["item"] == WD + "Q1"


def test_dbpedia_uri():
    assert lw.dbpedia_uri("https://en.wikipedia.org/wiki/Bukayo_Saka") == "http://dbpedia.org/resource/Bukayo_Saka"
    assert lw.dbpedia_uri("https://en.wikipedia.org/wiki/Real_Madrid_CF") == "http://dbpedia.org/resource/Real_Madrid_CF"
    assert lw.dbpedia_uri(None) is None
    assert lw.dbpedia_uri("https://de.wikipedia.org/wiki/X") is None


def test_write_links(cfg, tmp_path):
    uris = Uris(cfg)
    kinds = {
        "player": [{"item": WD + "Q1", "tm": "10", "article": "https://en.wikipedia.org/wiki/Bukayo_Saka"}],
        "competition": [{"item": WD + "Q9", "tm": "GB1"}],
    }
    counts = lw.write_links(tmp_path, uris, kinds)
    g = load_ttl(tmp_path / "wikidata.ttl")
    assert (URIRef(f"{R}player/10"), OWL.sameAs, URIRef(WD + "Q1")) in g
    assert (URIRef(f"{R}competition/GB1"), OWL.sameAs, URIRef(WD + "Q9")) in g
    d = load_ttl(tmp_path / "dbpedia.ttl")
    assert (URIRef(f"{R}player/10"), OWL.sameAs, URIRef("http://dbpedia.org/resource/Bukayo_Saka")) in d
    assert counts == {"player": 1, "competition": 1}


def test_stadium_links_use_closematch_and_normalised_names(cfg, tmp_path):
    uris = Uris(cfg)
    club_rows = [{"item": WD + "Q5", "tm": "11", "venue": WD + "Q99", "venueLabel": "Emirates Stadium"}]
    club_stadium = {"11": "emirates stadium"}                  # case-folded name from clubs.csv
    n = lw.write_stadium_links(tmp_path, uris, club_rows, {"11": "Emirates Stadium"})
    g = load_ttl(tmp_path / "stadiums.ttl")
    assert (URIRef(f"{R}stadium/Emirates_Stadium"), SKOS.closeMatch, URIRef(WD + "Q99")) in g
    assert n == 1
    # a venue whose label differs is not linked
    club_rows2 = [{"item": WD + "Q5", "tm": "11", "venue": WD + "Q98", "venueLabel": "Highbury"}]
    assert lw.write_stadium_links(tmp_path, uris, club_rows2, {"11": "Emirates Stadium"}) == 0


def test_country_rows_and_geonames(cfg, tmp_path):
    fetch = canned([{"name": "England", "item": WD + "Q21", "geonames": "6269131"}])
    rows = lw.country_rows(["England", "Atlantis"], tmp_path, fetch, pause=0)
    assert rows == [{"name": "England", "item": WD + "Q21", "geonames": "6269131"}]
    uris = Uris(cfg)
    n = lw.write_country_links(tmp_path, rows, {"England": f"<{R}country/189>"})
    g = load_ttl(tmp_path / "geonames.ttl")
    assert (URIRef(f"{R}country/189"), OWL.sameAs, URIRef("https://sws.geonames.org/6269131/")) in g
    w = load_ttl(tmp_path / "wikidata-countries.ttl")
    assert (URIRef(f"{R}country/189"), OWL.sameAs, URIRef(WD + "Q21")) in w
    assert n == 1


def test_report(tmp_path):
    lw.write_report(tmp_path, {"player": (100, 90), "club": (10, 0)})
    rep = json.loads((tmp_path / "report.json").read_text())
    assert rep["player"] == {"total": 100, "linked": 90, "rate": 0.9}
    assert rep["club"]["rate"] == 0.0
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_link_wikidata.py -v`
Expected: FAIL (`No module named 'link_wikidata'`).

- [ ] **Step 3: Write `src/link_wikidata.py`**

```python
"""5-star linking: exact joins on Transfermarkt IDs against Wikidata, plus DBpedia and GeoNames.

CLI: python src/link_wikidata.py   (needs .cache/scope.json and output/data/*.ttl built)
Wikidata responses are cached under <cache_dir>/wikidata/, so reruns work offline.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from common import BuildCtx, TurtleWriter, Uris, clean, hash_id, load_config, read_csv, slug
from countries import CountryResolver
from scope import Scope

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "football-lod-course/0.1 (student project; contact via repository owner)"
WIKIDATA = "http://www.wikidata.org/entity/"
PROP_PLAYER, PROP_TEAM, PROP_COMPETITION = "P2446", "P7223", "P12758"


def sparql(query, retries=4):
    data = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(ENDPOINT, data=data, headers={
        "Accept": "application/sparql-results+json", "User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                wait = int(e.headers.get("Retry-After", 5 * 2 ** attempt))
                time.sleep(wait)
                continue
            raise
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(5 * 2 ** attempt)
                continue
            raise


def cached_query(cache_dir, key, query, fetch=sparql, pause=1.0):
    path = Path(cache_dir) / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    result = fetch(query)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    time.sleep(pause)
    return result


def _rows(result):
    return [{k: v["value"] for k, v in b.items()} for b in result["results"]["bindings"]]


def tm_query(prop, ids, with_venue=False):
    values = " ".join(f'"{i}"' for i in ids)
    venue = ("OPTIONAL { ?item wdt:P115 ?venue . ?venue rdfs:label ?venueLabel . "
             'FILTER(LANG(?venueLabel) = "en") }' if with_venue else "")
    return (f"SELECT ?item ?tm ?article ?venue ?venueLabel WHERE {{ VALUES ?tm {{ {values} }} "
            f"?item wdt:{prop} ?tm . "
            "OPTIONAL { ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> } "
            f"{venue} }}")


def fetch_rows(prop, ids, cache_dir, key, fetch=sparql, with_venue=False, batch=300, pause=1.0):
    ids = sorted(ids)
    out, seen = [], set()
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        q = tm_query(prop, chunk, with_venue)
        result = cached_query(Path(cache_dir) / "wikidata", f"{key}-{hash_id(*chunk)}", q, fetch, pause)
        for row in _rows(result):
            sig = tuple(sorted(row.items()))
            if sig not in seen:
                seen.add(sig)
                out.append(row)
    return out


def dbpedia_uri(article_url):
    prefix = "https://en.wikipedia.org/wiki/"
    if not article_url or not article_url.startswith(prefix):
        return None
    return "http://dbpedia.org/resource/" + article_url[len(prefix):]


def write_links(out_dir, uris, kinds):
    out_dir = Path(out_dir)
    counts = {}
    with TurtleWriter(out_dir / "wikidata.ttl", uris.onto) as wd, \
            TurtleWriter(out_dir / "dbpedia.ttl", uris.onto) as db:
        for kind, rows in kinds.items():
            linked = set()
            for r in rows:
                ours = uris.res(kind, r["tm"])
                wd.node(ours, ("owl:sameAs", f"<{r['item']}>"))
                db_uri = dbpedia_uri(r.get("article"))
                db.node(ours, ("owl:sameAs", f"<{db_uri}>" if db_uri else None))
                linked.add(r["tm"])
            counts[kind] = len(linked)
    return counts


def write_stadium_links(out_dir, uris, club_rows, club_stadium_names):
    """club_rows: Wikidata rows for clubs (with venue); club_stadium_names: club id -> stadium name."""
    n = 0
    done = set()
    with TurtleWriter(Path(out_dir) / "stadiums.ttl", uris.onto) as w:
        for r in club_rows:
            ours_name = club_stadium_names.get(r["tm"])
            venue, label = r.get("venue"), r.get("venueLabel")
            if not (ours_name and venue and label):
                continue
            if clean(ours_name).casefold() != clean(label).casefold():
                continue
            key = (ours_name, venue)
            if key in done:
                continue
            done.add(key)
            w.node(uris.res("stadium", slug(ours_name)), ("skos:closeMatch", f"<{venue}>"))
            n += 1
    return n


def country_rows(names, cache_dir, fetch=sparql, pause=1.0):
    names = sorted(set(names))
    out = []
    for i in range(0, len(names), 100):
        chunk = names[i:i + 100]
        values = " ".join('"' + n.replace("\\", "\\\\").replace('"', '\\"') + '"@en' for n in chunk)
        q = ("SELECT ?name ?item ?geonames WHERE { VALUES ?name { " + values + " } "
             "?item rdfs:label ?name ; wdt:P31 ?type . VALUES ?type { wd:Q6256 wd:Q3624078 } "
             "OPTIONAL { ?item wdt:P1566 ?geonames } }")
        result = cached_query(Path(cache_dir) / "wikidata", f"countries-{hash_id(*chunk)}", q, fetch, pause)
        for row in _rows(result):
            out.append({"name": row["name"], "item": row["item"],
                        **({"geonames": row["geonames"]} if "geonames" in row else {})})
    return out


def write_country_links(out_dir, rows, name_to_uri):
    n = 0
    with TurtleWriter(Path(out_dir) / "wikidata-countries.ttl", "") as wd, \
            TurtleWriter(Path(out_dir) / "geonames.ttl", "") as gn:
        for r in rows:
            ours = name_to_uri.get(r["name"])
            if ours is None:
                continue
            wd.node(ours, ("owl:sameAs", f"<{r['item']}>"))
            gn.node(ours, ("owl:sameAs", f"<https://sws.geonames.org/{r['geonames']}/>" if r.get("geonames") else None))
            n += 1
    return n


def write_report(out_dir, stats):
    rep = {k: {"total": t, "linked": l, "rate": round(l / t, 4) if t else 0.0}
           for k, (t, l) in stats.items()}
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    return rep


def main():
    cfg = load_config()
    scope = Scope.load(Path(cfg["cache_dir"]) / "scope.json")
    uris = Uris(cfg)
    cache = cfg["cache_dir"]
    out = Path(cfg["out_dir"]) / "links"
    data_dir = Path(cfg["data_dir"])

    nat_ids = {clean(r["national_team_id"]) for r in read_csv(data_dir / "national_teams.csv")} | scope.national_ids
    comp_ids = {c["id"] for c in cfg["competitions"]}

    players = fetch_rows(PROP_PLAYER, scope.player_ids, cache, "player")
    clubs = fetch_rows(PROP_TEAM, scope.club_ids, cache, "club", with_venue=True)
    nationals = fetch_rows(PROP_TEAM, nat_ids, cache, "national", with_venue=False)
    comps = fetch_rows(PROP_COMPETITION, comp_ids, cache, "competition")

    counts = write_links(out, uris, {"player": players, "club": clubs,
                                     "national-team": nationals, "competition": comps})

    club_stadium = {clean(r["club_id"]): clean(r["stadium_name"])
                    for r in read_csv(data_dir / "clubs.csv") if clean(r["stadium_name"])}
    stadium_links = write_stadium_links(out, uris, clubs, club_stadium)

    ctx = BuildCtx(cfg, uris, scope, data_dir, out)
    resolver = CountryResolver(ctx)
    for r in read_csv(data_dir / "players.csv"):
        if r["player_id"] in scope.player_ids:
            resolver.uri(r["country_of_citizenship"])
            resolver.uri(r["country_of_birth"])
    names = resolver.all_names()
    crows = country_rows(list(names), cache)
    country_links = write_country_links(out, crows, names)

    report = write_report(out, {
        "player": (len(scope.player_ids), counts["player"]),
        "club": (len(scope.club_ids), counts["club"]),
        "national-team": (len(nat_ids), counts["national-team"]),
        "competition": (len(comp_ids), counts["competition"]),
        "country": (len(names), country_links),
        "stadium": (len(set(club_stadium.values())), stadium_links),
    })
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run unit tests**

Run: `.venv/bin/pytest tests/test_link_wikidata.py -v`
Expected: all PASS. (`write_country_links` passes an empty ontology base to `TurtleWriter`, which only adds an unused `@prefix fb: <>` line; that is harmless.)

- [ ] **Step 5: Smoke-test against the live endpoint with a tiny batch**

```bash
.venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, "src")
import link_wikidata as lw, tempfile
rows = lw.fetch_rows(lw.PROP_PLAYER, ["8198", "28003"], tempfile.mkdtemp(), "smoke")
print(rows)
EOF
```
Expected: rows for Transfermarkt player IDs 8198 (Cristiano Ronaldo) and 28003 (Lionel Messi) with `item` values like `http://www.wikidata.org/entity/Q...` (Q11571 and Q615 respectively). If the call fails with a 4xx, read the error body: it usually names the query problem. Fix `tm_query`, not the test.

- [ ] **Step 7: Run the real linking and check the report**

```bash
time .venv/bin/python src/link_wikidata.py
ls -la output/links
```
Expected: JSON report printed; `output/links/{wikidata,dbpedia,geonames,wikidata-countries,stadiums}.ttl` and `report.json` exist. Rates to expect (investigate if far below): clubs and competitions above 0.9, national teams above 0.9, players a substantial majority of well-known players (the report shows the real number; record it in the README). A rerun must finish in seconds with no network (cache hit): run it a second time to confirm.

- [ ] **Step 8: Commit**

```bash
git add src/link_wikidata.py tests/test_link_wikidata.py
git commit -m "feat: Wikidata/DBpedia/GeoNames linking with cache and report"
```

---

### Task 12: SHACL shapes

**Files:**
- Create: `shapes/football-shapes.ttl`, `tests/test_shacl.py`, `scripts/shacl.sh`

**Interfaces:**
- Consumes: `build_rdf.run`, fixtures; `ontology/football.ttl` (supplies the class hierarchy for `sh:class fb:Team`).
- Produces: shapes `fbs:MatchShape`, `fbs:AppearanceShape`, `fbs:TransferShape`, `fbs:PlayerShape`, `fbs:EventShape`; `scripts/shacl.sh` validating full data with Jena.

- [ ] **Step 1: Write the failing test `tests/test_shacl.py`**

```python
from pathlib import Path

from pyshacl import validate
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF

from build_rdf import run
from helpers import FB, R

ROOT = Path(__file__).resolve().parents[1]


def load_all(out):
    g = Graph()
    for f in sorted((out / "data").glob("*.ttl")):
        g.parse(str(f), format="turtle")
    return g


def shacl(data, ont):
    shapes = Graph().parse(str(ROOT / "shapes" / "football-shapes.ttl"), format="turtle")
    conforms, _, text = validate(data, shacl_graph=shapes, ont_graph=ont, inference=None)
    return conforms, text


def test_fixture_data_conforms(cfg, data_dir, tmp_path):
    from scope import select_scope
    out = tmp_path / "out"
    run(cfg, select_scope(cfg, data_dir), data_dir, out)
    ont = Graph().parse(str(ROOT / "ontology" / "football.ttl"), format="turtle")
    conforms, text = shacl(load_all(out), ont)
    assert conforms, text


def test_match_without_away_team_violates(cfg, data_dir, tmp_path):
    from scope import select_scope
    out = tmp_path / "out"
    run(cfg, select_scope(cfg, data_dir), data_dir, out)
    ont = Graph().parse(str(ROOT / "ontology" / "football.ttl"), format="turtle")
    g = load_all(out)
    g.remove((URIRef(f"{R}match/100"), URIRef(FB + "awayTeam"), None))
    conforms, text = shacl(g, ont)
    assert not conforms and "awayTeam" in text


def test_appearance_pointing_to_unknown_player_violates(cfg, data_dir, tmp_path):
    from scope import select_scope
    out = tmp_path / "out"
    run(cfg, select_scope(cfg, data_dir), data_dir, out)
    ont = Graph().parse(str(ROOT / "ontology" / "football.ttl"), format="turtle")
    g = load_all(out)
    g.set((URIRef(f"{R}appearance/100_10"), URIRef(FB + "appearanceOf"), URIRef(f"{R}player/does-not-exist")))
    conforms, _ = shacl(g, ont)
    assert not conforms
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_shacl.py -v`
Expected: FAIL (shapes file missing).

- [ ] **Step 3: Write `shapes/football-shapes.ttl`**

```turtle
@prefix fb:   <https://example.org/football/ontology#> .
@prefix fbs:  <https://example.org/football/shapes#> .
@prefix sh:   <http://www.w3.org/ns/shacl#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

fbs:MatchShape a sh:NodeShape ;
    sh:targetClass fb:Match ;
    sh:property [ sh:path fb:homeTeam ; sh:minCount 1 ; sh:maxCount 1 ; sh:class fb:Team ] ;
    sh:property [ sh:path fb:awayTeam ; sh:minCount 1 ; sh:maxCount 1 ; sh:class fb:Team ] ;
    sh:property [ sh:path fb:inCompetition ; sh:minCount 1 ; sh:maxCount 1 ; sh:class fb:Competition ] ;
    sh:property [ sh:path fb:matchDate ; sh:maxCount 1 ; sh:datatype xsd:date ] .

fbs:AppearanceShape a sh:NodeShape ;
    sh:targetClass fb:Appearance ;
    sh:property [ sh:path fb:appearanceOf ; sh:minCount 1 ; sh:maxCount 1 ; sh:class fb:Player ] ;
    sh:property [ sh:path fb:inMatch ; sh:minCount 1 ; sh:maxCount 1 ; sh:class fb:Match ] ;
    sh:property [ sh:path fb:forTeam ; sh:maxCount 1 ; sh:class fb:Team ] .

fbs:EventShape a sh:NodeShape ;
    sh:targetClass fb:MatchEvent ;
    sh:property [ sh:path fb:inMatch ; sh:minCount 1 ; sh:maxCount 1 ; sh:class fb:Match ] ;
    sh:property [ sh:path fb:byPlayer ; sh:maxCount 1 ; sh:class fb:Player ] .

fbs:TransferShape a sh:NodeShape ;
    sh:targetClass fb:Transfer ;
    sh:property [ sh:path fb:transferOf ; sh:minCount 1 ; sh:maxCount 1 ; sh:class fb:Player ] ;
    sh:property [ sh:path fb:fromClub ; sh:minCount 1 ; sh:maxCount 1 ; sh:class fb:Club ] ;
    sh:property [ sh:path fb:toClub ; sh:minCount 1 ; sh:maxCount 1 ; sh:class fb:Club ] ;
    sh:property [ sh:path fb:transferDate ; sh:minCount 1 ; sh:maxCount 1 ; sh:datatype xsd:date ] ;
    sh:property [ sh:path fb:transferFee ; sh:maxCount 1 ; sh:minExclusive 0 ] .

fbs:PlayerShape a sh:NodeShape ;
    sh:targetClass fb:Player ;
    sh:property [ sh:path fb:dateOfBirth ; sh:maxCount 1 ; sh:datatype xsd:date ] ;
    sh:property [ sh:path fb:heightCm ; sh:maxCount 1 ; sh:datatype xsd:integer ] .
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_shacl.py -v`
Expected: all PASS. If `test_fixture_data_conforms` fails, the printed report names the offending node; the usual cause is a reference to a node the fixture never creates, which is a real builder bug to fix there (not in the shapes).

- [ ] **Step 5: Write `scripts/shacl.sh`** (full-data validation with Jena inside the Task 13 image; run it after Task 13)

```bash
#!/usr/bin/env bash
# Validate the generated data against shapes/football-shapes.ttl with Jena's `shacl validate`.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose run --rm --no-deps -e JVM_ARGS=-Xmx6g --entrypoint sh fuseki -c '
  cat /import/ontology/football.ttl /import/output/data/*.ttl > /tmp/all.ttl 2>/dev/null || true
  /jena/bin/shacl validate --shapes /import/shapes/football-shapes.ttl --data /tmp/all.ttl
'
```
(`cat`ing Turtle files together is valid because each file repeats its `@prefix` lines.)

```bash
chmod +x scripts/shacl.sh
git add shapes scripts/shacl.sh tests/test_shacl.py
git commit -m "feat: SHACL shapes with fixture-level tests"
```

---

### Task 13: Fuseki endpoint, competency queries, dangling-reference checks

**Files:**
- Create: `docker/Dockerfile`, `docker-compose.yml`, `scripts/load.sh`, `scripts/query.sh`, `scripts/run_checks.sh`, `queries/q01_top_scorers_pl_2023.rq` … `queries/q09_class_counts.rq`, `queries/checks/dangling_*.rq`

**Interfaces:**
- Consumes: `output/data/*.ttl`, `output/links/*.ttl`, `ontology/football.ttl`, `shapes/`.
- Produces: SPARQL endpoint `http://localhost:3030/football/sparql`; `scripts/query.sh <file.rq> [accept-mime]` prints results (default CSV); `scripts/run_checks.sh` exits non-zero if any dangling-reference count is above zero.

- [ ] **Step 1: Write `docker/Dockerfile`**

```dockerfile
FROM eclipse-temurin:21-jre
ARG JENA_VERSION=5.5.0
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /jena /fuseki \
    && curl -fsSL https://repo1.maven.org/maven2/org/apache/jena/apache-jena/${JENA_VERSION}/apache-jena-${JENA_VERSION}.tar.gz | tar xz -C /jena --strip-components=1 \
    && curl -fsSL https://repo1.maven.org/maven2/org/apache/jena/apache-jena-fuseki/${JENA_VERSION}/apache-jena-fuseki-${JENA_VERSION}.tar.gz | tar xz -C /fuseki --strip-components=1
ENV JVM_ARGS="-Xmx4g"
EXPOSE 3030
CMD ["/fuseki/fuseki-server", "--tdb2", "--loc=/data/tdb", "--port=3030", "/football"]
```

- [ ] **Step 2: Write `docker-compose.yml`**

```yaml
services:
  fuseki:
    build: ./docker
    ports:
      - "3030:3030"
    volumes:
      - tdb:/data
      - ./output:/import/output:ro
      - ./ontology:/import/ontology:ro
      - ./shapes:/import/shapes:ro
volumes:
  tdb:
```

- [ ] **Step 3: Write `scripts/load.sh`**

```bash
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
```

- [ ] **Step 4: Write `scripts/query.sh`**

```bash
#!/usr/bin/env bash
# Usage: scripts/query.sh queries/q01_top_scorers_pl_2023.rq [accept-mime]
set -euo pipefail
ENDPOINT="${SPARQL_ENDPOINT:-http://localhost:3030/football/sparql}"
ACCEPT="${2:-text/csv}"
curl -sS --fail-with-body -H "Accept: ${ACCEPT}" --data-urlencode "query@${1}" "${ENDPOINT}"
```

- [ ] **Step 5: Write the competency queries**

`queries/q01_top_scorers_pl_2023.rq`
```sparql
PREFIX fb: <https://example.org/football/ontology#>
PREFIX fbr: <https://example.org/football/resource/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

# Top 10 scorers of the 2023 Premier League season
SELECT ?player (SUM(?g) AS ?goals) WHERE {
  ?a a fb:Appearance ; fb:appearanceOf ?p ; fb:inMatch ?m ; fb:goals ?g .
  ?m fb:inCompetition fbr:competition\/GB1 ; fb:inSeason fbr:season\/2023 .
  ?p rdfs:label ?player .
} GROUP BY ?p ?player ORDER BY DESC(?goals) LIMIT 10
```

`queries/q02_most_expensive_transfers.rq`
```sparql
PREFIX fb: <https://example.org/football/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

# 10 most expensive transfers in the dataset
SELECT ?player ?from ?to ?date ?fee WHERE {
  ?t a fb:Transfer ; fb:transferOf ?p ; fb:fromClub ?f ; fb:toClub ?c ;
     fb:transferDate ?date ; fb:transferFee ?fee .
  ?p rdfs:label ?player . ?f rdfs:label ?from . ?c rdfs:label ?to .
} ORDER BY DESC(?fee) LIMIT 10
```

`queries/q03_world_cup_2026_players.rq`
```sparql
PREFIX fb: <https://example.org/football/ontology#>
PREFIX fbr: <https://example.org/football/resource/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

# World Cup 2026 players with their national team and current club
SELECT DISTINCT ?player ?nation ?club WHERE {
  ?m fb:inCompetition fbr:competition\/FIWC ; fb:inSeason fbr:season\/2025 .
  ?a a fb:Appearance ; fb:inMatch ?m ; fb:appearanceOf ?p ; fb:forTeam ?t .
  ?p rdfs:label ?player ; fb:playsFor ?c .
  ?t rdfs:label ?nation . ?c rdfs:label ?club .
} ORDER BY ?nation ?player LIMIT 50
```

`queries/q04_federated_birthplace_wikidata.rq`
```sparql
PREFIX fb: <https://example.org/football/ontology#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>

# 5-star demo: for the 10 most valuable Wikidata-linked players, fetch the birth place from Wikidata
SELECT ?name ?birthPlaceLabel WHERE {
  { SELECT ?name ?wd WHERE {
      ?p a fb:Player ; rdfs:label ?name ; fb:currentMarketValueEUR ?v ; owl:sameAs ?wd .
      FILTER(STRSTARTS(STR(?wd), "http://www.wikidata.org/entity/Q"))
    } ORDER BY DESC(?v) LIMIT 10 }
  SERVICE <https://query.wikidata.org/sparql> {
    ?wd wdt:P19 ?bp . ?bp rdfs:label ?birthPlaceLabel . FILTER(LANG(?birthPlaceLabel) = "en")
  }
}
```

`queries/q05_arsenal_squad_by_value.rq`
```sparql
PREFIX fb: <https://example.org/football/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

# Players currently at Arsenal FC ordered by market value
SELECT ?player ?value WHERE {
  ?c a fb:Club ; rdfs:label ?cl . FILTER(STR(?cl) = "Arsenal FC")
  ?p fb:playsFor ?c ; rdfs:label ?player ; fb:currentMarketValueEUR ?value .
} ORDER BY DESC(?value) LIMIT 25
```

`queries/q06_biggest_champions_league_wins.rq`
```sparql
PREFIX fb: <https://example.org/football/ontology#>
PREFIX fbr: <https://example.org/football/resource/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

# Ten biggest winning margins in the Champions League
SELECT ?home ?away ?hs ?as ?diff ?date WHERE {
  ?m fb:inCompetition fbr:competition\/CL ; fb:homeTeam ?h ; fb:awayTeam ?a ;
     fb:homeScore ?hs ; fb:awayScore ?as ; fb:matchDate ?date .
  ?h rdfs:label ?home . ?a rdfs:label ?away .
  BIND(ABS(?hs - ?as) AS ?diff)
} ORDER BY DESC(?diff) ?date LIMIT 10
```

`queries/q07_real_madrid_to_barcelona.rq`
```sparql
PREFIX fb: <https://example.org/football/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

# Players who moved between Real Madrid and FC Barcelona, in either direction (directly)
SELECT ?player ?from ?to ?date WHERE {
  ?t a fb:Transfer ; fb:transferOf ?p ; fb:fromClub ?f ; fb:toClub ?c ; fb:transferDate ?date .
  ?f rdfs:label ?from . ?c rdfs:label ?to . ?p rdfs:label ?player .
  FILTER((STR(?from) = "Real Madrid" && STR(?to) = "FC Barcelona") ||
         (STR(?from) = "FC Barcelona" && STR(?to) = "Real Madrid"))
} ORDER BY ?date
```

`queries/q08_messi_valuation_history.rq`
```sparql
PREFIX fb: <https://example.org/football/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

# Market value history of Lionel Messi
SELECT ?date ?value WHERE {
  ?p a fb:Player ; rdfs:label ?n . FILTER(STR(?n) = "Lionel Messi")
  ?v fb:valuationOf ?p ; fb:valuationDate ?date ; fb:valueEUR ?value .
} ORDER BY ?date
```

`queries/q09_class_counts.rq`
```sparql
PREFIX fb: <https://example.org/football/ontology#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>

# Instances per ontology class, plus the number of owl:sameAs links
SELECT ?class (COUNT(?s) AS ?instances) WHERE { ?s a ?class . FILTER(STRSTARTS(STR(?class), STR(fb:))) }
GROUP BY ?class ORDER BY DESC(?instances)
```

Note: in the `fbr:competition\/GB1` forms above the backslash is the Turtle/SPARQL local-name escape for `/`; SPARQL allows `\/` in prefixed names. If Fuseki rejects it, replace each with a full IRI such as `<https://example.org/football/resource/competition/GB1>`.

- [ ] **Step 6: Write the dangling-reference checks**

`queries/checks/dangling_appearance_player.rq`
```sparql
PREFIX fb: <https://example.org/football/ontology#>
SELECT (COUNT(*) AS ?n) WHERE {
  ?a a fb:Appearance ; fb:appearanceOf ?p .
  FILTER NOT EXISTS { ?p a fb:Player }
}
```
`queries/checks/dangling_appearance_match.rq`
```sparql
PREFIX fb: <https://example.org/football/ontology#>
SELECT (COUNT(*) AS ?n) WHERE {
  ?a a fb:Appearance ; fb:inMatch ?m .
  FILTER NOT EXISTS { ?m a fb:Match }
}
```
`queries/checks/dangling_match_team.rq`
```sparql
PREFIX fb: <https://example.org/football/ontology#>
SELECT (COUNT(*) AS ?n) WHERE {
  ?m a fb:Match ; ?side ?t . FILTER(?side IN (fb:homeTeam, fb:awayTeam))
  FILTER NOT EXISTS { ?t a ?c . FILTER(?c IN (fb:Club, fb:NationalTeam)) }
}
```
`queries/checks/dangling_transfer_club.rq`
```sparql
PREFIX fb: <https://example.org/football/ontology#>
SELECT (COUNT(*) AS ?n) WHERE {
  ?t a fb:Transfer ; ?side ?c . FILTER(?side IN (fb:fromClub, fb:toClub))
  FILTER NOT EXISTS { ?c a fb:Club }
}
```
`queries/checks/dangling_event_player.rq`
```sparql
PREFIX fb: <https://example.org/football/ontology#>
SELECT (COUNT(*) AS ?n) WHERE {
  ?e a ?cls ; fb:byPlayer ?p . FILTER(?cls IN (fb:Goal, fb:Card, fb:Substitution, fb:PenaltyShootoutKick))
  FILTER NOT EXISTS { ?p a fb:Player }
}
```

- [ ] **Step 7: Write `scripts/run_checks.sh`**

```bash
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
```

- [ ] **Step 8: Build, load and start**

```bash
chmod +x scripts/*.sh
scripts/load.sh
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3030/$/ping
```
Expected: image builds (needs network), the loader prints triple counts, ping prints `200`. If `tdb2.tdbloader` reports a Turtle syntax error with a line number, the offending builder line is in the named file: fix the builder (and add a regression test with the awkward value) rather than editing output.

- [ ] **Step 9: Run every competency query and the checks**

```bash
for q in queries/q*.rq; do echo "== $q"; scripts/query.sh "$q" | head -n 6; done
scripts/run_checks.sh
```
Expected: q01–q03, q05–q09 return rows (q01 should list known Premier League scorers; q07 may legitimately be small). q04 returns rows only if Wikidata is reachable from the container host; if it errors, record that in the README rather than deleting the query. `run_checks.sh` must exit 0 (all counts `0`). A non-zero count means a builder produces dangling references: find the cause with the matching check query changed to `SELECT ?a ?p ... LIMIT 10`, fix the builder or scope, rebuild and reload.

- [ ] **Step 10: Run SHACL on the full data**

Run: `scripts/shacl.sh`
Expected: Jena reports `sh:conforms true`. If the JVM runs out of memory, raise `-Xmx` in `scripts/shacl.sh`; if it still fails, record in the README that full-data SHACL was skipped for memory and that the dangling-reference checks plus fixture SHACL tests stand in.

- [ ] **Step 11: Commit**

```bash
git add docker docker-compose.yml scripts queries
git commit -m "feat: Fuseki endpoint, competency queries, dangling-reference checks"
```

---

### Task 14: README, Makefile, final verification

**Files:**
- Create: `README.md`, `Makefile`

**Interfaces:**
- Consumes: everything above. Produces: a reproducible end-to-end recipe.

- [ ] **Step 1: Write `Makefile`**

```make
PY=.venv/bin/python

.PHONY: test scope build vocab links load checks all
test:   ; .venv/bin/pytest -q
scope:  ; $(PY) src/select_scope.py
build:  ; $(PY) src/build_rdf.py
vocab:  ; $(PY) src/validate.py vocab
links:  ; $(PY) src/link_wikidata.py
load:   ; scripts/load.sh
checks: ; scripts/run_checks.sh
all: test scope build vocab links load checks
```

- [ ] **Step 2: Write `README.md`**

Contents (fill the bracketed numbers from your own runs in Tasks 3, 10, 11, 13; do not leave brackets in the committed file):

````markdown
# Football Linked Open Data

Transfermarkt CSVs → football ontology → 4-star RDF → 5-star links (Wikidata, DBpedia, GeoNames) → Fuseki SPARQL endpoint.

## Quick start
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
make all            # tests, scope, build, vocabulary check, links, Fuseki load, checks
```
Endpoint: http://localhost:3030/football/sparql (UI at http://localhost:3030/).
Terminal: `scripts/query.sh queries/q01_top_scorers_pl_2023.rq`

## Scope
GB1, ES1, IT1, L1, FR1, CL, EL for 2012–2025; FIWC (6 editions). Change `config.json` to narrow or widen.

## Results of the last run
- Triples (data): <TOTAL from build_rdf>
- Players / clubs / games in scope: <numbers from select_scope>
- Link rates (output/links/report.json): <players %, clubs %, national teams %, competitions %, countries %>
- Validation: vocabulary OK; SHACL <conforms / skipped because ...>; dangling-reference checks all 0

## Layout, decisions and limits
See `docs/superpowers/specs/2026-10-02-football-lod-design.md` and the "Decisions made in this plan" section of `docs/superpowers/plans/2026-10-02-football-lod.md`.
Known source limits: FIWC appearances exist only for the 2026 edition; `transfer_fee` empty and `0` are not distinguishable and are omitted; future-dated transfers exist in the source.

## Not yet built
Web UI for querying (planned as a separate cycle).
````

- [ ] **Step 3: Fresh end-to-end verification**

```bash
rm -rf output .cache
make all 2>&1 | tail -n 40
```
Expected: tests pass, build prints totals, vocabulary OK, `report.json` printed (live Wikidata calls repopulate the cache), Fuseki starts, checks exit 0. Then confirm the three headline numbers appear in the README and match this run. If anything fails, fix the cause and rerun from `make all`; do not edit the README to describe a state that was not reproduced.

- [ ] **Step 4: Commit**

```bash
git add README.md Makefile
git commit -m "docs: README and Makefile for end-to-end run"
```

---

## Self-review

**Spec coverage:**
- Goal / deliverables 1–5 (spec §1): ontology Task 4; 4-star data Tasks 5–10; 5-star links Task 11; endpoint Task 13; SHACL and competency queries Tasks 12–13.
- Data scope (spec §2): Task 1 `config.json`, Task 3 `select_scope`; dropped tables are never read by any task; source limits are carried to the README (Task 14).
- Ontology classes/properties/URI scheme/n-ary relations/conventions (spec §3): Task 4 and builders in Tasks 5–9; `fb:isFreeTransfer` is deliberately never emitted (Global Constraints); `fb:linkConfidence` is replaced by `skos:closeMatch` (decision 6, a documented deviation from spec §4.3 item 4).
- Pipeline mapping table (spec §4.2): reference Task 5; clubs/players Task 6; games Task 7; appearances/events Task 8; transfers/valuations Task 9; minimal-node fallbacks and `players.name` as the canonical label are in Tasks 5, 6.
- Linking (spec §4.3): Task 11 (exact ID joins, DBpedia via sitelink, GeoNames, stadium closeMatch, cache, report).
- Endpoint (spec §4.4) and validation (spec §5): Tasks 12–13, including the federated query.
- Risks (spec §6): covered by minimal nodes (Tasks 5, 6), batching/cache (Task 11), and the "stop and investigate" thresholds in Tasks 3 and 10.

**Placeholder scan:** The only bracketed values are the README run results in Task 14, which depend on real runs and are explicitly to be filled in before commit. No "TBD/TODO/similar to Task N" steps remain.

**Type/name consistency:** `Scope` fields (`game_ids`, `game_kind`, `club_ids`, `club_names`, `national_ids`, `national_names`, `player_ids`) are used identically in Tasks 3, 5–11. Builder contract `build(ctx)->int` is the same everywhere; `facts` and `transfers` expose two named functions each and `build_rdf.STEPS` references exactly those names. `ctx.notes` (not `dropped`) is the counter in all tasks. `Uris.res` returns `None` for empty keys, which every builder relies on. `named_node(ctx, w, kind, cls, name)` has one signature across Tasks 2, 5, 6, 7. Helper `t_int/t_dec/t_date/typed/lit/iri` are defined in Task 2 and imported from there.

**Review Focus coverage:** (1) awkward literals — Task 2 round-trip test; (2) empty cells — Tasks 5, 6, 7 assertions that no triple is created; (3) fee `""`/`0.000`/positive — Task 9 first test; (4) clubs/national teams missing from reference CSVs — Tasks 3, 5, 6 tests plus the real-data notes in Task 10; (5) determinism and offline relinking — Task 10 steps 5 and 8, Task 11 `test_cached_query_is_offline_on_second_call` and step 7.
