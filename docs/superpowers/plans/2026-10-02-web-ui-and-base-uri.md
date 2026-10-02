# Web UI and Real Base URI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the dataset to a real namespace (`https://vdhugn.github.io/Football-LOD/`) and add a Flask web app with entity pages, content negotiation for resource URIs, ontology page and a SPARQL playground.

**Architecture:** Task 1 rewrites the namespace everywhere and regenerates data. The web app is a Flask package `src/footballweb/` that only talks to Fuseki's query endpoint through a small client (injectable for tests), builds entity pages from SPARQL results, serves RDF with rdflib, and ships a CodeMirror-based playground.

**Tech Stack:** Python 3.12, Flask, Jinja2, rdflib, gunicorn (Docker), CodeMirror 5 from cdnjs, pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-web-ui-and-base-uri-design.md` (extends `2026-10-02-football-lod-design.md`).

## Global Constraints

- Base URIs: ontology `https://vdhugn.github.io/Football-LOD/ontology#`, resources `https://vdhugn.github.io/Football-LOD/resource/`, shapes `https://vdhugn.github.io/Football-LOD/shapes#`. Never hard-code them in `src/footballweb/`; read them from `config.json`.
- The web app only issues SELECT, ASK and CONSTRUCT/DESCRIBE queries to `<FUSEKI_URL>/sparql` (default `http://localhost:3030/football`), with a 60-second timeout; it never contacts any update endpoint.
- Any user text placed into SPARQL goes through `sparqlutil.escape_literal`; resource IRIs are built only with `common.Uris.res` after validating `kind` against `^[a-z][a-z-]*$`.
- Content types: `text/turtle`, `application/ld+json`, `application/rdf+xml`, `application/n-triples`; HTML is the default for `*/*`.
- Python style follows the existing code (flat modules in `src/`, stdlib first, no pandas).
- Commits: author is the repo-local git identity; end commit messages with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A user search string containing quotes, backslashes or newlines must never break out of the SPARQL string literal (Task 3).
2. A playground query that contains an update keyword only inside a string, IRI, comment, variable name or prefixed name must still run; a real `INSERT`/`DELETE`/`DROP`/... must be rejected (Task 3).
3. `Accept: */*` and browser Accept headers must land on HTML; every RDF media type must land on the matching `/data/...` document (Task 4).
4. Resource IDs with spaces, quotes or non-ASCII characters (stadium and referee names) must round-trip through `/resource`, `/page` and `/data` (Task 4).
5. Fuseki being down or rejecting a query must produce a clean 502/400 response, never a stack trace (Tasks 4, 5).

---

## File Structure

```
src/footballweb/__init__.py       exports create_app
src/footballweb/fuseki.py         FusekiClient, FusekiError, FusekiUnavailable
src/footballweb/sparqlutil.py     escape_literal, query_form
src/footballweb/rdfio.py          EXTS, MIME_EXT, OFFERS, parse_turtle, serialize
src/footballweb/entities.py       Entities (describe, page, search, related), fmt_number, short
src/footballweb/app.py            create_app (routes, error handlers, ontology summary)
src/footballweb/templates/*.html  base, index, search, entity, ontology, query, error
src/footballweb/static/style.css, query.js
tests/test_base_uri.py, tests/test_web_util.py, tests/test_web_entities.py, tests/test_web_app.py
docker/Dockerfile.web, .dockerignore
```

---

### Task 1: Real base URI

**Files:**
- Create: `tests/test_base_uri.py`
- Modify: `config.json`, `ontology/football.ttl`, `shapes/football-shapes.ttl`, `queries/*.rq`, `queries/checks/*.rq`, `tests/helpers.py`, `tests/conftest.py`, `tests/test_ontology.py` (all via one `sed`)

**Interfaces:**
- Produces: `config.json` with `ontology_base` = `https://vdhugn.github.io/Football-LOD/ontology#` and `resource_base` = `https://vdhugn.github.io/Football-LOD/resource/`; every later task reads these from `cfg` (the `cfg` test fixture in `tests/conftest.py` carries them too).

- [ ] **Step 1: Write the failing test `tests/test_base_uri.py`**

```python
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ["src", "ontology", "shapes", "queries", "tests", "scripts", "docker", "config.json", "Makefile"]


def test_no_placeholder_namespace_left():
    me = Path(__file__).resolve()
    hits = []
    for entry in SCAN:
        path = ROOT / entry
        files = [path] if path.is_file() else (p for p in path.rglob("*") if p.is_file())
        for f in files:
            if "__pycache__" in f.parts or f.resolve() == me:
                continue
            if "example.org" in f.read_text(encoding="utf-8", errors="ignore"):
                hits.append(str(f.relative_to(ROOT)))
    assert hits == []


def test_config_uses_the_real_namespace():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert cfg["resource_base"] == "https://vdhugn.github.io/Football-LOD/resource/"
    assert cfg["ontology_base"] == "https://vdhugn.github.io/Football-LOD/ontology#"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_base_uri.py -q 2>&1 | tail -6`
Expected: both tests FAIL (the first lists `config.json`, `ontology/football.ttl`, `queries/...`).

- [ ] **Step 3: Rewrite the namespace**

```bash
grep -rl "example.org" src ontology shapes queries tests config.json 2>/dev/null | grep -v __pycache__ | xargs sed -i \
  -e 's#https://example.org/football/ontology#https://vdhugn.github.io/Football-LOD/ontology#g' \
  -e 's#https://example.org/football/resource/#https://vdhugn.github.io/Football-LOD/resource/#g' \
  -e 's#https://example.org/football/shapes#https://vdhugn.github.io/Football-LOD/shapes#g'
grep -rn "example.org" src ontology shapes queries tests config.json scripts docker Makefile | grep -v __pycache__ | grep -v test_base_uri.py || echo "none left"
```
Expected: `none left`.

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/pytest -q 2>&1 | tail -4`
Expected: all tests pass (60 existing + 2 new).

- [ ] **Step 5: Regenerate data, links and the endpoint under the new namespace**

```bash
.venv/bin/python src/build_rdf.py | tail -3
.venv/bin/python src/validate.py vocab
.venv/bin/python src/link_wikidata.py | tr -d '\n' | sed 's/  */ /g'; echo
scripts/load.sh 2>&1 | grep -E "Time =|Endpoint|rror"
scripts/run_checks.sh; echo "checks exit=$?"
scripts/shacl.sh 2>&1 | grep conforms
grep -c "vdhugn.github.io" output/data/players.ttl output/links/wikidata.ttl
```
Expected: TOTAL about 14.18M triples, `vocabulary OK (8 files)`, link report with the same rates as before (players 0.9139, competitions 1.0), loader about 14.23M triples, all five checks `0`, `sh:conforms true`, and non-zero counts in the last grep. Relinking must be offline and fast (a few seconds).

- [ ] **Step 6: Commit**

```bash
git add -A tests config.json ontology shapes queries
git commit -m "feat: move to the real namespace https://vdhugn.github.io/Football-LOD/

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Fuseki client, SPARQL utilities and RDF I/O

**Files:**
- Create: `src/footballweb/__init__.py`, `src/footballweb/fuseki.py`, `src/footballweb/sparqlutil.py`, `src/footballweb/rdfio.py`, `tests/test_web_util.py`

**Interfaces:**
- Produces:
  - `fuseki.FusekiClient(base_url, timeout=60)` with `select(query)->dict` (SPARQL JSON results), `ask(query)->bool`, `construct(query)->str` (Turtle text); `fuseki.FusekiError(message)` for rejected queries (HTTP 4xx), `fuseki.FusekiUnavailable(message)` for unreachable or 5xx.
  - `sparqlutil.escape_literal(text)->str` (content for a double-quoted SPARQL string); `sparqlutil.query_form(query)->"select"|"ask"|"construct"|"describe"`, raising `ValueError(message)` for updates or other forms.
  - `rdfio.EXTS` (`{"ttl": (mime, rdflib_format), ...}` for `ttl`, `jsonld`, `rdf`, `nt`), `rdfio.MIME_EXT` (mime → ext), `rdfio.OFFERS` (`["text/html", *mimes]`), `rdfio.parse_turtle(text)->rdflib.Graph`, `rdfio.serialize(graph, ext)->bytes`.
- `src/footballweb/__init__.py` imports `create_app` from `.app`, which Task 4 creates; until then it must not import it (see step 3).

- [ ] **Step 1: Write the failing tests `tests/test_web_util.py`**

```python
import json
import urllib.error

import pytest
from rdflib import Graph, Literal, URIRef

from footballweb import fuseki, rdfio, sparqlutil


# ---------- escape_literal ----------

def test_escape_literal_neutralises_quotes_backslashes_and_newlines():
    assert sparqlutil.escape_literal('a"b') == 'a\\"b'
    assert sparqlutil.escape_literal("a\\b") == "a\\\\b"
    assert sparqlutil.escape_literal("a\nb\r\tc") == "a\\nb\\r\\tc"
    assert sparqlutil.escape_literal('"} UNION { ?s ?p ?o') == '\\"} UNION { ?s ?p ?o'


# ---------- query_form ----------

@pytest.mark.parametrize("query,form", [
    ("SELECT * WHERE { ?s ?p ?o }", "select"),
    ("PREFIX fb: <https://x/#>\nASK { ?s a fb:Player }", "ask"),
    ("# a comment\nCONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }", "construct"),
    ("describe <https://x/y>", "describe"),
    ('SELECT * WHERE { ?s ?p "INSERT DELETE DROP" }', "select"),      # keywords inside a string
    ("SELECT * WHERE { ?s ?p ?add . ?s <https://x/load> ?o }", "select"),   # variable / IRI
    ("SELECT * WHERE { ?s fb:create ?o }  # DROP everything", "select"),   # prefixed name + comment
    ("SELECT * WHERE { ?s ?p 'it''s' } # don't DELETE", "select"),
])
def test_query_form_accepts_read_queries(query, form):
    assert sparqlutil.query_form(query) == form


@pytest.mark.parametrize("query", [
    "INSERT DATA { <a> <b> <c> }",
    "DELETE WHERE { ?s ?p ?o }",
    "DROP ALL",
    "LOAD <http://x/y>",
    "CLEAR GRAPH <http://x/y>",
    "CREATE GRAPH <http://x/y>",
    "WITH <http://g> DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }",
    "SELECT * WHERE { ?s ?p ?o } ; DROP ALL",
    "   ",
    "this is not sparql",
])
def test_query_form_rejects_updates_and_garbage(query):
    with pytest.raises(ValueError):
        sparqlutil.query_form(query)


# ---------- rdfio ----------

def graph():
    g = Graph()
    g.add((URIRef("https://x/a"), URIRef("http://www.w3.org/2000/01/rdf-schema#label"), Literal("Türkiye", lang="en")))
    return g


def test_serialize_every_format():
    g = graph()
    assert b"T\xc3\xbcrkiye" in rdfio.serialize(g, "ttl")
    assert json.loads(rdfio.serialize(g, "jsonld"))
    assert b"rdf:RDF" in rdfio.serialize(g, "rdf")
    assert rdfio.serialize(g, "nt").strip().endswith(b".")
    assert set(rdfio.EXTS) == {"ttl", "jsonld", "rdf", "nt"}
    assert rdfio.OFFERS[0] == "text/html" and rdfio.MIME_EXT["text/turtle"] == "ttl"


def test_parse_turtle_round_trip():
    g = rdfio.parse_turtle(rdfio.serialize(graph(), "ttl").decode())
    assert len(g) == 1


# ---------- FusekiClient ----------

class FakeResponse:
    def __init__(self, body): self.body = body.encode()
    def read(self): return self.body
    def __enter__(self): return self
    def __exit__(self, *a): return False


def client_with(monkeypatch, behaviour):
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append((req.full_url, req.data.decode(), req.get_header("Accept"), timeout))
        return behaviour(req)

    monkeypatch.setattr(fuseki.urllib.request, "urlopen", fake_urlopen)
    return fuseki.FusekiClient("http://h:3030/football/", timeout=7), calls


def test_client_select_ask_construct(monkeypatch):
    def behaviour(req):
        accept = req.get_header("Accept")
        if accept == "text/turtle":
            return FakeResponse("<a> <b> <c> .")
        return FakeResponse(json.dumps({"head": {"vars": []}, "boolean": True, "results": {"bindings": []}}))

    c, calls = client_with(monkeypatch, behaviour)
    assert c.select("SELECT 1")["results"]["bindings"] == []
    assert c.ask("ASK {}") is True
    assert c.construct("CONSTRUCT {} WHERE {}") == "<a> <b> <c> ."
    assert calls[0][0] == "http://h:3030/football/sparql"
    assert calls[0][1].startswith("query=") and calls[0][3] == 7
    assert calls[0][2] == "application/sparql-results+json" and calls[2][2] == "text/turtle"


def test_client_maps_http_and_network_errors(monkeypatch):
    def http(code, body):
        def behaviour(req):
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, __import__("io").BytesIO(body.encode()))
        return behaviour

    c, _ = client_with(monkeypatch, http(400, "Parse error: unexpected }"))
    with pytest.raises(fuseki.FusekiError, match="Parse error"):
        c.select("bad")
    c, _ = client_with(monkeypatch, http(503, "overloaded"))
    with pytest.raises(fuseki.FusekiUnavailable):
        c.select("x")

    def down(req):
        raise urllib.error.URLError("connection refused")

    c, _ = client_with(monkeypatch, down)
    with pytest.raises(fuseki.FusekiUnavailable):
        c.ask("ASK {}")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_web_util.py -q 2>&1 | tail -4`
Expected: FAIL / collection error (`No module named 'footballweb'`).

- [ ] **Step 3: Write `src/footballweb/__init__.py` (temporary, no app yet)**

```python
"""Football LOD web application."""
```

- [ ] **Step 4: Write `src/footballweb/fuseki.py`**

```python
"""Thin read-only client for the Fuseki SPARQL query endpoint."""
import json
import urllib.error
import urllib.parse
import urllib.request


class FusekiError(Exception):
    """The endpoint rejected the query (HTTP 4xx)."""


class FusekiUnavailable(Exception):
    """The endpoint could not be reached or failed (network error, HTTP 5xx)."""


class FusekiClient:
    def __init__(self, base_url, timeout=60):
        self.endpoint = base_url.rstrip("/") + "/sparql"
        self.timeout = timeout

    def _post(self, query, accept):
        data = urllib.parse.urlencode({"query": query}).encode("utf-8")
        req = urllib.request.Request(self.endpoint, data=data, headers={
            "Accept": accept, "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace").strip()[:500] or f"HTTP {e.code}"
            raise (FusekiError if e.code < 500 else FusekiUnavailable)(body) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise FusekiUnavailable(str(e)) from e

    def select(self, query):
        return json.loads(self._post(query, "application/sparql-results+json"))

    def ask(self, query):
        return bool(json.loads(self._post(query, "application/sparql-results+json"))["boolean"])

    def construct(self, query):
        return self._post(query, "text/turtle")
```

- [ ] **Step 5: Write `src/footballweb/sparqlutil.py`**

```python
"""SPARQL helpers: literal escaping and a read-only query guard."""
import re

_ESC = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}

# strings, IRIs and comments, matched left to right so that '#' inside a string or IRI
# and quotes inside a comment never confuse each other
_NOISE = re.compile(
    r'"""(?s:.*?)"""|\'\'\'(?s:.*?)\'\'\'|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\''
    r"|<[^<>\"{}|^`\\\s]*>|#[^\n]*"
)
_WORD = re.compile(r"(?<![?$:\w])[A-Za-z_]+(?![\w:])")
UPDATE_WORDS = {"INSERT", "DELETE", "LOAD", "CLEAR", "DROP", "CREATE", "COPY", "MOVE", "ADD", "WITH"}
FORMS = ("SELECT", "ASK", "CONSTRUCT", "DESCRIBE")


def escape_literal(text):
    """Escape text for use inside a double-quoted SPARQL string literal."""
    return "".join(_ESC.get(c, c) for c in text)


def query_form(query):
    """Return 'select', 'ask', 'construct' or 'describe'; raise ValueError for anything else."""
    cleaned = _NOISE.sub(" ", query)
    words = [w.upper() for w in _WORD.findall(cleaned)]
    if any(w in UPDATE_WORDS for w in words):
        raise ValueError("Update operations are not allowed; use SELECT, ASK, CONSTRUCT or DESCRIBE.")
    for w in words:
        if w in FORMS:
            return w.lower()
    raise ValueError("Only SELECT, ASK, CONSTRUCT and DESCRIBE queries are allowed.")
```

- [ ] **Step 6: Write `src/footballweb/rdfio.py`**

```python
"""RDF serialisation formats offered by the web app."""
from rdflib import Graph

EXTS = {
    "ttl": ("text/turtle", "turtle"),
    "jsonld": ("application/ld+json", "json-ld"),
    "rdf": ("application/rdf+xml", "xml"),
    "nt": ("application/n-triples", "nt"),
}
MIME_EXT = {mime: ext for ext, (mime, _) in EXTS.items()}
OFFERS = ["text/html"] + list(MIME_EXT)


def parse_turtle(text):
    g = Graph()
    g.parse(data=text, format="turtle")
    return g


def serialize(graph, ext):
    return graph.serialize(format=EXTS[ext][1]).encode("utf-8")
```

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/pytest -q 2>&1 | tail -8`
Expected: all pass. If a `query_form` case fails, fix the regexes in `sparqlutil.py`, not the test: the cases encode the Review Focus.

- [ ] **Step 8: Commit**

```bash
git add src/footballweb tests/test_web_util.py
git commit -m "feat(web): Fuseki client, SPARQL guard and RDF serialisation helpers

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Entity model (search, entity page data)

**Files:**
- Create: `src/footballweb/entities.py`, `tests/test_web_entities.py`

**Interfaces:**
- Consumes: `common.Uris`, `common.clean`, `sparqlutil.escape_literal`, a client with `select/ask/construct` (real or fake).
- Produces: `entities.KIND_RE`; `entities.short(uri)->str`; `entities.fmt_number(text)->str`; `entities.Entities(client, cfg)` with:
  - `iri(kind, key)->str|None` (`"<...>"`, as `Uris.res`)
  - `exists(iri)->bool`; `describe_graph(iri)->str` (Turtle of outgoing triples)
  - `search(text)->list[{"label","type","href"}]`
  - `page(kind, key)->dict|None` with keys `title`, `uri`, `types` (list of str), `depiction` (str|None), `external` (list of `{"pred","uri"}`), `groups` (list of `{"name","values"}`; each value `{"kind":"uri"|"literal","text","href","internal","meta"}`), `related` (dict; see Step 4), or `None` when the resource has no triples.

- [ ] **Step 1: Write the failing tests `tests/test_web_entities.py`**

```python
import pytest

from footballweb import entities
from footballweb.entities import Entities, fmt_number, short
from helpers import FB, R

LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
SAME = "http://www.w3.org/2002/07/owl#sameAs"
DEPICT = "http://xmlns.com/foaf/0.1/depiction"


def uri(v, label=None):
    row = {"type": "uri", "value": v}
    return row


def lit(v, datatype=None, lang=None):
    d = {"type": "literal", "value": v}
    if datatype:
        d["datatype"] = datatype
    if lang:
        d["xml:lang"] = lang
    return d


def row(p, o, ol=None):
    b = {"p": {"type": "uri", "value": p}, "o": o}
    if ol:
        b["ol"] = lit(ol)
    return b


def result(vars_, rows):
    return {"head": {"vars": vars_}, "results": {"bindings": rows}}


class Fake:
    """Answers SPARQL by looking for a marker in the query text."""
    def __init__(self, routes, ask=True, construct=""):
        self.routes, self._ask, self._construct, self.queries = routes, ask, construct, []

    def select(self, q):
        self.queries.append(q)
        for marker, data in self.routes.items():
            if marker in q:
                return data
        return result([], [])

    def ask(self, q):
        self.queries.append(q)
        return self._ask

    def construct(self, q):
        self.queries.append(q)
        return self._construct


@pytest.fixture
def cfg():
    return {"ontology_base": FB, "resource_base": R}


def test_short_and_fmt_number():
    assert short("https://x/y#Player") == "Player" and short("https://x/y/z/") == "z"
    assert fmt_number("120000000") == "120,000,000"
    assert fmt_number("120000000.0") == "120,000,000"
    assert fmt_number("27.1") == "27.1"
    assert fmt_number("abc") == "abc"


def test_iri_validates_and_quotes(cfg):
    e = Entities(Fake({}), cfg)
    assert e.iri("player", "10") == f"<{R}player/10>"
    assert e.iri("stadium", "Allianz Arena") == f"<{R}stadium/Allianz%20Arena>"
    assert e.iri("player", "") is None


def test_search_escapes_user_text_and_lowercases(cfg):
    fake = Fake({"?label": result(["s", "label", "type"], [
        {"s": uri(f"{R}player/10"), "label": lit("Bukayo Saka"), "type": uri(FB + "Player")}])})
    e = Entities(fake, cfg)
    out = e.search('O"Brien\\ \n')
    q = fake.queries[0]
    assert 'o\\"brien\\\\ \\n' in q                       # lower-cased and escaped, still one literal
    assert "LIMIT 25" in q
    assert out == [{"label": "Bukayo Saka", "type": "Player", "href": "/page/player/10"}]


def test_search_skips_foreign_uris(cfg):
    fake = Fake({"?label": result(["s", "label", "type"], [
        {"s": uri("https://other.example/x"), "label": lit("X"), "type": uri(FB + "Club")}])})
    assert Entities(fake, cfg).search("x") == []


def player_rows():
    return [
        row(TYPE, uri(FB + "Player")),
        row(LABEL, lit("Bukayo Saka", lang="und")),
        row(FB + "playsFor", uri(f"{R}club/11"), "Arsenal FC"),
        row(FB + "heightCm", lit("178", datatype="http://www.w3.org/2001/XMLSchema#integer")),
        row(FB + "currentMarketValueEUR", lit("120000000.0", datatype="http://www.w3.org/2001/XMLSchema#decimal")),
        row(SAME, uri("http://www.wikidata.org/entity/Q1")),
        row(DEPICT, uri("https://img.example/10.jpg")),
    ]


def test_page_player(cfg):
    fake = Fake({
        "GROUP BY ?p ?o": result(["p", "o", "ol"], player_rows()),
        "fb:transferOf": result(["date", "from", "fl", "to", "tl", "fee"], [{
            "date": lit("2023-01-01"), "from": uri(f"{R}club/11"), "fl": lit("Arsenal FC"),
            "to": uri(f"{R}club/148"), "tl": lit("Tottenham Hotspur"), "fee": lit("5000000.0")}]),
        "fb:valuationOf": result(["date", "value"], [{"date": lit("2023-06-01"), "value": lit("100000000.0")}]),
        "COUNT(?a)": result(["apps", "goals"], [{"apps": lit("12"), "goals": lit("3")}]),
    })
    p = Entities(fake, cfg).page("player", "10")
    assert p["title"] == "Bukayo Saka" and p["types"] == ["Player"]
    assert p["uri"] == f"{R}player/10"
    assert p["depiction"] == "https://img.example/10.jpg"
    assert p["external"] == [{"pred": "sameAs", "uri": "http://www.wikidata.org/entity/Q1"}]
    names = [g["name"] for g in p["groups"]]
    assert names == sorted(names) and "playsFor" in names and "sameAs" not in names and "type" not in names
    plays = next(g for g in p["groups"] if g["name"] == "playsFor")["values"][0]
    assert plays == {"kind": "uri", "text": "Arsenal FC", "href": "/page/club/11", "internal": True, "meta": None}
    value = next(g for g in p["groups"] if g["name"] == "currentMarketValueEUR")["values"][0]
    assert value["text"] == "120,000,000" and value["meta"] == "decimal"
    rel = p["related"]
    assert rel["transfers"] == [{"date": "2023-01-01", "from": {"text": "Arsenal FC", "href": "/page/club/11"},
                                 "to": {"text": "Tottenham Hotspur", "href": "/page/club/148"}, "fee": "5,000,000"}]
    assert rel["valuations"] == [{"date": "2023-06-01", "value": "100,000,000"}]
    assert rel["totals"] == {"appearances": "12", "goals": "3"}


def test_page_club_squad(cfg):
    fake = Fake({
        "GROUP BY ?p ?o": result(["p", "o", "ol"], [row(TYPE, uri(FB + "Club")), row(LABEL, lit("Arsenal FC"))]),
        "fb:playsFor": result(["p", "label", "value"], [
            {"p": uri(f"{R}player/10"), "label": lit("Bukayo Saka"), "value": lit("120000000.0")},
            {"p": uri(f"{R}player/20"), "label": lit("Unvalued")}]),
    })
    p = Entities(fake, cfg).page("club", "11")
    assert p["related"] == {"squad": [
        {"text": "Bukayo Saka", "href": "/page/player/10", "value": "120,000,000"},
        {"text": "Unvalued", "href": "/page/player/20", "value": None}]}


def test_page_other_kinds_have_no_related_and_unknown_is_none(cfg):
    fake = Fake({"GROUP BY ?p ?o": result(["p", "o", "ol"], [row(LABEL, lit("Premier League"))])})
    assert Entities(fake, cfg).page("competition", "GB1")["related"] == {}
    assert Entities(Fake({}), cfg).page("player", "999") is None          # no triples
    assert Entities(Fake({}), cfg).page("player", "") is None


def test_title_falls_back_to_uri(cfg):
    fake = Fake({"GROUP BY ?p ?o": result(["p", "o", "ol"], [row(FB + "goals", lit("1"))])})
    assert Entities(fake, cfg).page("appearance", "a1")["title"] == f"{R}appearance/a1"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_web_entities.py -q 2>&1 | tail -4`
Expected: FAIL (`cannot import name 'entities'`).

- [ ] **Step 3: Write `src/footballweb/entities.py`**

```python
"""Entity model: SPARQL queries and view data for search results and entity pages."""
import re
from decimal import Decimal, InvalidOperation

from common import Uris, clean

from .sparqlutil import escape_literal

KIND_RE = re.compile(r"^[a-z][a-z-]*$")
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
FOAF_DEPICTION = "http://xmlns.com/foaf/0.1/depiction"
EXTERNAL = {
    "http://www.w3.org/2002/07/owl#sameAs",
    "http://www.w3.org/2004/02/skos/core#closeMatch",
    "http://www.w3.org/2000/01/rdf-schema#seeAlso",
    FOAF_DEPICTION,
}
NUMERIC = ("integer", "decimal", "double", "float")


def short(uri):
    return re.split(r"[#/]", uri.rstrip("/"))[-1]


def fmt_number(text):
    try:
        d = Decimal(text)
    except InvalidOperation:
        return text
    return f"{d:,.0f}" if d == d.to_integral_value() else f"{d:,}"


def _val(binding, name):
    cell = binding.get(name)
    return cell["value"] if cell else None


class Entities:
    def __init__(self, client, cfg):
        self.client = client
        self.uris = Uris(cfg)
        self.base = cfg["resource_base"]
        self.prefixes = (f"PREFIX fb: <{cfg['ontology_base']}>\n"
                         "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n")

    # ---------- URIs ----------

    def iri(self, kind, key):
        return self.uris.res(kind, key)

    def local(self, uri):
        """Canonical resource URI -> local page path, or None for foreign URIs."""
        return "/page/" + uri[len(self.base):] if uri.startswith(self.base) else None

    # ---------- raw access ----------

    def exists(self, iri):
        return self.client.ask(f"ASK {{ {iri} ?p ?o }}")

    def describe_graph(self, iri):
        return self.client.construct(f"CONSTRUCT {{ {iri} ?p ?o }} WHERE {{ {iri} ?p ?o }}")

    # ---------- search ----------

    def search(self, text):
        needle = escape_literal(text.lower())
        q = (self.prefixes +
             "SELECT ?s ?label ?type WHERE { "
             "VALUES ?type { fb:Player fb:Club fb:NationalTeam fb:Competition fb:Country } "
             "?s a ?type ; rdfs:label ?label . "
             f'FILTER(CONTAINS(LCASE(STR(?label)), "{needle}")) '
             "} ORDER BY ?label LIMIT 25")
        out = []
        for b in self.client.select(q)["results"]["bindings"]:
            href = self.local(b["s"]["value"])
            if href:
                out.append({"label": b["label"]["value"], "type": short(b["type"]["value"]), "href": href})
        return out

    # ---------- entity page ----------

    def _item(self, o, olabel):
        if o["type"] == "uri":
            href = self.local(o["value"])
            return {"kind": "uri", "text": olabel or short(o["value"]), "href": href or o["value"],
                    "internal": href is not None, "meta": None}
        dt = short(o["datatype"]) if o.get("datatype") else None
        text = fmt_number(o["value"]) if dt in NUMERIC else o["value"]
        return {"kind": "literal", "text": text, "href": None, "internal": False,
                "meta": dt or o.get("xml:lang")}

    def page(self, kind, key):
        iri = self.iri(kind, key)
        if iri is None:
            return None
        q = (self.prefixes +
             f"SELECT ?p ?o (SAMPLE(?l) AS ?ol) WHERE {{ {iri} ?p ?o . OPTIONAL {{ ?o rdfs:label ?l }} }} "
             "GROUP BY ?p ?o ORDER BY ?p LIMIT 500")
        rows = self.client.select(q)["results"]["bindings"]
        if not rows:
            return None
        uri = iri[1:-1]
        title, types, external, depiction, groups = None, [], [], None, {}
        for b in rows:
            p, o = b["p"]["value"], b["o"]
            if p == RDF_TYPE:
                types.append(short(o["value"]))
            elif p in EXTERNAL:
                external.append({"pred": short(p), "uri": o["value"]})
                if p == FOAF_DEPICTION:
                    depiction = o["value"]
            else:
                if p == RDFS_LABEL and title is None:
                    title = o["value"]
                groups.setdefault(p, []).append(self._item(o, _val(b, "ol")))
        return {
            "title": title or uri, "uri": uri, "types": types, "depiction": depiction,
            "external": external,
            "groups": [{"name": short(p), "values": v} for p, v in sorted(groups.items(), key=lambda kv: short(kv[0]))],
            "related": self._related(kind, iri),
        }

    # ---------- kind-specific sections ----------

    def _related(self, kind, iri):
        if kind == "player":
            return {"transfers": self._transfers(iri), "valuations": self._valuations(iri),
                    "totals": self._totals(iri)}
        if kind == "club":
            return {"squad": self._squad(iri)}
        return {}

    def _club_ref(self, b, uri_name, label_name):
        uri = _val(b, uri_name)
        return {"text": _val(b, label_name) or short(uri), "href": self.local(uri) or uri}

    def _transfers(self, iri):
        q = (self.prefixes +
             f"SELECT ?date ?from ?fl ?to ?tl ?fee WHERE {{ ?t fb:transferOf {iri} ; fb:transferDate ?date ; "
             "fb:fromClub ?from ; fb:toClub ?to . OPTIONAL { ?t fb:transferFee ?fee } "
             "OPTIONAL { ?from rdfs:label ?fl } OPTIONAL { ?to rdfs:label ?tl } } "
             "ORDER BY DESC(?date) LIMIT 50")
        out = []
        for b in self.client.select(q)["results"]["bindings"]:
            fee = _val(b, "fee")
            out.append({"date": _val(b, "date"), "from": self._club_ref(b, "from", "fl"),
                        "to": self._club_ref(b, "to", "tl"), "fee": fmt_number(fee) if fee else None})
        return out

    def _valuations(self, iri):
        q = (self.prefixes +
             f"SELECT ?date ?value WHERE {{ ?v fb:valuationOf {iri} ; fb:valuationDate ?date ; fb:valueEUR ?value }} "
             "ORDER BY DESC(?date) LIMIT 100")
        return [{"date": _val(b, "date"), "value": fmt_number(_val(b, "value"))}
                for b in self.client.select(q)["results"]["bindings"]]

    def _totals(self, iri):
        q = (self.prefixes +
             f"SELECT (COUNT(?a) AS ?apps) (SUM(?g) AS ?goals) WHERE {{ ?a fb:appearanceOf {iri} . "
             "OPTIONAL { ?a fb:goals ?g } }")
        rows = self.client.select(q)["results"]["bindings"]
        b = rows[0] if rows else {}
        return {"appearances": _val(b, "apps") or "0", "goals": _val(b, "goals") or "0"}

    def _squad(self, iri):
        q = (self.prefixes +
             f"SELECT ?p ?label ?value WHERE {{ ?p fb:playsFor {iri} ; rdfs:label ?label . "
             "OPTIONAL { ?p fb:currentMarketValueEUR ?value } } ORDER BY DESC(?value) LIMIT 60")
        out = []
        for b in self.client.select(q)["results"]["bindings"]:
            href = self.local(_val(b, "p"))
            if href:
                value = _val(b, "value")
                out.append({"text": _val(b, "label"), "href": href, "value": fmt_number(value) if value else None})
        return out
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest -q 2>&1 | tail -8`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/footballweb/entities.py tests/test_web_entities.py
git commit -m "feat(web): entity model for search and entity pages

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Flask app: routes, negotiation, templates

**Files:**
- Create: `src/footballweb/app.py`, `src/footballweb/templates/base.html`, `index.html`, `search.html`, `entity.html`, `ontology.html`, `query.html`, `error.html`, `src/footballweb/static/style.css`, `src/footballweb/static/query.js`, `tests/test_web_app.py`
- Modify: `src/footballweb/__init__.py`, `requirements.txt`

**Interfaces:**
- Consumes: Task 2 and Task 3 modules; `common.load_config`.
- Produces: `footballweb.create_app(cfg=None, client=None, root=<repo root>) -> flask.Flask` with endpoints named `index`, `search`, `resource`, `page`, `data`, `ontology_view`, `query_page`, `api_query`, `api_examples`; routes and behaviours exactly as in spec section 3.

- [ ] **Step 1: Add dependencies**

Append to `requirements.txt`:
```
flask>=3.0
gunicorn>=22.0
```

- [ ] **Step 2: Write the failing tests `tests/test_web_app.py`**

```python
import json

import pytest
from rdflib import Graph

from footballweb import create_app
from footballweb.fuseki import FusekiError, FusekiUnavailable
from helpers import FB, R

PLAYER_TTL = f"""@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<{R}player/10> rdfs:label "Bukayo Saka"@und .
"""
LABEL = "http://www.w3.org/2000/01/rdf-schema#label"


def result(vars_, rows):
    return {"head": {"vars": vars_}, "results": {"bindings": rows}}


class Fake:
    def __init__(self, routes=None, ask=True, construct=PLAYER_TTL, error=None):
        self.routes, self._ask, self._construct, self.error, self.queries = routes or {}, ask, construct, error, []

    def _maybe_fail(self):
        if self.error:
            raise self.error

    def select(self, q):
        self.queries.append(q)
        self._maybe_fail()
        for marker, data in self.routes.items():
            if marker in q:
                return data
        return result([], [])

    def ask(self, q):
        self.queries.append(q)
        self._maybe_fail()
        return self._ask

    def construct(self, q):
        self.queries.append(q)
        self._maybe_fail()
        return self._construct


@pytest.fixture
def cfg():
    return {"ontology_base": FB, "resource_base": R, "competitions": []}


def client_for(cfg, fake):
    app = create_app(cfg=cfg, client=fake)
    app.testing = True
    return app.test_client()


# ---------- content negotiation ----------

@pytest.mark.parametrize("accept,target", [
    ("text/html", "/page/player/10"),
    ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "/page/player/10"),
    ("*/*", "/page/player/10"),
    (None, "/page/player/10"),
    ("text/turtle", "/data/player/10.ttl"),
    ("application/ld+json", "/data/player/10.jsonld"),
    ("application/rdf+xml", "/data/player/10.rdf"),
    ("application/n-triples", "/data/player/10.nt"),
])
def test_resource_redirects_by_accept_header(cfg, accept, target):
    c = client_for(cfg, Fake())
    r = c.get("/resource/player/10", headers={"Accept": accept} if accept else {})
    assert r.status_code == 303 and r.headers["Location"].endswith(target)


def test_resource_unknown_or_invalid_is_404(cfg):
    assert client_for(cfg, Fake(ask=False)).get("/resource/player/999").status_code == 404
    assert client_for(cfg, Fake()).get("/resource/Bad_Kind/1").status_code == 404
    assert client_for(cfg, Fake()).get("/page/Bad_Kind/1").status_code == 404
    assert client_for(cfg, Fake()).get("/data/Bad_Kind/1.ttl").status_code == 404


def test_ids_with_special_characters_round_trip(cfg):
    fake = Fake()
    c = client_for(cfg, fake)
    r = c.get("/resource/stadium/Allianz%20Arena", headers={"Accept": "text/turtle"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/data/stadium/Allianz%20Arena.ttl")
    c.get("/data/stadium/Allianz%20Arena.ttl")
    assert f"<{R}stadium/Allianz%20Arena>" in fake.queries[-1]
    r = c.get('/resource/referee/Mr_%22Q%22', headers={"Accept": "text/turtle"})
    assert r.status_code == 303
    c.get('/data/referee/Mr_%22Q%22.ttl')
    assert f"<{R}referee/Mr_%22Q%22>" in fake.queries[-1]


# ---------- data documents ----------

def test_data_in_every_format(cfg):
    c = client_for(cfg, Fake())
    ttl = c.get("/data/player/10.ttl")
    assert ttl.status_code == 200 and ttl.mimetype == "text/turtle" and b"Bukayo Saka" in ttl.data
    js = c.get("/data/player/10.jsonld")
    assert js.mimetype == "application/ld+json" and json.loads(js.data)
    assert b"rdf:RDF" in c.get("/data/player/10.rdf").data
    nt = c.get("/data/player/10.nt")
    assert nt.mimetype == "application/n-triples" and nt.data.strip().endswith(b".")
    for body in (ttl.data, js.data, nt.data):
        g = Graph()
        g.parse(data=body.decode(), format={"ttl": "turtle"}.get("ttl") if body is ttl.data else ("json-ld" if body is js.data else "nt"))
        assert len(g) == 1


def test_data_unknown_extension_or_empty_graph_is_404(cfg):
    assert client_for(cfg, Fake()).get("/data/player/10.pdf").status_code == 404
    assert client_for(cfg, Fake()).get("/data/player/10").status_code == 404
    assert client_for(cfg, Fake(construct="")).get("/data/player/10.ttl").status_code == 404


# ---------- HTML pages ----------

def test_entity_page_renders_data_and_links(cfg):
    rows = [
        {"p": {"type": "uri", "value": LABEL}, "o": {"type": "literal", "value": "Bukayo Saka", "xml:lang": "und"}},
        {"p": {"type": "uri", "value": FB + "playsFor"}, "o": {"type": "uri", "value": f"{R}club/11"},
         "ol": {"type": "literal", "value": "Arsenal FC"}},
        {"p": {"type": "uri", "value": "http://www.w3.org/2002/07/owl#sameAs"},
         "o": {"type": "uri", "value": "http://www.wikidata.org/entity/Q1"}},
    ]
    fake = Fake({"GROUP BY ?p ?o": result(["p", "o", "ol"], rows),
                 "fb:transferOf": result(["date", "from", "fl", "to", "tl", "fee"], [{
                     "date": {"type": "literal", "value": "2023-01-01"},
                     "from": {"type": "uri", "value": f"{R}club/11"}, "fl": {"type": "literal", "value": "Arsenal FC"},
                     "to": {"type": "uri", "value": f"{R}club/148"}, "tl": {"type": "literal", "value": "Spurs"},
                     "fee": {"type": "literal", "value": "5000000.0"}}]),
                 "COUNT(?a)": result(["apps", "goals"], [{"apps": {"type": "literal", "value": "12"},
                                                          "goals": {"type": "literal", "value": "3"}}])})
    html = client_for(cfg, fake).get("/page/player/10").get_data(as_text=True)
    assert "Bukayo Saka" in html and f"{R}player/10" in html
    assert 'href="/page/club/11"' in html and "Arsenal FC" in html
    assert 'href="http://www.wikidata.org/entity/Q1"' in html
    assert "Transfers" in html and "5,000,000" in html and "2023-01-01" in html
    assert "/data/player/10.ttl" in html and "/data/player/10.jsonld" in html
    assert "<script>" not in html.split("</head>")[1].split("<script src")[0]


def test_entity_page_escapes_hostile_values(cfg):
    rows = [{"p": {"type": "uri", "value": LABEL}, "o": {"type": "literal", "value": "<script>alert(1)</script>"}}]
    html = client_for(cfg, Fake({"GROUP BY ?p ?o": result(["p", "o", "ol"], rows)})).get("/page/player/10").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_unknown_entity_page_is_404_html(cfg):
    r = client_for(cfg, Fake()).get("/page/player/999")
    assert r.status_code == 404 and "text/html" in r.content_type


def test_search_page(cfg):
    rows = [{"s": {"type": "uri", "value": f"{R}player/10"}, "label": {"type": "literal", "value": "Bukayo Saka"},
             "type": {"type": "uri", "value": FB + "Player"}}]
    c = client_for(cfg, Fake({"?label": result(["s", "label", "type"], rows)}))
    ok = c.get("/search?q=saka")
    assert ok.status_code == 200 and 'href="/page/player/10"' in ok.get_data(as_text=True)
    assert c.get("/search?q=a").status_code == 400
    assert c.get("/search?q=" + "x" * 81).status_code == 400
    assert c.get("/search").status_code == 200                     # empty form
    assert c.get("/search?q=none-here").status_code == 200


def test_static_pages_render(cfg):
    c = client_for(cfg, Fake())
    for path in ("/", "/query", "/ontology"):
        r = c.get(path)
        assert r.status_code == 200 and "text/html" in r.content_type, path


# ---------- ontology ----------

def test_ontology_html_and_rdf(cfg):
    c = client_for(cfg, Fake())
    html = c.get("/ontology").get_data(as_text=True)
    assert "Player" in html and "playsFor" in html and "Team" in html
    ttl = c.get("/ontology", headers={"Accept": "text/turtle"})
    assert ttl.mimetype == "text/turtle" and ttl.headers["Content-Location"] == "/ontology.ttl"
    assert b"Player" in ttl.data
    assert json.loads(c.get("/ontology.jsonld").data)
    assert c.get("/ontology.pdf").status_code == 404


# ---------- playground API ----------

def api(c, query):
    return c.post("/api/query", json={"query": query})


def test_api_select_ask_and_graph(cfg):
    fake = Fake({"SELECT": result(["a", "b"], [{"a": {"type": "literal", "value": "1"}}])},
                construct="<a> <b> <c> .")
    fake.ask = lambda q: True
    c = client_for(cfg, fake)
    sel = api(c, "SELECT ?a ?b WHERE { ?a ?b ?c }").get_json()
    assert sel == {"form": "select", "vars": ["a", "b"], "rows": [{"a": "1", "b": None}], "truncated": False}
    assert api(c, "ASK { ?s ?p ?o }").get_json() == {"form": "ask", "boolean": True}
    assert api(c, "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }").get_json() == {"form": "graph", "turtle": "<a> <b> <c> ."}


def test_api_truncates_to_1000_rows(cfg):
    rows = [{"a": {"type": "literal", "value": str(i)}} for i in range(1001)]
    out = api(client_for(cfg, Fake({"SELECT": result(["a"], rows)})), "SELECT ?a WHERE { ?a ?b ?c }").get_json()
    assert len(out["rows"]) == 1000 and out["truncated"] is True


def test_api_rejects_updates_and_bad_input_without_calling_fuseki(cfg):
    fake = Fake()
    c = client_for(cfg, fake)
    r = api(c, "INSERT DATA { <a> <b> <c> }")
    assert r.status_code == 400 and "not allowed" in r.get_json()["error"]
    assert api(c, "").status_code == 400
    assert c.post("/api/query", json={"query": 5}).status_code == 400
    assert c.post("/api/query", data="not json").status_code == 400
    assert api(c, "SELECT * WHERE { ?s ?p ?o } # " + "x" * 20001).status_code == 400
    assert fake.queries == []
    assert api(c, 'SELECT * WHERE { ?s ?p "INSERT" }').status_code == 200


def test_api_maps_fuseki_errors(cfg):
    r = api(client_for(cfg, Fake(error=FusekiError("Parse error at line 1"))), "SELECT * WHERE { ?s ?p ?o }")
    assert r.status_code == 400 and r.get_json() == {"error": "Parse error at line 1"}
    r = api(client_for(cfg, Fake(error=FusekiUnavailable("connection refused"))), "SELECT * WHERE { ?s ?p ?o }")
    assert r.status_code == 502 and "SPARQL endpoint" in r.get_json()["error"]


def test_api_examples_lists_the_competency_queries(cfg):
    ex = client_for(cfg, Fake()).get("/api/examples").get_json()
    assert len(ex) == 9 and all(e["query"].strip() and e["name"] and e["id"] for e in ex)
    assert ex[0]["id"].startswith("q01")


# ---------- failure pages ----------

def test_fuseki_down_gives_clean_502_page(cfg):
    c = client_for(cfg, Fake(error=FusekiUnavailable("connection refused")))
    for path in ("/resource/player/10", "/page/player/10", "/search?q=saka"):
        r = c.get(path)
        text = r.get_data(as_text=True)
        assert r.status_code == 502 and "SPARQL endpoint" in text and "Traceback" not in text, path
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/pytest tests/test_web_app.py -q 2>&1 | tail -4`
Expected: FAIL / collection error (`cannot import name 'create_app'`).

- [ ] **Step 4: Write `src/footballweb/__init__.py`**

```python
"""Football LOD web application."""
from .app import create_app

__all__ = ["create_app"]
```

- [ ] **Step 5: Write `src/footballweb/app.py`**

```python
"""Flask application: entity pages, content negotiation, ontology and SPARQL playground."""
import os
from pathlib import Path

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, url_for
from rdflib import OWL, RDF, RDFS, Graph

from common import load_config

from .entities import KIND_RE, Entities, short
from .fuseki import FusekiClient, FusekiError, FusekiUnavailable
from .rdfio import EXTS, MIME_EXT, OFFERS, parse_turtle, serialize
from .sparqlutil import query_form

ROOT = Path(__file__).resolve().parents[2]
MAX_ROWS = 1000
MAX_QUERY_CHARS = 20000
UNAVAILABLE = "The SPARQL endpoint could not be reached. Is Fuseki running (scripts/load.sh)?"


def summarize_ontology(g, onto_base):
    def local(term):
        s = str(term)
        return s[len(onto_base):] if s.startswith(onto_base) else short(s)

    def comment(term):
        c = g.value(term, RDFS.comment)
        return str(c) if c else ""

    classes = []
    for c in sorted(g.subjects(RDF.type, OWL.Class), key=str):
        if str(c).startswith(onto_base):
            classes.append({"name": local(c), "comment": comment(c),
                            "parents": [local(p) for p in g.objects(c, RDFS.subClassOf) if str(p).startswith(onto_base)]})
    props = []
    for kind, typ in (("object", OWL.ObjectProperty), ("datatype", OWL.DatatypeProperty)):
        for p in sorted(g.subjects(RDF.type, typ), key=str):
            if str(p).startswith(onto_base):
                dom, rng = g.value(p, RDFS.domain), g.value(p, RDFS.range)
                props.append({"name": local(p), "kind": kind, "comment": comment(p),
                              "domain": local(dom) if dom else "", "range": local(rng) if rng else ""})
    return {"classes": classes, "properties": sorted(props, key=lambda x: x["name"])}


def create_app(cfg=None, client=None, root=ROOT):
    root = Path(root)
    cfg = cfg or load_config(root / "config.json")
    client = client or FusekiClient(os.environ.get("FUSEKI_URL", "http://localhost:3030/football"))
    app = Flask(__name__)
    ent = Entities(client, cfg)

    ontology = Graph()
    ontology.parse(str(root / "ontology" / "football.ttl"), format="turtle")
    onto_summary = summarize_ontology(ontology, cfg["ontology_base"])

    def examples():
        out = []
        for f in sorted((root / "queries").glob("q*.rq")):
            text = f.read_text(encoding="utf-8")
            title = next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("#")), f.stem)
            out.append({"id": f.stem, "name": title, "query": text})
        return out

    def check_kind(kind):
        if not KIND_RE.match(kind):
            abort(404)

    def best_offer():
        return request.accept_mimetypes.best_match(OFFERS, default="text/html")

    # ---------- error handling ----------

    @app.errorhandler(FusekiUnavailable)
    def unavailable(_):
        if request.path.startswith("/api/"):
            return jsonify(error=UNAVAILABLE), 502
        return render_template("error.html", title="Endpoint unavailable", message=UNAVAILABLE), 502

    @app.errorhandler(FusekiError)
    def rejected(e):
        if request.path.startswith("/api/"):
            return jsonify(error=str(e)), 400
        return render_template("error.html", title="Query rejected", message=str(e)), 400

    @app.errorhandler(404)
    def not_found(_):
        return render_template("error.html", title="Not found", message="Nothing here."), 404

    # ---------- pages ----------

    @app.get("/")
    def index():
        return render_template("index.html", examples=examples())

    @app.get("/search")
    def search():
        q = (request.args.get("q") or "").strip()
        error, results = None, []
        if q:
            if not 2 <= len(q) <= 80:
                error = "Type between 2 and 80 characters."
            else:
                results = ent.search(q)
        return render_template("search.html", q=q, results=results, error=error), (400 if error else 200)

    @app.get("/resource/<kind>/<path:key>")
    def resource(kind, key):
        check_kind(kind)
        iri = ent.iri(kind, key)
        if iri is None or not ent.exists(iri):
            abort(404)
        best = best_offer()
        if best == "text/html":
            return redirect(url_for("page", kind=kind, key=key), 303)
        return redirect(url_for("data", kind=kind, name=f"{key}.{MIME_EXT[best]}"), 303)

    @app.get("/page/<kind>/<path:key>")
    def page(kind, key):
        check_kind(kind)
        entity = ent.page(kind, key)
        if entity is None:
            abort(404)
        return render_template("entity.html", e=entity, kind=kind, key=key, exts=list(EXTS))

    @app.get("/data/<kind>/<path:name>")
    def data(kind, name):
        check_kind(kind)
        key, dot, ext = name.rpartition(".")
        if not dot or ext not in EXTS:
            abort(404)
        iri = ent.iri(kind, key)
        if iri is None:
            abort(404)
        graph = parse_turtle(ent.describe_graph(iri))
        if len(graph) == 0:
            abort(404)
        return Response(serialize(graph, ext), mimetype=EXTS[ext][0])

    @app.get("/ontology")
    @app.get("/ontology.<ext>")
    def ontology_view(ext=None):
        if ext is None:
            best = best_offer()
            if best == "text/html":
                return render_template("ontology.html", o=onto_summary, base=cfg["ontology_base"], exts=list(EXTS))
            ext = MIME_EXT[best]
        elif ext not in EXTS:
            abort(404)
        resp = Response(serialize(ontology, ext), mimetype=EXTS[ext][0])
        resp.headers["Content-Location"] = f"/ontology.{ext}"
        return resp

    # ---------- playground ----------

    @app.get("/query")
    def query_page():
        return render_template("query.html", resource_base=cfg["resource_base"])

    @app.get("/api/examples")
    def api_examples():
        return jsonify(examples())

    @app.post("/api/query")
    def api_query():
        payload = request.get_json(silent=True)
        text = payload.get("query") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            return jsonify(error="Enter a SPARQL query."), 400
        if len(text) > MAX_QUERY_CHARS:
            return jsonify(error=f"The query is longer than {MAX_QUERY_CHARS} characters."), 400
        try:
            form = query_form(text)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        if form == "select":
            res = client.select(text)
            names = res["head"]["vars"]
            bindings = res["results"]["bindings"]
            rows = [{n: (b[n]["value"] if n in b else None) for n in names} for b in bindings[:MAX_ROWS]]
            return jsonify(form="select", vars=names, rows=rows, truncated=len(bindings) > MAX_ROWS)
        if form == "ask":
            return jsonify(form="ask", boolean=client.ask(text))
        return jsonify(form="graph", turtle=client.construct(text))

    return app
```

- [ ] **Step 6: Write the templates**

`src/footballweb/templates/base.html`:
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Football LOD{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
  {% block head %}{% endblock %}
</head>
<body>
  <header class="top">
    <a class="brand" href="{{ url_for('index') }}">Football LOD</a>
    <nav>
      <a href="{{ url_for('query_page') }}">SPARQL</a>
      <a href="{{ url_for('ontology_view') }}">Ontology</a>
    </nav>
    <form class="searchbar" action="{{ url_for('search') }}" method="get">
      <input type="search" name="q" value="{{ q or '' }}" placeholder="Search players, clubs, countries" aria-label="Search" maxlength="80">
      <button type="submit">Search</button>
    </form>
  </header>
  <main>{% block content %}{% endblock %}</main>
  <footer>Linked Open Data from Transfermarkt, linked to Wikidata, DBpedia and GeoNames.</footer>
  {% block scripts %}{% endblock %}
</body>
</html>
```

`src/footballweb/templates/index.html`:
```html
{% extends "base.html" %}
{% block content %}
<section class="hero">
  <h1>Football Linked Open Data</h1>
  <p>Browse players, clubs, competitions and matches, follow links to Wikidata and DBpedia, or query the data with SPARQL.</p>
</section>
<section>
  <h2>Example queries</h2>
  <ul class="cards">
    {% for ex in examples %}
    <li><a href="{{ url_for('query_page') }}#{{ ex.id }}">{{ ex.name }}</a></li>
    {% endfor %}
  </ul>
</section>
{% endblock %}
```

`src/footballweb/templates/search.html`:
```html
{% extends "base.html" %}
{% block title %}Search {{ q }} · Football LOD{% endblock %}
{% block content %}
<h1>Search</h1>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
{% if q and not error %}
  {% if results %}
  <ul class="results">
    {% for r in results %}
    <li><a href="{{ r.href }}">{{ r.label }}</a> <span class="badge">{{ r.type }}</span></li>
    {% endfor %}
  </ul>
  {% else %}<p>No results for “{{ q }}”.</p>{% endif %}
{% elif not q %}
  <p>Type at least two characters in the search box.</p>
{% endif %}
{% endblock %}
```

`src/footballweb/templates/entity.html`:
```html
{% extends "base.html" %}
{% macro val(v) -%}
  {%- if v.kind == 'uri' -%}
    <a href="{{ v.href }}"{% if not v.internal %} rel="noopener"{% endif %}>{{ v.text }}</a>
  {%- else -%}
    {{ v.text }}{% if v.meta %} <span class="meta">{{ v.meta }}</span>{% endif %}
  {%- endif -%}
{%- endmacro %}
{% block title %}{{ e.title }} · Football LOD{% endblock %}
{% block content %}
<article>
  <header class="entity-head">
    {% if e.depiction %}<img class="depiction" src="{{ e.depiction }}" alt="" loading="lazy">{% endif %}
    <div>
      <h1>{{ e.title }}</h1>
      <p>{% for t in e.types %}<span class="badge">{{ t }}</span> {% endfor %}</p>
      <p class="uri"><code>{{ e.uri }}</code></p>
      <p class="formats">Data:
        {% for x in exts %}<a href="{{ url_for('data', kind=kind, name=key ~ '.' ~ x) }}">{{ x }}</a>{% if not loop.last %} · {% endif %}{% endfor %}
      </p>
    </div>
  </header>

  {% if e.external %}
  <section>
    <h2>Linked data</h2>
    <ul class="links">
      {% for l in e.external %}<li><span class="meta">{{ l.pred }}</span> <a href="{{ l.uri }}" rel="noopener">{{ l.uri }}</a></li>{% endfor %}
    </ul>
  </section>
  {% endif %}

  {% set rel = e.related %}
  {% if rel.totals %}
  <section>
    <h2>Career in the dataset</h2>
    <p>{{ rel.totals.appearances }} appearances, {{ rel.totals.goals }} goals.</p>
  </section>
  {% endif %}

  <section>
    <h2>Properties</h2>
    <table>
      <tbody>
      {% for g in e.groups %}
        <tr><th scope="row">{{ g.name }}</th><td>{% for v in g.values %}{{ val(v) }}{% if not loop.last %}<br>{% endif %}{% endfor %}</td></tr>
      {% endfor %}
      </tbody>
    </table>
  </section>

  {% if rel.transfers %}
  <section>
    <h2>Transfers</h2>
    <table>
      <thead><tr><th>Date</th><th>From</th><th>To</th><th class="num">Fee (EUR)</th></tr></thead>
      <tbody>
      {% for t in rel.transfers %}
        <tr><td>{{ t.date }}</td><td><a href="{{ t.from.href }}">{{ t.from.text }}</a></td><td><a href="{{ t.to.href }}">{{ t.to.text }}</a></td><td class="num">{{ t.fee or '' }}</td></tr>
      {% endfor %}
      </tbody>
    </table>
  </section>
  {% endif %}

  {% if rel.valuations %}
  <section>
    <h2>Market value history</h2>
    <table>
      <thead><tr><th>Date</th><th class="num">Value (EUR)</th></tr></thead>
      <tbody>{% for v in rel.valuations %}<tr><td>{{ v.date }}</td><td class="num">{{ v.value }}</td></tr>{% endfor %}</tbody>
    </table>
  </section>
  {% endif %}

  {% if rel.squad %}
  <section>
    <h2>Current squad</h2>
    <table>
      <thead><tr><th>Player</th><th class="num">Market value (EUR)</th></tr></thead>
      <tbody>{% for p in rel.squad %}<tr><td><a href="{{ p.href }}">{{ p.text }}</a></td><td class="num">{{ p.value or '' }}</td></tr>{% endfor %}</tbody>
    </table>
  </section>
  {% endif %}
</article>
{% endblock %}
```

`src/footballweb/templates/ontology.html`:
```html
{% extends "base.html" %}
{% block title %}Ontology · Football LOD{% endblock %}
{% block content %}
<h1>Football ontology</h1>
<p><code>{{ base }}</code></p>
<p class="formats">Download:
  {% for x in exts %}<a href="{{ url_for('ontology_view', ext=x) }}">{{ x }}</a>{% if not loop.last %} · {% endif %}{% endfor %}
</p>
<h2>Classes</h2>
<table>
  <thead><tr><th>Class</th><th>Subclass of</th><th>Description</th></tr></thead>
  <tbody>{% for c in o.classes %}<tr id="{{ c.name }}"><th scope="row">{{ c.name }}</th><td>{{ c.parents | join(', ') }}</td><td>{{ c.comment }}</td></tr>{% endfor %}</tbody>
</table>
<h2>Properties</h2>
<table>
  <thead><tr><th>Property</th><th>Kind</th><th>Domain</th><th>Range</th><th>Description</th></tr></thead>
  <tbody>{% for p in o.properties %}<tr id="{{ p.name }}"><th scope="row">{{ p.name }}</th><td>{{ p.kind }}</td><td>{{ p.domain }}</td><td>{{ p.range }}</td><td>{{ p.comment }}</td></tr>{% endfor %}</tbody>
</table>
{% endblock %}
```

`src/footballweb/templates/error.html`:
```html
{% extends "base.html" %}
{% block title %}{{ title }} · Football LOD{% endblock %}
{% block content %}
<h1>{{ title }}</h1>
<p>{{ message }}</p>
<p><a href="{{ url_for('index') }}">Back to the start page</a></p>
{% endblock %}
```

`src/footballweb/templates/query.html`:
```html
{% extends "base.html" %}
{% block title %}SPARQL · Football LOD{% endblock %}
{% block head %}
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css">
{% endblock %}
{% block content %}
<h1>SPARQL playground</h1>
<div class="toolbar">
  <label>Example <select id="examples"><option value="">Choose…</option></select></label>
  <button id="run" type="button">Run (Ctrl+Enter)</button>
  <button id="csv" type="button" disabled>Download CSV</button>
  <button id="json" type="button" disabled>Download JSON</button>
  <span id="status" role="status"></span>
</div>
<textarea id="q" aria-label="SPARQL query">SELECT ?s ?label WHERE { ?s rdfs:label ?label } LIMIT 10</textarea>
<div id="result" data-resource-base="{{ resource_base }}"></div>
{% endblock %}
{% block scripts %}
  <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/sparql/sparql.min.js"></script>
  <script src="{{ url_for('static', filename='query.js') }}"></script>
{% endblock %}
```
(The default query uses `rdfs:label` without a PREFIX: Fuseki rejects that. Change the default text to include `PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>` on its own line.)

- [ ] **Step 7: Write the static files**

`src/footballweb/static/style.css`:
```css
:root {
  --bg: #fafaf8; --fg: #1c1d21; --muted: #5d6270; --line: #dcdcd4; --card: #fff;
  --accent: #0b6b4d; --accent-fg: #fff; --err: #b3261e;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #14161a; --fg: #e8e8e4; --muted: #9aa0ad; --line: #2c3038; --card: #1c1f25; --accent: #4cc39a; --accent-fg: #0b1a14; --err: #f2b8b5; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, sans-serif; }
a { color: var(--accent); }
header.top { display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--line); background: var(--card); }
.brand { font-weight: 700; text-decoration: none; color: var(--fg); }
nav { display: flex; gap: 16px; }
.searchbar { margin-left: auto; display: flex; gap: 8px; }
input[type=search], select, textarea { font: inherit; color: var(--fg); background: var(--bg); border: 1px solid var(--line); border-radius: 6px; padding: 6px 10px; }
button { font: inherit; color: var(--accent-fg); background: var(--accent); border: 0; border-radius: 6px; padding: 6px 14px; cursor: pointer; }
button:disabled { opacity: .5; cursor: default; }
main { max-width: 1000px; margin: 0 auto; padding: 16px; }
footer { max-width: 1000px; margin: 24px auto; padding: 0 16px; color: var(--muted); font-size: 14px; }
.hero { padding: 24px 0; }
.cards, .results, .links { padding: 0; list-style: none; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.cards li { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
.badge { display: inline-block; font-size: 12px; padding: 1px 8px; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); }
.meta { color: var(--muted); font-size: 13px; }
.error { color: var(--err); }
.entity-head { display: flex; gap: 16px; align-items: flex-start; flex-wrap: wrap; }
.depiction { width: 120px; height: 120px; object-fit: cover; border-radius: 8px; border: 1px solid var(--line); }
.uri code { word-break: break-all; font-size: 13px; color: var(--muted); }
table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--line); border-radius: 8px; }
th, td { text-align: left; vertical-align: top; padding: 6px 10px; border-bottom: 1px solid var(--line); }
tbody th { width: 28%; font-weight: 600; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.toolbar { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; margin-bottom: 8px; }
.CodeMirror { height: 260px; border: 1px solid var(--line); border-radius: 6px; font-size: 14px; }
#result { margin-top: 16px; overflow-x: auto; }
#result pre { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 12px; overflow-x: auto; }
@media (max-width: 600px) { .searchbar { margin-left: 0; width: 100%; } .searchbar input { flex: 1; } }
```

`src/footballweb/static/query.js`:
```javascript
(function () {
  var resultEl = document.getElementById('result');
  var statusEl = document.getElementById('status');
  var csvBtn = document.getElementById('csv');
  var jsonBtn = document.getElementById('json');
  var select = document.getElementById('examples');
  var base = resultEl.dataset.resourceBase;
  var last = null;

  var editor = CodeMirror.fromTextArea(document.getElementById('q'), {
    mode: 'sparql', lineNumbers: true,
    extraKeys: { 'Ctrl-Enter': run, 'Cmd-Enter': run }
  });

  function setStatus(text) { statusEl.textContent = text; }

  function cell(value) {
    var td = document.createElement('td');
    if (value === null) return td;
    if (value.indexOf(base) === 0) {
      var a = document.createElement('a');
      a.href = '/page/' + value.slice(base.length);
      a.textContent = value;
      td.appendChild(a);
    } else if (/^https?:\/\//.test(value)) {
      var b = document.createElement('a');
      b.href = value; b.rel = 'noopener'; b.textContent = value;
      td.appendChild(b);
    } else {
      td.textContent = value;
    }
    return td;
  }

  function render(data) {
    resultEl.textContent = '';
    last = data;
    csvBtn.disabled = jsonBtn.disabled = data.form !== 'select';
    if (data.form === 'ask') {
      resultEl.textContent = data.boolean ? 'true' : 'false';
    } else if (data.form === 'graph') {
      var pre = document.createElement('pre');
      pre.textContent = data.turtle;
      resultEl.appendChild(pre);
    } else {
      var table = document.createElement('table');
      var head = table.createTHead().insertRow();
      data.vars.forEach(function (v) { var th = document.createElement('th'); th.textContent = v; head.appendChild(th); });
      var body = table.createTBody();
      data.rows.forEach(function (row) {
        var tr = body.insertRow();
        data.vars.forEach(function (v) { tr.appendChild(cell(row[v])); });
      });
      resultEl.appendChild(table);
      setStatus(data.rows.length + ' rows' + (data.truncated ? ' (truncated to 1000)' : ''));
    }
  }

  function run() {
    setStatus('Running…');
    fetch('/api/query', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: editor.getValue() })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) { resultEl.textContent = ''; last = null; csvBtn.disabled = jsonBtn.disabled = true; setStatus(res.body.error || 'Error'); return; }
        setStatus('');
        render(res.body);
      })
      .catch(function () { setStatus('Request failed'); });
  }

  function download(name, type, text) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: type }));
    a.download = name; a.click(); URL.revokeObjectURL(a.href);
  }

  function csvQuote(v) { return v === null ? '' : '"' + v.replace(/"/g, '""') + '"'; }

  csvBtn.addEventListener('click', function () {
    if (!last || last.form !== 'select') return;
    var lines = [last.vars.join(',')];
    last.rows.forEach(function (row) { lines.push(last.vars.map(function (v) { return csvQuote(row[v]); }).join(',')); });
    download('results.csv', 'text/csv', lines.join('\n'));
  });
  jsonBtn.addEventListener('click', function () {
    if (last && last.form === 'select') download('results.json', 'application/json', JSON.stringify(last.rows, null, 2));
  });
  document.getElementById('run').addEventListener('click', run);

  fetch('/api/examples').then(function (r) { return r.json(); }).then(function (examples) {
    examples.forEach(function (ex) {
      var opt = document.createElement('option');
      opt.value = ex.id; opt.textContent = ex.name; select.appendChild(opt);
    });
    function choose(id) {
      var ex = examples.find(function (e) { return e.id === id; });
      if (ex) { editor.setValue(ex.query); select.value = id; run(); }
    }
    select.addEventListener('change', function () { history.replaceState(null, '', '#' + select.value); choose(select.value); });
    if (location.hash.length > 1) choose(location.hash.slice(1));
  });
})();
```

- [ ] **Step 8: Run the tests**

Run: `.venv/bin/pytest -q 2>&1 | tail -15`
Expected: all pass. Typical fixes: if `test_entity_page_renders...` complains about the `<script>` assertion, the assertion only checks that no inline script exists in the body before the first external script tag; templates must not contain inline `<script>` blocks (the page templates above have none).

- [ ] **Step 9: Commit**

```bash
git add requirements.txt src/footballweb tests/test_web_app.py
git commit -m "feat(web): Flask app with entity pages, content negotiation, ontology page and SPARQL playground

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Run it for real, Docker, docs

**Files:**
- Create: `docker/Dockerfile.web`, `.dockerignore`
- Modify: `docker-compose.yml`, `Makefile`, `README.md`

**Interfaces:**
- Consumes: everything above, a running Fuseki with the regenerated data (Task 1).
- Produces: `make web` (port 8000), compose service `web`.

- [ ] **Step 1: Run against the live Fuseki and exercise every route**

```bash
cd "/home/jkl/Projects/Semantic Football Web"
curl -s -o /dev/null -w "fuseki %{http_code}\n" http://localhost:3030/\$/ping
PYTHONPATH=src .venv/bin/python -m flask --app footballweb run --port 8000 > .cache/web.log 2>&1 &
sleep 3
B=http://localhost:8000
P="resource/player/28003"
curl -s -o /dev/null -w "search %{http_code}\n" "$B/search?q=messi"
curl -s -o /dev/null -w "resource html -> %{http_code} %{redirect_url}\n" -H "Accept: text/html" "$B/$P"
curl -s -o /dev/null -w "resource ttl  -> %{http_code} %{redirect_url}\n" -H "Accept: text/turtle" "$B/$P"
curl -sL -H "Accept: text/turtle" "$B/$P" | head -8
curl -sL -H "Accept: application/ld+json" "$B/$P" | head -c 300; echo
curl -s -o /dev/null -w "page %{http_code}\n" "$B/page/player/28003"
curl -s "$B/page/player/28003" | grep -o "Transfers\|Market value history\|wikidata.org/entity/Q615" | sort -u
curl -s -o /dev/null -w "club page %{http_code}\n" "$B/page/club/11"
curl -s -o /dev/null -w "ontology %{http_code}\n" "$B/ontology"
curl -s -o /dev/null -w "unknown %{http_code}\n" "$B/resource/player/999999999"
curl -s -X POST -H 'Content-Type: application/json' -d '{"query":"DROP ALL"}' "$B/api/query"; echo
curl -s -X POST -H 'Content-Type: application/json' -d '{"query":"SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }"}' "$B/api/query"; echo
```
Expected: Fuseki 200; search 200; HTML → 303 to `/page/player/28003`; Turtle → 303 to `/data/player/28003.ttl` and then Turtle with Messi's label; JSON-LD document; player page 200 containing Transfers/Market value history/the Wikidata link `Q615`; club page 200; ontology 200; unknown resource 404; `DROP ALL` rejected with an error; the count query returns about 14.2 million. If a resource ID differs from the real data (for example Messi is not `28003` in this dataset), look the ID up with a search first and rerun.

- [ ] **Step 2: Run every example query through the API**

```bash
for f in queries/q*.rq; do
  python3 -c "import json,sys; print(json.dumps({'query': open(sys.argv[1], encoding='utf-8').read()}))" "$f" \
   | curl -s -X POST -H 'Content-Type: application/json' -d @- http://localhost:8000/api/query \
   | python3 -c "import json,sys; d=json.load(sys.stdin); print('$f', d.get('form') or d, len(d.get('rows',[])), d.get('error',''))"
done
```
Expected: nine lines with `select` and at least one row each (q04 needs network access to Wikidata). Any `error` is a defect to investigate.

- [ ] **Step 3: Look at the pages in a headless browser**

```bash
mkdir -p .cache/shots
for p in "" "page/player/28003" "page/club/11" "query" "ontology"; do
  n=$(echo "${p:-home}" | tr '/' '_')
  google-chrome --headless=new --no-sandbox --disable-gpu --hide-scrollbars --window-size=1200,1500 --virtual-time-budget=6000 \
    --screenshot=".cache/shots/$n.png" "http://localhost:8000/$p" >/dev/null 2>&1
done
ls -la .cache/shots
```
Then read each PNG with the Read tool and check layout and content (header, search box, tables, playground editor with a CodeMirror theme, no broken styling). The playground needs the cdnjs scripts; if the network blocks them the editor falls back to a plain textarea and `CodeMirror is not defined` appears in the page; in that case record it rather than guess.

- [ ] **Step 4: Stop the dev server**

```bash
pkill -f "flask --app footballweb" ; sleep 1; curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/ || true
```
Expected: connection refused (`000`).

- [ ] **Step 5: Write `.dockerignore` and `docker/Dockerfile.web`**

`.dockerignore`:
```
datasets
output
.cache
.venv
.git
.superpowers
__pycache__
*.pyc
tests
docs
```

`docker/Dockerfile.web`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "flask>=3.0" "gunicorn>=22.0" "rdflib>=7.0"
COPY src ./src
COPY ontology ./ontology
COPY queries ./queries
COPY config.json ./config.json
ENV PYTHONPATH=/app/src FUSEKI_URL=http://fuseki:3030/football
EXPOSE 8000
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-w", "2", "--timeout", "90", "footballweb:create_app()"]
```

- [ ] **Step 6: Extend `docker-compose.yml` and `Makefile`**

Add this service under `services:` in `docker-compose.yml` (keep the existing `fuseki` service and `volumes:` block):
```yaml
  web:
    build:
      context: .
      dockerfile: docker/Dockerfile.web
    ports:
      - "8000:8000"
    depends_on:
      - fuseki
```
Add to `Makefile` (and to `.PHONY`):
```make
web:    ; PYTHONPATH=src $(PY) -m flask --app footballweb run --port 8000
```

- [ ] **Step 7: Build and run the container, then repeat a smoke test**

```bash
docker compose build web 2>&1 | tail -3
docker compose up -d web 2>&1 | tail -2
sleep 4
curl -s -o /dev/null -w "web in docker %{http_code}\n" http://localhost:8000/
curl -s -o /dev/null -w "resource -> %{http_code} %{redirect_url}\n" -H "Accept: text/turtle" http://localhost:8000/resource/player/28003
curl -s -o /dev/null -w "page %{http_code}\n" http://localhost:8000/page/player/28003
```
Expected: image builds quickly (the build context excludes datasets), all three 200/303/200.

- [ ] **Step 8: Update `README.md`**

Add a "Web application" section after "Quick start" covering: `make web` and `http://localhost:8000`, the route table in short, content negotiation with a `curl -H "Accept: text/turtle" http://localhost:8000/resource/player/28003` example, and the namespace paragraph: the canonical URIs live under `https://vdhugn.github.io/Football-LOD/`, GitHub Pages cannot serve them itself, the app serves the same paths and the base URI is set in `config.json`. Update the Layout table with `src/footballweb/` and the "Not yet built" section (remove the web UI line, and mention that a public deployment and a dashboard page are not built). Update the test count after running `.venv/bin/pytest -q`.

- [ ] **Step 9: Run the full verification and commit**

```bash
.venv/bin/pytest -q 2>&1 | tail -2
git add -A docker .dockerignore docker-compose.yml Makefile README.md
git commit -m "feat(web): Docker service, make web target and documentation

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git status --short | wc -l
```
Expected: suite green; clean working tree.

---

## Self-review

**Spec coverage:** base URI (spec §2) Task 1; routes and behaviours (§3.1) Tasks 3–4 (`/`, `/search`, `/resource`, `/page`, `/data`, `/ontology`, `/query`, `/api/query`, `/api/examples`); entity page content incl. linked-data block, player and club sections, format links (§3.2) Tasks 3–4; playground features, query guard, truncation and response shapes (§3.3) Tasks 2 and 4; config and running (§3.4) Task 5; error handling (§4) Tasks 2, 4; testing incl. the example.org test and live checks (§5) Tasks 1, 2–4, 5. Spec detail added by the plan: `/api/examples` entries carry an `id` besides `name` and `query`.

**Placeholder scan:** none; Task 5 step 8 describes README content in prose because the README text depends on numbers produced by the run (test count, ports), the rest is complete.

**Name consistency:** `Entities.iri/exists/describe_graph/search/page`, `fmt_number`, `short`, `KIND_RE` are defined in Task 3 and used in Task 4 as defined. Endpoint names used by `url_for` (`index`, `search`, `resource`, `page`, `data`, `ontology_view`, `query_page`) match the function names in `app.py`. `rdfio.EXTS/MIME_EXT/OFFERS/parse_turtle/serialize` and `sparqlutil.escape_literal/query_form` match Task 2.

**Review Focus coverage:** (1) escaping — Task 2 `test_escape_literal...`, Task 3 `test_search_escapes_user_text_and_lowercases`; (2) update-keyword guard — Task 2 `test_query_form_*`, Task 4 `test_api_rejects_updates...`; (3) negotiation — Task 4 `test_resource_redirects_by_accept_header`; (4) special-character IDs — Task 4 `test_ids_with_special_characters_round_trip`; (5) clean failures — Task 2 `test_client_maps_http_and_network_errors`, Task 4 `test_api_maps_fuseki_errors`, `test_fuseki_down_gives_clean_502_page`.
